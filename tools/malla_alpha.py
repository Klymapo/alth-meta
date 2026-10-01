"""Herramientas sobre una COPIA de Theo Alpha para los bancos de T6 (Alpha nunca se escribe).

- `cargar(soldar=True)`: bmesh de la malla del cuerpo (theo_v3_v11) en mm ALTH (pies en Z=0, frente −Y),
  soldada (la malla de SAM 3D viene como triángulos sueltos) y su transformación de vuelta a Blender.
- `siluetas(verts, caras, vistas)`: máscaras ortográficas por vista (numpy + Pillow, sin render).
- `integridad(bm)`, `huella_congelada(bm, fuera)`: auditores de malla y de regiones congeladas.
- `region_mano(lado)`: vértices de la mano según data/alpha_medidas.json (medida en T0).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
ALPHA = RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb"
SHA_ALPHA = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"
CUERPO = "theo_v3_v11"
MEDIDAS = RAIZ / "data" / "alpha_medidas.json"
VISTAS = {  # mismas direcciones que alth.VISTAS (desde el objeto hacia la cámara)
    "frente": (0.0, -1.0, 0.0), "lateral": (1.0, 0.0, 0.0), "espalda": (0.0, 1.0, 0.0),
    "tres_cuartos": tuple(np.array([0.62, -0.72, 0.32]) / np.linalg.norm([0.62, -0.72, 0.32])),
}
SOLDADURA_MM = 1e-4


def sha_ok() -> bool:
    return hashlib.sha256(ALPHA.read_bytes()).hexdigest() == SHA_ALPHA


def cargar(soldar: bool = True):
    """(bmesh en mm ALTH, otros objetos {nombre: tris}). Alpha se lee; nunca se escribe."""
    import bpy
    import bmesh
    from mathutils import Matrix
    assert sha_ok(), "theo_alpha.glb no coincide con su SHA-256 protegido"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ALPHA))
    o = bpy.data.objects[CUERPO]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    # Blender (x, y, z) m → ALTH (x, z, −y) mm  ==  rotación −90° en X y ×1000
    a_alth = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1))) @ Matrix.Scale(1000.0, 4)
    bm.transform(a_alth @ o.matrix_world)
    suelo = min(v.co.z for v in bm.verts)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, -suelo))
    if soldar:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=SOLDADURA_MM)
    otros = {ob.name: sum(len(p.vertices) - 2 for p in ob.data.polygons)
             for ob in bpy.data.objects if ob.type == "MESH" and ob.name != CUERPO}
    assert sha_ok()
    return bm, otros


def arreglos(bm) -> tuple[np.ndarray, np.ndarray]:
    bm.verts.index_update()
    v = np.array([x.co[:] for x in bm.verts])
    tris = []
    for f in bm.faces:
        ids = [x.index for x in f.verts]
        for k in range(1, len(ids) - 1):
            tris.append((ids[0], ids[k], ids[k + 1]))
    return v, np.array(tris, dtype=np.int64).reshape(-1, 3)


def _base_vista(d) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(d, dtype=float)
    d = d / np.linalg.norm(d)
    arriba = np.array([0.0, 0.0, 1.0])
    der = np.cross(arriba, d)          # derecha de la imagen vista desde la cámara
    der /= np.linalg.norm(der)
    up = np.cross(d, der)
    return -der, up                    # x de imagen hacia la derecha del observador


def proyectar(v: np.ndarray, vista: str) -> np.ndarray:
    ex, ey = _base_vista(VISTAS[vista])
    return np.stack([v @ ex, v @ ey], 1)


def siluetas(v: np.ndarray, tris: np.ndarray, vistas=VISTAS, px_mm: float = 6.0, caja=None) -> dict:
    """{vista: (máscara bool, origen_mm, px_mm)}. `caja` = (min, max) mm en 3D para encuadrar igual."""
    out = {}
    for nombre in vistas:
        p = proyectar(v, nombre)
        if caja is not None:
            esquinas = np.array([[x, y, z] for x in caja[0][:1].tolist() + caja[1][:1].tolist()
                                 for y in (caja[0][1], caja[1][1]) for z in (caja[0][2], caja[1][2])])
            pc = proyectar(esquinas, nombre)
            mn, mx = pc.min(0), pc.max(0)
        else:
            mn, mx = p.min(0), p.max(0)
        w, h = int(np.ceil((mx[0] - mn[0]) * px_mm)) + 4, int(np.ceil((mx[1] - mn[1]) * px_mm)) + 4
        im = Image.new("1", (w, h), 0)
        dr = ImageDraw.Draw(im)
        q = (p - mn) * px_mm + 2
        q[:, 1] = h - 1 - q[:, 1]
        for t in tris:
            dr.polygon([tuple(q[i]) for i in t], fill=1)
        out[nombre] = (np.asarray(im, dtype=bool), mn, px_mm)
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    A = np.zeros((h, w), bool)
    B = np.zeros((h, w), bool)
    A[:a.shape[0], :a.shape[1]] = a
    B[:b.shape[0], :b.shape[1]] = b
    return float((A & B).sum() / max((A | B).sum(), 1))


def volumen(v: np.ndarray, tris: np.ndarray) -> float:
    """Volumen con signo por divergencia (mm³). Con bordes abiertos es aproximado: se compara relativo."""
    a, b, c = v[tris[:, 0]], v[tris[:, 1]], v[tris[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0))


def integridad(bm) -> dict:
    return {"verts": len(bm.verts), "tris": sum(len(f.verts) - 2 for f in bm.faces),
            "no_manifold": sum(1 for e in bm.edges if len(e.link_faces) > 2),
            "borde": sum(1 for e in bm.edges if len(e.link_faces) == 1),
            "aristas_sueltas": sum(1 for e in bm.edges if not e.link_faces),
            "degeneradas": sum(1 for f in bm.faces if f.calc_area() < 1e-8)}


def huella_congelada(bm, dentro) -> str:
    """Hash de las posiciones de los vértices FUERA de la región editable (deben quedar idénticas)."""
    pts = sorted({tuple(round(c, 4) for c in v.co) for v in bm.verts if not dentro(v.co)})   # posiciones únicas
    return hashlib.sha256(json.dumps(pts).encode()).hexdigest()


def region_mano(lado: str = "der", margen_mm: float = 0.5):
    """Función co → ¿está en la mano? (más allá de la muñeca medida en T0, dentro de la banda del brazo)."""
    med = json.loads(MEDIDAS.read_text(encoding="utf-8"))
    m = med["manos"][lado]
    s = 1 if lado == "der" else -1
    zc, gz = m["z_centro"], m["grosor_H"] / 2 + 3
    x0 = m["x_muneca"] - margen_mm

    def dentro(co) -> bool:
        return s * co[0] >= x0 and abs(co[2] - zc) <= gz
    return dentro


def huecos_por_vista(v: np.ndarray, tris: np.ndarray, dentro, px_mm: float = 12.0) -> dict:
    """Huecos entre dedos (tools/reconocer.huecos_entre_dedos) de la mano en cada vista ortográfica.

    Se rasteriza SOLO la geometría de la mano (triángulos con todos sus vértices en la región) para que
    el antebrazo o el cuerpo no tapen ni sumen huecos; es la misma medición que da 4 en la mano abierta
    de refs/infografias/mano-con-regla.jpg.
    """
    import sys as _s
    _s.path.insert(0, str(RAIZ / "tools"))
    import reconocer
    from scipy import ndimage
    en = np.array([dentro(x) for x in v])
    t = tris[en[tris].all(1)]
    if not len(t):
        return {k: 0 for k in VISTAS}
    out = {}
    for nombre, (m, _, _) in siluetas(v, t, px_mm=px_mm).items():
        et, n = ndimage.label(m)
        if n > 1:
            m = et == (1 + int(np.argmax(ndimage.sum(m, et, range(1, n + 1)))))
        out[nombre] = int(reconocer.huecos_entre_dedos(m))
    return out
