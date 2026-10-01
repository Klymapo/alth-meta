"""Banco genérico de tools/investigar.py: ¿el candidato se puede aplicar sin romper la malla?

Solo puede TUMBAR un candidato (`failed`): si truena o deja la malla peor (aristas no-manifold, caras
degeneradas o aristas sueltas nuevas). Si pasa, el candidato sigue `unverified`: probar que resuelve el problema le toca
al banco propio de la capacidad (tools/bancos/<capacidad>.py), con la misma interfaz:

    probar(tecnica: dict, carpeta: Path) -> {"ok": True | False | None, "motivo": str,
                                              "metricas": dict, "evidencia": [rutas]}

`ok=None` = no se pudo ejercitar (sin efecto con los parámetros encontrados): no cuenta como falla.
Sin bpy.ops: todo por bmesh y modificadores evaluados por datos (regla ALTH).
"""
from __future__ import annotations

import json
from pathlib import Path

ELEMENTOS = {"geom", "verts", "edges", "faces", "geom_split", "input"}


def integridad(bm) -> dict:
    no_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    borde = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    sueltas = sum(1 for e in bm.edges if not e.link_faces)
    degeneradas = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    return {"verts": len(bm.verts), "caras": len(bm.faces), "no_manifold": no_manifold, "borde": borde,
            "aristas_sueltas": sueltas, "degeneradas": degeneradas,
            "tris": sum(len(f.verts) - 2 for f in bm.faces)}


def huella(bm) -> tuple:
    return (len(bm.verts), len(bm.edges), len(bm.faces),
            round(sum(v.co.x * 1.3 + v.co.y * 1.7 + v.co.z * 1.9 for v in bm.verts), 4))


def malla_banco():
    """Esfera cerrada de 10 mm con 'región' = mitad superior (edición local, como en un asset real)."""
    import bpy  # noqa: F401 — bmesh solo existe con bpy cargado
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=5.0)
    return bm


def kwargs_para(bm, tecnica: dict) -> dict:
    region_f = [f for f in bm.faces if f.calc_center_median().z > 0]
    region_v = list({v for f in region_f for v in f.verts})
    region_e = list({e for f in region_f for e in f.edges})
    tipos = tecnica.get("tipos") or {}
    kw = {}
    for p in tecnica.get("params_doc") or []:
        t = tipos.get(p)
        if p in ELEMENTOS or t == "elementos":
            if p in ("verts",):
                kw[p] = region_v
            elif p in ("edges",):
                kw[p] = region_e
            elif p in ("faces",):
                kw[p] = region_f
            elif p in ("geom", "input", "geom_split"):
                kw[p] = region_v + region_e + region_f
    for k, v in (tecnica.get("parametros") or {}).items():
        escalar = isinstance(v, (int, float, bool, str))
        vector = isinstance(v, (list, tuple)) and all(isinstance(x, (int, float)) for x in v)
        if k not in kw and (escalar or vector):
            kw[k] = v
    return kw


def aplicar(bm, tecnica: dict):
    import bpy
    import bmesh
    nombre = tecnica["name"]
    if nombre.startswith("bmesh.ops."):
        if any(t == "puntero" for t in (tecnica.get("tipos") or {}).values()):
            raise ValueError("pide un puntero (otra malla u objeto): no se ejecuta vacío")
        op = getattr(bmesh.ops, nombre.split(".")[-1])
        op(bm, **kwargs_para(bm, tecnica))
        return bm
    if nombre.startswith("modificador:"):
        me = bpy.data.meshes.new("banco")
        bm.to_mesh(me)
        ob = bpy.data.objects.new("banco", me)
        bpy.context.scene.collection.objects.link(ob)
        mod = ob.modifiers.new("cand", nombre.split(":", 1)[1])
        for k, v in (tecnica.get("parametros") or {}).items():
            if hasattr(mod, k) and not isinstance(v, (dict, list)):
                try:
                    setattr(mod, k, v)
                except (TypeError, AttributeError, ValueError):
                    pass
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        nuevo = bmesh.new()
        nuevo.from_mesh(ev.to_mesh())
        ev.to_mesh_clear()
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        return nuevo
    raise ValueError(f"no ejecutable por datos: {nombre}")


def probar(tecnica: dict, carpeta: Path) -> dict:
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    bm = malla_banco()
    antes, h0 = integridad(bm), huella(bm)
    try:
        bm2 = aplicar(bm, tecnica)
        bm2.normal_update()
    except Exception as e:  # noqa: BLE001 — cualquier error del candidato es su resultado
        r = {"ok": False, "motivo": f"error al aplicar en el banco: {type(e).__name__}: {e}"[:300],
             "metricas": {"antes": antes}}
    else:
        despues = integridad(bm2)
        if huella(bm2) == h0:
            r = {"ok": None, "motivo": "sin efecto en el banco con los parámetros encontrados", "metricas":
                 {"antes": antes, "despues": despues}}
        elif any(despues[k] > antes[k] for k in ("no_manifold", "degeneradas", "aristas_sueltas")):
            r = {"ok": False, "motivo": f"rompe la malla: no-manifold {antes['no_manifold']}→{despues['no_manifold']}, "
                 f"degeneradas {antes['degeneradas']}→{despues['degeneradas']}, "
                 f"aristas sueltas {antes['aristas_sueltas']}→{despues['aristas_sueltas']}",
                 "metricas": {"antes": antes, "despues": despues}}
        else:
            r = {"ok": True, "motivo": f"aplica sin romper la malla (borde {antes['borde']}→{despues['borde']}, "
                 f"tris {antes['tris']}→{despues['tris']})", "metricas": {"antes": antes, "despues": despues}}
    ruta = carpeta / "integridad.json"
    ruta.write_text(json.dumps({"tecnica": tecnica["name"], **r}, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    r["evidencia"] = [str(ruta)]
    return r
