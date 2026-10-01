"""Mide Theo Alpha por piezas y escribe la escala nueva (bloque T0 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/medir_alpha.py                    # mide y escribe data/alpha_medidas.json
    alth-python tools/medir_alpha.py --spec             # además escribe spec/alth_spec.json v2
    alth-python tools/medir_alpha.py --comprobar        # re-mide y falla si no coincide con lo guardado

Alpha (assets/joven_rubio/theo_alpha.glb) es glTF con los datos en Z-up (sin raíz ×0.01, en metros):
al importarlo, Blender convierte Y-up → Z-up y el cuerpo queda acostado. Aquí se pasa a la convención
ALTH (mm, pies en Z=0, frente hacia −Y) con (x, y, z)_ALTH = (x, z, −y)_Blender × 1000.
El GLB nunca se modifica: se verifica su SHA-256 antes y después.

Qué es cada pieza se decide solo con geometría y color de la textura (sin IA):
  - piel / pelo / ropa: color de la textura en la UV de puntos muestreados sobre la superficie, al color medido más cercano de
    spec → paleta.medidos (Lab);
  - entrepierna: primera altura donde un rayo por X=0 atraviesa el cuerpo;
  - cuello: ancho mínimo del bloque central entre hombros y cabeza;
  - hombros/brazos/manos: pose T, los brazos van sobre X; la mano es la piel con |x| grande.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
ALPHA = RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb"
SHA_ALPHA = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"
CUERPO = "theo_v3_v11"           # malla de SAM 3D: el cuerpo completo (las demás son pelo y orejas)
SALIDA = RAIZ / "data" / "alpha_medidas.json"
SPEC = RAIZ / "spec" / "alth_spec.json"
ALTO_REAL_THEO_MM = 1800.0       # confirmado por el usuario (1 oct 2026), sin contar el pelo
CLASES = {  # clase → colores de spec.paleta.medidos que la representan
    "piel": ["piel_clara", "piel_clara_sombra"],
    "pelo": ["cabello_rubio", "rubio_arena"],
    "camisa": ["camisa_blanca"],
    "chaleco": ["chaleco_negro"],
    "pantalon": ["pantalon_azul"],
    "corbata": ["corbata_azul"],
    "zapato": ["zapato_negro", "botas_cafe"],
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _lab(rgb: np.ndarray) -> np.ndarray:
    """rgb (…, 3) en 0-255 → Lab D65 (igual que tools/reconocer.py; el Python de Blender no trae scipy)."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


# ---------------------------------------------------------------- Blender → numpy
def cargar_alpha():
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(ALPHA))
    mallas = {}
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        me = o.data
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        m = np.array(o.matrix_world)
        w = co @ m[:3, :3].T + m[:3, 3]
        mallas[o.name] = {"obj": o, "v": np.stack([w[:, 0], w[:, 2], -w[:, 1]], 1) * 1000.0}
    return mallas


