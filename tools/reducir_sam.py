"""Candidato reducido de la malla de SAM 3D de Theo (bloque T6 de docs/BRIEF_LINEA_UNICA.md), sin IA.

    alth-python tools/reducir_sam.py --brief kb/investigacion/<…>.json --salida .linea/t6/reduccion

La malla theo_v3_v11 trae 25 624 triángulos sueltos (76 872 vértices sin soldar); el tope de personaje
es 6000 para todo Theo. Las técnicas salen del brief de tools/investigar.py; aquí solo se buscan
parámetros y orden, de forma voraz y medida:
  - cada paso prueba cada técnica ejecutable (bmesh.ops sobre la región NO protegida; modificadores
    con el grupo de vértices "proteger" invertido) con valores muestreados de sus parámetros
    (rangos suaves que declara Blender para los modificadores, relativos al tamaño para bmesh);
  - se queda con el que más baja triángulos (a igualdad, vértices) sin violar: IoU de silueta ≥ 0.97 en las 4 vistas
    contra Alpha, volumen ±3 %, sin empeorar no-manifold/degeneradas/sueltas/bordes (agujeros) respecto al
    mejor paso anterior, cara y manos intactas;
  - para al llegar al tope o cuando ningún paso mejora (PLATEAU).
Alpha nunca se escribe; el candidato se exporta a <salida>/candidato_reducido.glb (no a assets/).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import malla_alpha as ma  # noqa: E402

TOPE_PERSONAJE = 6000
IOU_MIN = 0.97
VOLUMEN_TOL = 0.03
MUESTRAS = 6
MAX_PASOS = 8


def protegido_fn():
    """Cara (frente de la cabeza) y manos: no se tocan. Regiones medidas en T0 (data/alpha_medidas.json)."""
    med = json.loads(ma.MEDIDAS.read_text(encoding="utf-8"))
    manos = [ma.region_mano("der"), ma.region_mano("izq")]
    z_cuello = med["cabeza"]["z_cuello"]
    y_frente = med["cabeza"]["min"][1]
    prof = med["cabeza"]["D"]

    def dentro(co) -> bool:
        cara = co[2] >= z_cuello and co[1] <= y_frente + 0.4 * prof
        return cara or any(m(co) for m in manos)
    return dentro


def metricas(bm, ref_sil, vol_ref, protegido, huella_prot) -> dict:
    v, tris = ma.arreglos(bm)
    sil = ma.siluetas(v, tris, px_mm=3.0)
    ious = {k: round(ma.iou(sil[k][0], ref_sil[k][0]), 4) for k in sil}
    vol = ma.volumen(v, tris)
    integ = ma.integridad(bm)
    return {"tris": integ["tris"], "iou": ious, "iou_min": min(ious.values()),
            "volumen_rel": round(vol / vol_ref - 1, 4), "integridad": integ,
            "protegido_intacto": ma.huella_congelada(bm, lambda co: not protegido(co)) == huella_prot}


def aceptable(m: dict, base_integ: dict) -> tuple[bool, list[str]]:
    malos = []
    if m["iou_min"] < IOU_MIN:
        malos.append(f"IoU {m['iou_min']} < {IOU_MIN}")
    if abs(m["volumen_rel"]) > VOLUMEN_TOL:
        malos.append(f"volumen {m['volumen_rel'] * 100:+.1f} %")
    for k in ("no_manifold", "degeneradas", "aristas_sueltas", "borde"):   # borde = agujeros
        if m["integridad"][k] > base_integ[k]:
            malos.append(f"{k} {base_integ[k]}→{m['integridad'][k]}")
    if not m["protegido_intacto"]:
        malos.append("cambió la cara o las manos")
    return not malos, malos


def aplicar(bm, tecnica: dict, valores: dict, protegido, escala_mm: float):
    """Copia de bm con la técnica aplicada a lo NO protegido."""
    import bmesh
    import bpy
    nuevo = bm.copy()
    nombre = tecnica["name"]
    if nombre.startswith("bmesh.ops."):
        libres_v = [v for v in nuevo.verts if not protegido(v.co)]
        libres_f = [f for f in nuevo.faces if not any(protegido(v.co) for v in f.verts)]
        libres_e = list({e for f in libres_f for e in f.edges})
        kw = {}
        for p in tecnica.get("params_doc") or []:
            t = (tecnica.get("tipos") or {}).get(p)
            if t == "elementos" or p in ("verts", "edges", "faces", "geom"):
                kw[p] = libres_v if p.endswith("verts") else libres_e if p.endswith("edges") else \
                    libres_f if p.endswith("faces") else libres_v + libres_e + libres_f
            elif p in valores:
                kw[p] = valores[p] * escala_mm if t == "float" and not p.startswith(("use_", "angle")) else valores[p]
            elif t is None or t in ("puntero", "mapa", "matriz", "vector"):
                continue                     # sin tipo conocido o no muestreable: se deja el valor de Blender
        getattr(bmesh.ops, nombre.split(".")[-1])(nuevo, **kw)
        return nuevo
    if nombre.startswith("modificador:"):
        me = bpy.data.meshes.new("cand")
        nuevo.to_mesh(me)
        nuevo.free()
        ob = bpy.data.objects.new("cand", me)
        bpy.context.scene.collection.objects.link(ob)
        g = ob.vertex_groups.new(name="proteger")
        g.add([v.index for v in me.vertices if protegido(v.co)], 1.0, "REPLACE")
        mod = ob.modifiers.new("cand", nombre.split(":", 1)[1])
        for k, val in valores.items():
            if k.startswith("_"):
                continue
            try:
                setattr(mod, k, val)
            except (AttributeError, TypeError, ValueError):
                pass
        if valores.get("_proteger", True) and hasattr(mod, "vertex_group"):
            mod.vertex_group = "proteger"
            if hasattr(mod, "invert_vertex_group"):
                mod.invert_vertex_group = True
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        res = bmesh.new()
        res.from_mesh(ev.to_mesh())
        ev.to_mesh_clear()
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        return res
    raise ValueError(f"no ejecutable por datos: {nombre}")


def muestrear(tecnica: dict, rng: random.Random) -> dict:
    """Valores de parámetros. Modificadores: rangos suaves que declara Blender. bmesh: relativos (×mm)."""
    import bpy
    nombre = tecnica["name"]
    out = {}
    if nombre.startswith("modificador:"):
        ob = bpy.data.objects.new("tmp", bpy.data.meshes.new("tmp"))
        mod = ob.modifiers.new("tmp", nombre.split(":", 1)[1])
        for prop in mod.bl_rna.properties:
            if prop.is_readonly or prop.identifier in ("name", "show_viewport", "show_render", "show_in_editmode",
                                                       "show_on_cage", "show_expanded", "is_active", "use_pin_to_last"):
                continue
            if prop.type == "FLOAT" and getattr(prop, "array_length", 0) == 0:
                lo, hi = prop.soft_min, prop.soft_max
                if hi - lo < 1e6:
                    # rango de varios órdenes de magnitud (umbrales, distancias): muestreo logarítmico
                    if lo >= 0 and hi > 100 * max(lo, 1e-4):
                        out[prop.identifier] = round(10 ** rng.uniform(np.log10(max(lo, 1e-4)), np.log10(hi)), 6)
                    else:
                        out[prop.identifier] = round(rng.uniform(lo, hi), 4)
            elif prop.type == "INT" and getattr(prop, "array_length", 0) == 0:
                lo, hi = max(prop.soft_min, -10), min(prop.soft_max, 10)
                out[prop.identifier] = rng.randint(lo, hi) if hi >= lo else prop.default
            elif prop.type == "ENUM" and not prop.is_enum_flag:
                ids = [e.identifier for e in prop.enum_items]
                if ids:
                    out[prop.identifier] = rng.choice(ids)
        bpy.data.objects.remove(ob)
        # con o sin el grupo "proteger": quien decide si se tocó la cara o las manos es el auditor
        out["_proteger"] = rng.random() < 0.5
        return out
    for p in tecnica.get("params_doc") or []:
        t = (tecnica.get("tipos") or {}).get(p)
        lit = (tecnica.get("parametros") or {}).get(p)
        if t and t.startswith("enum:"):
            out[p] = lit if isinstance(lit, str) else rng.choice(t.split(":", 1)[1].split("|"))
        elif t == "bool":
            out[p] = lit if isinstance(lit, bool) else rng.random() < 0.5
        elif t == "int":
            out[p] = rng.randint(1, 4)
        elif t == "float":
            out[p] = round(10 ** rng.uniform(-5, -1.5), 6)     # fracción del tamaño del cuerpo
    return out


def reducir(brief: dict, salida: Path, semilla: int = 7) -> dict:
    import investigar
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    assert ma.sha_ok()
    rng = random.Random(semilla)
    ref, otros = ma.cargar(soldar=True)       # referencia de medida: Alpha soldada (misma superficie)
    v_ref, t_ref = ma.arreglos(ref)
    ref_sil = ma.siluetas(v_ref, t_ref, px_mm=3.0)
    vol_ref = ma.volumen(v_ref, t_ref)
    actual, _ = ma.cargar(soldar=False)       # el candidato parte de la malla tal como viene de SAM
    protegido = protegido_fn()
    huella_prot = ma.huella_congelada(ref, lambda co: not protegido(co))
    tope = TOPE_PERSONAJE - sum(otros.values())
    escala = float(np.ptp(v_ref[:, 2]))
    tecnicas = [t for t in brief.get("techniques", []) if t.get("estado") != "failed"
                and investigar.ejecutable(t["name"], t.get("tipos"))[0]]
    base = metricas(actual, ref_sil, vol_ref, protegido, huella_prot)
    base_integ = dict(base["integridad"])
    pasos, intentos = [], []
    estado = "RESEARCH_REQUIRED" if not tecnicas else "PLATEAU"
    for paso in range(1, MAX_PASOS + 1):
        if not tecnicas or base["tris"] <= tope:
            break
        mejor = None
        for t in tecnicas:
            for _ in range(MUESTRAS):
                vals = muestrear(t, rng)
                try:
                    cand = aplicar(actual, t, vals, protegido, escala)
                except Exception as e:  # noqa: BLE001
                    intentos.append({"paso": paso, "tecnica": t["name"], "valores": vals, "estado": "ERROR",
                                     "motivo": f"{type(e).__name__}: {e}"[:200]})
                    continue
                m = metricas(cand, ref_sil, vol_ref, protegido, huella_prot)
                ok, malos = aceptable(m, base_integ)
                intentos.append({"paso": paso, "tecnica": t["name"], "valores": vals, "estado": "PASS" if ok else "FAIL",
                                 "tris": m["tris"], "iou_min": m["iou_min"], "volumen_rel": m["volumen_rel"],
                                 "motivo": "; ".join(malos)})
                clave = (m["tris"], m["integridad"]["verts"])        # menos triángulos; a igualdad, menos vértices
                if ok and clave < (base["tris"], base["integridad"]["verts"]) and (
                        mejor is None or clave < (mejor[1]["tris"], mejor[1]["integridad"]["verts"])):
                    if mejor:
                        mejor[0].free()
                    mejor = (cand, m, t["name"], vals)
                else:
                    cand.free()
        if not mejor:
            break
        actual.free()
        actual, base = mejor[0], mejor[1]
        base_integ = {k: min(base_integ[k], base["integridad"][k]) for k in base_integ}
        pasos.append({"paso": paso, "tecnica": mejor[2], "valores": mejor[3], "tris": base["tris"],
                      "iou_min": base["iou_min"], "volumen_rel": base["volumen_rel"]})
    if tecnicas and base["tris"] <= tope:
        estado = "CANDIDATO_PARA_REVISION"
    res = {"estado": estado, "tope_cuerpo_tris": tope, "tris_inicial": 25624, "tris_final": base["tris"],
           "iou_por_vista": base["iou"], "volumen_rel": base["volumen_rel"], "integridad": base["integridad"],
           "protegido_intacto": base["protegido_intacto"], "pasos": pasos, "intentos": intentos,
           "tecnicas_disponibles": [t["name"] for t in tecnicas], "segundos": round(time.time() - t0, 1),
           "promocion": "deshabilitada: Alpha no se reemplaza; revisión visual del usuario"}
    if pasos:
        import bpy
        me = bpy.data.meshes.new("theo_reducido")
        actual.to_mesh(me)
        ob = bpy.data.objects.new("theo_reducido", me)
        bpy.context.scene.collection.objects.link(ob)
        for o in bpy.context.scene.objects:
            o.select_set(o is ob)
        bpy.ops.export_scene.gltf(filepath=str(salida / "candidato_reducido.glb"), export_format="GLB",
                                  use_selection=True)
        res["glb"] = str(salida / "candidato_reducido.glb")
    actual.free()
    ref.free()
    assert ma.sha_ok(), "Alpha cambió: no debe pasar nunca"
    res["alpha_sha_intacto"] = True
    (salida / "reduccion.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str) + "\n",
                                           encoding="utf-8")
    return res


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--brief", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--semilla", type=int, default=7)
    a = p.parse_args(argv)
    r = reducir(json.loads(Path(a.brief).read_text(encoding="utf-8")), Path(a.salida), a.semilla)
    print(json.dumps({k: v for k, v in r.items() if k != "intentos"}, ensure_ascii=False, indent=2, default=str))
    return {"CANDIDATO_PARA_REVISION": 0, "PLATEAU": 2}.get(r["estado"], 9)


if __name__ == "__main__":
    sys.exit(main())