def muestrear(o, v: np.ndarray, paso: float = 0.3, semilla: int = 7):
    """Puntos repartidos sobre la superficie (≈1 cada paso² mm²) con su color de textura (sRGB 0..255).

    La malla de SAM tiene triángulos de tamaños muy distintos: medir con sus vértices deja huecos
    falsos en las rebanadas. Muestrear la superficie da una densidad pareja.
    """
    me = o.data
    me.calc_loop_triangles()
    tri_v = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri_v)
    tri_l = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", tri_l)
    tri_v, tri_l = tri_v.reshape(-1, 3), tri_l.reshape(-1, 3)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    a, b, c = v[tri_v[:, 0]], v[tri_v[:, 1]], v[tri_v[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    rng = np.random.default_rng(semilla)
    n = rng.poisson(area / paso ** 2) + 1
    t = np.repeat(np.arange(len(n)), n)
    r1_, r2_ = rng.random(len(t)), rng.random(len(t))
    f = r1_ + r2_ > 1
    r1_[f], r2_[f] = 1 - r1_[f], 1 - r2_[f]
    w0 = 1 - r1_ - r2_
    p = w0[:, None] * a[t] + r1_[:, None] * b[t] + r2_[:, None] * c[t]
    q = w0[:, None] * uv[tri_l[t, 0]] + r1_[:, None] * uv[tri_l[t, 1]] + r2_[:, None] * uv[tri_l[t, 2]]
    img = next(nd.image for nd in me.materials[0].node_tree.nodes if nd.type == "TEX_IMAGE")
    iw, ih = img.size
    px = np.empty(iw * ih * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(ih, iw, 4)[..., :3]
    x = np.clip((q[:, 0] % 1.0) * (iw - 1), 0, iw - 1).astype(int)
    y = np.clip((q[:, 1] % 1.0) * (ih - 1), 0, ih - 1).astype(int)
    col = px[y, x].astype(np.float64)
    # pixeles de una imagen sRGB se leen tal cual (sRGB 0..1); otras se pasan de lineal a sRGB
    if img.colorspace_settings.name != "sRGB":
        col = np.where(col <= 0.0031308, 12.92 * col, 1.055 * col ** (1 / 2.4) - 0.055)
    return p, np.clip(col * 255.0, 0, 255)


def clasificar(rgb: np.ndarray, spec: dict) -> np.ndarray:
    med = spec["paleta"]["medidos"]
    nombres, labs = [], []
    for clase, claves in CLASES.items():
        for c in claves:
            h = med[c].lstrip("#")
            nombres.append(clase)
            labs.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    ref = _lab(np.array(labs, dtype=float))
    lab = _lab(rgb)
    d = ((lab[:, None, :] - ref[None, :, :]) ** 2).sum(-1)
    return np.array(nombres)[d.argmin(1)]


# ---------------------------------------------------------------- medición pura (numpy)
def r1(x) -> float:
    return round(float(x), 2)


def ext(v: np.ndarray) -> dict:
    mn, mx = v.min(0), v.max(0)
    return {"W": r1(mx[0] - mn[0]), "D": r1(mx[1] - mn[1]), "H": r1(mx[2] - mn[2]),
            "min": [r1(a) for a in mn], "max": [r1(a) for a in mx]}


def ancho_central(v: np.ndarray, z0: float, z1: float, paso: float = 0.5, hueco: float = 1.0):
    """(z, ancho X) del tramo continuo que contiene X=0 en cada rebanada (corta en huecos > `hueco` mm)."""
    filas = []
    for z in np.arange(z0, z1, paso):
        xs = np.sort(v[(v[:, 2] >= z) & (v[:, 2] < z + paso), 0])
        if len(xs) < 6:
            continue
        cortes = np.where(np.diff(xs) > hueco)[0]
        bordes = np.concatenate([[0], cortes + 1, [len(xs)]])
        for a, b in zip(bordes[:-1], bordes[1:]):
            if xs[a] <= 0 <= xs[b - 1]:
                filas.append((z + paso / 2, xs[b - 1] - xs[a]))
                break
    return filas


def _primero_estable(xs: np.ndarray, frac: np.ndarray, umbral: float = 0.5) -> float | None:
    """Menor x a partir de la cual la fracción se mantiene ≥ umbral hasta la punta."""
    ok = frac >= umbral
    for i in range(len(xs)):
        if ok[i:].all():
            return float(xs[i])
    return None


def medir(v: np.ndarray, clase: np.ndarray, todo: np.ndarray, rayo_x0, cuerpo_v: np.ndarray | None = None) -> dict:
    """Mide piezas sobre el cuerpo ya en mm ALTH. rayo_x0(z) → True si el cuerpo cruza X=0 a esa altura.

    Geometría primero (entrepierna, cuello, brazos, tobillo); el color de la textura solo decide
    piel contra manga (muñeca) y pelo contra piel (cabeza), que la forma no distingue.
    """
    cuerpo_v = v if cuerpo_v is None else cuerpo_v     # vértices reales: el piso y el tope exactos
    suelo = cuerpo_v[:, 2].min()
    v = v - [0, 0, suelo]
    todo = todo - [0, 0, suelo]
    alto = cuerpo_v[:, 2].max() - suelo

    # entrepierna: primera altura con cuerpo en X=0 (sube desde el piso)
    z_entre = next(z for z in np.arange(2.0, alto / 2, 0.1) if rayo_x0(z + suelo))

    # brazos en T: rebanadas cuyo tramo central es > 1.6× el de la cadera. Cuello: el ancho mínimo
    # entre el tope de los brazos y lo más ancho de la cabeza.
    filas = ancho_central(v, z_entre + 2, alto - 1)
    zs = np.array([z for z, _ in filas])
    anchos = np.array([w for _, w in filas])
    w_cadera = anchos[0]
    ancho = anchos > 1.6 * w_cadera              # la cabeza chibi también es ancha: solo el primer tramo
    i0 = int(np.argmax(ancho))
    i1 = i0 + (int(np.argmin(ancho[i0:])) if not ancho[i0:].all() else len(ancho) - i0)
    z_brazos = zs[i0:i1]
    arriba = zs > z_brazos.max()
    z_cab_ancha = zs[arriba][np.argmax(anchos[arriba])]
    tramo = arriba & (zs < z_cab_ancha)
    k = int(np.argmin(np.where(tramo, anchos, np.inf)))
    z_cuello, w_cuello = float(zs[k]), float(anchos[k])

    # torso: de la entrepierna al cuello; anchos medidos bajo las axilas (sin brazos)
    sin_brazos = zs < z_brazos.min()
    ancho_torso = float(anchos[sin_brazos].max())
    kc = int(np.argmin(np.where(sin_brazos, anchos, np.inf)))
    z_cintura, w_cintura = float(zs[kc]), float(anchos[kc])
    w_pecho = float(anchos[sin_brazos][-1])
    hombro_x = ancho_torso / 2
    # fondo del torso bajo las axilas: arriba de ellas cuelga el pelo de la nuca
    torso = v[(v[:, 2] > z_entre) & (v[:, 2] < z_brazos.min()) & (np.abs(v[:, 0]) <= hombro_x)]

    # brazos y manos: todo lo que sale más allá del torso entre la entrepierna y el cuello.
    # La muñeca es donde empieza la piel (por bandas de 0.5 mm en |x|, piel ≥ 50 % hasta la punta).
    manos, brazos = {}, {}
    for lado, s in (("izq", -1), ("der", 1)):
        sel = (s * v[:, 0] > hombro_x + 1) & (v[:, 2] > z_entre) & (v[:, 2] < z_cuello)
        b, cb = v[sel], clase[sel]
        if not len(b):
            continue
        ax = np.abs(b[:, 0])
        bins = np.arange(ax.min(), ax.max() + 0.5, 0.5)
        frac = np.array([(cb[(ax >= x) & (ax < x + 0.5)] == "piel").mean() if ((ax >= x) & (ax < x + 0.5)).any() else 1.0
                         for x in bins])  # banda vacía (pasada la punta) no interrumpe la piel
        x_muneca = _primero_estable(bins, frac) or float(ax.max())
        x_punta = float(ax.max())
        m = b[ax >= x_muneca]
        brazos[lado] = {"z_min": r1(b[:, 2].min()), "z_max": r1(b[:, 2].max())}
        manos[lado] = {"x_muneca": r1(x_muneca), "x_punta": r1(x_punta), "largo": r1(x_punta - x_muneca),
                       "ancho_D": r1(np.ptp(m[:, 1])), "grosor_H": r1(np.ptp(m[:, 2])), "z_centro": r1(m[:, 2].mean())}
    largo_mano = float(np.mean([m["largo"] for m in manos.values()])) if manos else None
    largo_brazo = float(np.mean([m["x_muneca"] for m in manos.values()])) - hombro_x if manos else None
    z_hombro = float(np.mean([(b["z_min"] + b["z_max"]) / 2 for b in brazos.values()])) if brazos else None

    # tobillo: el zapato es más profundo hacia el frente que la pierna; el tobillo es donde el frente
    # (Y mínima) de la rebanada ya recorrió el 90 % del camino del zapato a la pierna
    def y_frente(z):
        s_ = v[(v[:, 2] >= z) & (v[:, 2] < z + 0.5), 1]
        return s_.min() if len(s_) else np.nan
    y_zap, y_pie = y_frente(1.0), y_frente(z_entre - 1.0)
    z_tobillo = next((z for z in np.arange(1.0, z_entre, 0.25) if y_frente(z) >= y_zap + 0.9 * (y_pie - y_zap)), None)

    # cabeza: sobre el cuello y dentro del tramo central más ancho (deja fuera el tope de los hombros)
    media_cab = anchos[arriba].max() / 2 + 0.5
    en_cab = (v[:, 2] >= z_cuello) & (np.abs(v[:, 0]) <= media_cab)
    cabeza, cc = v[en_cab], clase[en_cab]
    zap = v[v[:, 2] <= (z_tobillo or 0)]

    return {
        "suelo_glb_mm": r1(suelo),
        "alto_cuerpo_mm": r1(alto),
        "alto_total_con_pelo_mm": r1(todo[:, 2].max()),
        "cabeza": {**ext(cabeza), "z_cuello": r1(z_cuello),
                   "pelo_frac": r1((cc == "pelo").mean()),
                   "nota": "H va del cuello al tope e incluye el volumen de pelo esculpido en la malla de SAM 3D"},
        "cuello_W": r1(w_cuello),
        "torso": {"z0": r1(z_entre), "z1": r1(z_cuello), "H": r1(z_cuello - z_entre), "ancho_max_W": r1(ancho_torso),
                  "D": r1(np.ptp(torso[:, 1])), "cintura_z": r1(z_cintura), "cintura_W": r1(w_cintura),
                  "pecho_W": r1(w_pecho), "cadera_W": r1(w_cadera)},
        "piernas": {"L": r1(z_entre), "tobillo_z": r1(z_tobillo) if z_tobillo else None,
                    "pierna_sin_zapato_L": r1(z_entre - z_tobillo) if z_tobillo else None},
        "brazos": {"pose": "T", "por_lado": brazos, "envergadura_W": r1(np.ptp(v[:, 0])), "hombro_x": r1(hombro_x),
                   "largo_hasta_muneca": r1(largo_brazo) if largo_brazo else None},
        "manos": manos,
        "largo_mano_mm": r1(largo_mano) if largo_mano else None,
        "zapatos": ext(zap) if len(zap) else None,
        "anclas_z": {"tobillo": r1(z_tobillo) if z_tobillo else None, "cadera": r1(z_entre), "cintura": r1(z_cintura),
                     "hombro": r1(z_hombro) if z_hombro else None, "cuello": r1(z_cuello), "cabeza_tope": r1(alto)},
        "clases_vertices": {c: int((clase == c).sum()) for c in CLASES},
    }


# ---------------------------------------------------------------- spec v2
BASE_95 = {"palma_L": 7.5, "dedo_medio": 6.0}   # spec v1 cuerpo_base_95mm (mano = palma + dedo medio)


def spec_v2(spec: dict, med: dict) -> dict:
    """Escribe en la spec la escala nueva sin borrar la v1 (queda como historial)."""
    s0 = med["alto_cuerpo_mm"] / ALTO_REAL_THEO_MM
    f_mano = med["largo_mano_mm"] / (BASE_95["palma_L"] + BASE_95["dedo_medio"]) if med["largo_mano_mm"] else 1.0
    cb = spec["cuerpo_base_95mm"]
    dedos = {k: round(v * f_mano, 2) for k, v in cb["dedos_L"].items()}
    palma = [round(x * f_mano, 2) for x in cb["palma_LW"]]
    estandar = spec["arquetipos_mm"]["estandar"]["altura"]   # v1 en mm de 95: solo se usan sus proporciones
    arquetipos = {}
    for nombre, a in spec["arquetipos_mm"].items():
        f = a["altura"] / estandar
        arquetipos[nombre] = {"factor_vs_alpha": round(f, 4), "alto_mm": round(med["alto_cuerpo_mm"] * f, 2),
                              "alto_real_mm": round(ALTO_REAL_THEO_MM * f), "personajes": a["personajes"],
                              "delta_rel": {k: round(d / estandar, 4) for k, d in a.get("delta", {}).items()}}
    nuevo = dict(spec)
    nuevo["version"] = "2.0"
    nuevo["fecha"] = "2026-10-01"
    nuevo["escala_congelada"] = {
        "version": "v2.0", "fecha": "2026-10-01",
        "nota": "Escala de 95 mm descartada (decisión del usuario, 1 oct 2026). La base es Theo Alpha "
                "(assets/joven_rubio/theo_alpha.glb) medido con tools/medir_alpha.py.",
        # re-correr sobre una spec v2 no anida historiales: se conserva la v1 original
        "anterior": spec["escala_congelada"].get("anterior") if spec.get("escala_alpha") else spec.get("escala_congelada"),
    }
    nuevo["escala_alpha"] = {
        "s0": round(s0, 5),
        "formula_s0": "alto_cuerpo_alpha_mm / alto_real_theo_mm",
        "alto_cuerpo_alpha_mm": med["alto_cuerpo_mm"],
        "alto_cuerpo_nota": "malla theo_v3_v11 sin las mallas de pelo ni orejas, de la suela al tope (el tope "
                            "incluye el volumen esculpido de SAM 3D en la coronilla)",
        "alto_total_con_pelo_mm": med["alto_total_con_pelo_mm"],
        "alto_real_theo_mm": ALTO_REAL_THEO_MM,
        "alto_real_nota": "parámetro: Theo mide ≈1.80 m sin contar el pelo (confirmado por el usuario); "
                          "cambiarlo cambia s0",
        "fuente": "assets/joven_rubio/theo_alpha.glb",
        "sha256_fuente": SHA_ALPHA,
        "medidas": "data/alpha_medidas.json",
        "piezas_mm": {
            "cabeza_WHD": [med["cabeza"]["W"], med["cabeza"]["H"], med["cabeza"]["D"]],
            "cuello_z": med["anclas_z"]["cuello"], "cuello_W": med["cuello_W"],
            "torso_H": med["torso"]["H"], "torso_W": med["torso"]["ancho_max_W"], "torso_D": med["torso"]["D"],
            "piernas_L": med["piernas"]["L"], "tobillo_z": med["anclas_z"]["tobillo"],
            "brazo_hasta_muneca_L": med["brazos"]["largo_hasta_muneca"], "hombro_x": med["brazos"]["hombro_x"],
            "envergadura_T": med["brazos"]["envergadura_W"], "mano_L": med["largo_mano_mm"],
        },
        "anclas_z_mm": med["anclas_z"],
        "anclas_nota": "Alpha está en pose T: muñeca y punta de mano no tienen altura de pie; se miden en X.",
        "mano_mm": {
            "factor_vs_95": round(f_mano, 4),
            "palma_LW": palma,
            "dedos_L": dedos,
            "medida_en_alpha": {"L": med["largo_mano_mm"],
                                "ancho": r1(np.mean([m["ancho_D"] for m in med["manos"].values()])),
                                "grosor": r1(np.mean([m["grosor_H"] for m in med["manos"].values()]))},
            "nota": "cotas del estándar de 95 mm (palma 7.5 + dedo medio 6.0) reescaladas al largo de mano "
                    "medido en Alpha; las referencias de Theo dibujan dedos juntos y no sirven para esto",
        },
    }
    nuevo["arquetipos_alpha"] = arquetipos
    u = dict(spec["unidades"])
    u.update({"humano_real_mm": ALTO_REAL_THEO_MM, "s0_real_a_alth": round(s0, 5),
              "s0_nota": "copia de escala_alpha.s0 (la fuente es escala_alpha)"})
    u["export_godot"] = dict(u["export_godot"], nota="la raíz ×0.01 deja 1 mm de maqueta = 1 cm en Godot")
    nuevo["unidades"] = u
    ck = dict(spec["conversion_k"])
    ck["formula"] = "mm_alth = mm_real * escala_alpha.s0 * k"
    nuevo["conversion_k"] = ck
    nuevo["cuerpo_base_95mm_nota"] = "Historial v1 (escala de 95 mm descartada). Para medidas nuevas usa escala_alpha."
    return nuevo


def comparar(guardado, medido, tol: float = 0.05, ruta: str = "") -> list[str]:
    """Diferencias numéricas > tol mm entre dos mediciones (recursivo)."""
    if isinstance(guardado, dict) and isinstance(medido, dict):
        out = []
        for k in guardado.keys() | medido.keys():
            if k == "clases_vertices":     # conteos de muestreo: informativos, no cotas
                continue
            if k not in guardado or k not in medido:
                out.append(f"{ruta}{k}: falta en {'la medición' if k not in medido else 'lo guardado'}")
            else:
                out += comparar(guardado[k], medido[k], tol, f"{ruta}{k}.")
        return out
    if isinstance(guardado, list) and isinstance(medido, list) and len(guardado) == len(medido):
        return [d for i, (a, b) in enumerate(zip(guardado, medido)) for d in comparar(a, b, tol, f"{ruta}{i}.")]
    if isinstance(guardado, (int, float)) and isinstance(medido, (int, float)):
        return [] if abs(guardado - medido) <= tol else [f"{ruta[:-1]}: guardado {guardado} ≠ medido {medido}"]
    return [] if guardado == medido else [f"{ruta[:-1]}: guardado {guardado!r} ≠ medido {medido!r}"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", action="store_true", help="escribe spec/alth_spec.json v2")
    ap.add_argument("--comprobar", action="store_true",
                    help="no escribe: compara con data/alpha_medidas.json y la spec (CI)")
    args = ap.parse_args(argv)
    if sha256(ALPHA) != SHA_ALPHA:
        print("ERROR: theo_alpha.glb no coincide con su SHA-256 protegido", file=sys.stderr)
        return 2
    import bpy  # noqa: F401
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    mallas = cargar_alpha()
    cu = mallas[CUERPO]
    puntos, rgb = muestrear(cu["obj"], cu["v"])
    clase = clasificar(rgb, spec)
    todo = np.concatenate([m["v"] for m in mallas.values()])

    o = cu["obj"]
    bvh = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())
    mi = o.matrix_world.inverted()

    def rayo_x0(z_alth: float) -> bool:
        # ALTH (x, y, z) mm → Blender (x, −z, y) m ; rayo a lo largo de Y_ALTH = Z_Blender
        ini = mi @ Vector((0.0, -z_alth / 1000.0, -1.0))
        dir_ = (mi.to_3x3() @ Vector((0, 0, 1))).normalized()
        return bvh.ray_cast(ini, dir_)[0] is not None

    med = medir(puntos, clase, todo, rayo_x0, cuerpo_v=cu["v"])
    med["s0"] = round(med["alto_cuerpo_mm"] / ALTO_REAL_THEO_MM, 5)
    med["fuente"] = {"glb": str(ALPHA.relative_to(RAIZ)), "sha256": SHA_ALPHA, "malla_cuerpo": CUERPO,
                     "tris": {n: sum(len(p.vertices) - 2 for p in m["obj"].data.polygons) for n, m in mallas.items()}}
    if args.comprobar:
        assert sha256(ALPHA) == SHA_ALPHA, "Alpha cambió: no debe pasar nunca"
        difs = comparar(json.loads(SALIDA.read_text(encoding="utf-8")), med)
        if spec.get("escala_alpha", {}).get("s0") != med["s0"]:
            difs.append(f"spec escala_alpha.s0={spec.get('escala_alpha', {}).get('s0')} ≠ medido {med['s0']}")
        print("\n".join(difs) or f"OK: Alpha mide lo guardado (s0 = {med['s0']})")
        return 1 if difs else 0
    SALIDA.write_text(json.dumps(med, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(med, ensure_ascii=False, indent=1))
    if args.spec:
        SPEC.write_text(json.dumps(spec_v2(spec, med), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("spec v2 escrita:", SPEC.relative_to(RAIZ))
    assert sha256(ALPHA) == SHA_ALPHA, "Alpha cambió: no debe pasar nunca"
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
