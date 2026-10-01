"""Campaña de dedos separados en Theo (bloque T6 de docs/BRIEF_LINEA_UNICA.md), sin IA.

    alth-python tools/campana_dedos.py --brief kb/investigacion/<dedos-…>.json --salida .linea/t6

Los candidatos salen SOLO de lo que encontró tools/investigar.py (técnicas del brief, que ya excluyen
las fallidas). El motor no sabe "cómo se hacen dedos": prueba secuencias de 1-2 operadores con
parámetros muestreados en el marco local de la mano (ejes principales, fracciones del largo y del
ancho, subconjuntos de la región) y mide. Reglas (CLAUDE.md, protección de Theo):
  - Alpha nunca se escribe ni se reemplaza (SHA verificado antes y después); se trabaja en una copia;
  - exactamente 3 hermanos por generación, todos desde la misma baseline; máximo 3 generaciones;
  - un candidato pasa solo si: ≥ 3 huecos entre dedos en alguna vista (misma medición de reconocer),
    integridad sin empeorar (no-manifold, degeneradas, sueltas, bordes), región congelada idéntica;
  - los rechazos se publican con su evidencia; un candidato que pase NO se promueve solo: queda en
    candidato.glb para revisión visual del usuario (en una rama aparte, nunca en main).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import malla_alpha as ma  # noqa: E402

HERMANOS = 3
MAX_GENERACIONES = 3
HUECOS_MIN = 3
NO_AJUSTABLES = {"puntero", "mapa", "matriz"}


# ---------------------------------------------------------------- marco de la mano
def marco(pts: np.ndarray) -> dict:
    c = pts.mean(0)
    vals, vecs = np.linalg.eigh(np.cov((pts - c).T))
    ejes = vecs[:, ::-1].T                       # e1 = largo, e2 = ancho, e3 = grosor
    proy = (pts - c) @ ejes.T
    return {"c": c, "ejes": ejes, "min": proy.min(0), "max": proy.max(0), "L": np.ptp(proy, 0)}


def _tipo(nombre: str, tipos: dict) -> str:
    t = tipos.get(nombre)
    if t:
        return t
    n = nombre.lower()
    if n.startswith("use_") or n.startswith("is_"):
        return "bool"
    if n in ("geom", "verts", "edges", "faces", "input") or n.endswith(("_verts", "_edges", "_faces")):
        return "elementos"
    if any(k in n for k in ("_no", "normal", "axis", "_co", "cent", "vec", "dir")):
        return "vector"
    if any(k in n for k in ("segments", "steps", "cuts", "count", "num")):
        return "int"
    return "float"


def muestrear_params(tecnica: dict, mf: dict, rng: random.Random) -> dict:
    """Valores concretos para cada parámetro, en el marco de la mano. Los literales de los ejemplos
    publicados se usan si existen; el resto se muestrea en rangos relativos al tamaño de la mano."""
    out = {}
    tipos = tecnica.get("tipos") or {}
    for p in tecnica.get("params_doc") or []:
        t = _tipo(p, tipos)
        if t in NO_AJUSTABLES:
            continue
        lit = (tecnica.get("parametros") or {}).get(p)
        if t.startswith("enum"):
            ops_ = t.split(":", 1)[1].split("|") if ":" in t else []
            if isinstance(lit, str):
                out[p] = lit
            elif ops_:
                out[p] = rng.choice(ops_)
            continue                                    # enum sin valores conocidos: se deja el de Blender
        if t == "elementos":
            out[p] = {"region": rng.choice(["toda", "distal", "franja"]), "f": round(rng.uniform(-0.45, 0.45), 3),
                      "eje": rng.choice([1, 2])}
        elif t == "bool":
            out[p] = lit if isinstance(lit, bool) else rng.random() < 0.5
        elif t == "int":
            out[p] = lit if isinstance(lit, int) and not isinstance(lit, bool) else rng.randint(1, 4)
        elif t == "vector":
            if any(k in p for k in ("_co", "cent", "center")):
                out[p] = {"punto": [round(rng.uniform(0.0, 0.45), 3), round(rng.uniform(-0.45, 0.45), 3), 0.0]}
            else:
                out[p] = {"eje": rng.randrange(3), "signo": rng.choice([1, -1]),
                          "escala": round(rng.choice([1.0, 0.1, 0.25, 0.5]), 3)}
        else:
            if "angle" in p:
                out[p] = round(rng.uniform(0.0, math.pi / 2), 4)
            elif any(k in p for k in ("fac", "percent", "ratio", "weight")):
                out[p] = round(rng.uniform(0.0, 1.0), 4)
            else:                                  # longitudes: fracción del largo de la mano
                out[p] = {"frac_largo": round(10 ** rng.uniform(-2.3, -0.5), 4)}
    return out


def concretar(params: dict, bm, dentro, mf: dict) -> dict:
    """Traduce los parámetros relativos a la mano a argumentos de bmesh.ops."""
    from mathutils import Vector
    caras_mano = [f for f in bm.faces if all(dentro(v.co) for v in f.verts)]
    kw = {}
    for p, val in params.items():
        if isinstance(val, dict) and "region" in val:
            sel = caras_mano
            if val["region"] != "toda":
                e = mf["ejes"][0 if val["region"] == "distal" else val["eje"]]
                L = mf["L"][0 if val["region"] == "distal" else val["eje"]]
                corte = 0.0 if val["region"] == "distal" else val["f"] * L
                ancho = L / 6
                sel = [f for f in caras_mano if (
                    (np.dot(np.array(f.calc_center_median()) - mf["c"], e) > corte) if val["region"] == "distal"
                    else abs(np.dot(np.array(f.calc_center_median()) - mf["c"], e) - corte) < ancho)]
            vs = list({v for f in sel for v in f.verts})
            es = list({e for f in sel for e in f.edges})
            kw[p] = vs if p.endswith("verts") else es if p.endswith("edges") else sel if p.endswith("faces") \
                else vs + es + sel
        elif isinstance(val, dict) and "punto" in val:
            a, b, c = val["punto"]
            q = mf["c"] + sum(f * L * e for f, L, e in zip((a, b, c), mf["L"], mf["ejes"]))
            kw[p] = Vector(q.tolist())
        elif isinstance(val, dict) and "eje" in val:
            kw[p] = Vector((val["signo"] * mf["ejes"][val["eje"]] * val["escala"]
                            * (mf["L"][0] if val["escala"] != 1.0 else 1.0)).tolist())
        elif isinstance(val, dict) and "frac_largo" in val:
            kw[p] = float(val["frac_largo"] * mf["L"][0])
        else:
            kw[p] = val
    return kw


# ---------------------------------------------------------------- evaluación
def evaluar(bm_base, secuencia: list[dict], dentro, mf: dict, base: dict) -> dict:
    import bmesh
    bm = bm_base.copy()
    try:
        for paso in secuencia:
            op = getattr(bmesh.ops, paso["tecnica"].split(".")[-1])
            op(bm, **concretar(paso["params"], bm, dentro, mf))
        bm.normal_update()
    except Exception as e:  # noqa: BLE001 — el error del candidato es su resultado
        bm.free()
        return {"status": "REJECTED", "reason": f"error al aplicar: {type(e).__name__}: {e}"[:300]}
    integ = ma.integridad(bm)
    congelada = ma.huella_congelada(bm, dentro) == base["huella"]
    v, tris = ma.arreglos(bm)
    huecos = ma.huecos_por_vista(v, tris, dentro)
    bm.free()
    aud = [
        {"id": "huecos_dedos", "status": "PASS" if max(huecos.values()) >= HUECOS_MIN else "FAIL", "detalle": huecos},
        {"id": "integridad", "status": "PASS" if all(integ[k] <= base["integridad"][k] for k in
                                                    ("no_manifold", "degeneradas", "aristas_sueltas", "borde"))
         else "FAIL", "detalle": {"antes": base["integridad"], "despues": integ}},
        {"id": "regiones_congeladas", "status": "PASS" if congelada else "FAIL",
         "detalle": "fuera de la mano idéntico" if congelada else "cambió geometría fuera de la mano"},
    ]
    ok = all(a["status"] == "PASS" for a in aud)
    return {"status": "ELIGIBLE" if ok else "REJECTED", "audit": aud, "score": max(huecos.values()),
            "reason": None if ok else "auditor_veto: " + ", ".join(a["id"] for a in aud if a["status"] == "FAIL")}


def campana(brief: dict, salida: Path, semilla: int = 7, lado: str = "der") -> dict:
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    assert ma.sha_ok()
    bm, _ = ma.cargar()
    dentro = ma.region_mano(lado)
    pts = np.array([v.co[:] for v in bm.verts if dentro(v.co)])
    mf = marco(pts)
    v, tris = ma.arreglos(bm)
    base = {"integridad": ma.integridad(bm), "huella": ma.huella_congelada(bm, dentro),
            "huecos": ma.huecos_por_vista(v, tris, dentro)}
    import investigar
    tecnicas = [t for t in brief.get("techniques", []) if t["name"].startswith("bmesh.ops.")
                and t.get("estado") != "failed" and investigar.ejecutable(t["name"], t.get("tipos"))[0]]
    rng = random.Random(semilla)
    manifest = {"campana": "dedos-separados-theo", "brief": brief.get("research_id"), "semilla": semilla,
                "baseline": {"huecos": base["huecos"], "integridad": base["integridad"]},
                "tecnicas_disponibles": [t["name"] for t in tecnicas],
                "no_repetir": brief.get("no_repetir", []), "candidates": [], "generaciones": []}
    ganador = None
    if not tecnicas:
        manifest["estado"] = "RESEARCH_REQUIRED"
    else:
        for g in range(1, MAX_GENERACIONES + 1):
            elegibles = []
            for k in range(1, HERMANOS + 1):
                n = 1 if rng.random() < 0.5 else 2
                secuencia = [{"tecnica": (t := rng.choice(tecnicas))["name"], "params": muestrear_params(t, mf, rng)}
                             for _ in range(n)]
                r = evaluar(bm, secuencia, dentro, mf, base)
                c = {"id": f"g{g:02d}-c{k:02d}", "generacion": g, "padre": "alpha-soldada", "secuencia": secuencia, **r}
                (salida / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, indent=2, default=str),
                                                       encoding="utf-8")
                manifest["candidates"].append(c)
                if r["status"] == "ELIGIBLE":
                    elegibles.append(c)
            manifest["generaciones"].append({"generacion": g, "elegibles": [c["id"] for c in elegibles]})
            if elegibles:
                ganador = max(elegibles, key=lambda c: c["score"])
                break
        manifest["estado"] = "CANDIDATO_PARA_REVISION" if ganador else "PLATEAU"
    manifest["ganador"] = ganador["id"] if ganador else None
    manifest["promocion"] = "deshabilitada: la aprobación final es visual y del usuario"
    manifest["segundos"] = round(time.time() - t0, 1)
    assert ma.sha_ok(), "Alpha cambió: no debe pasar nunca"
    manifest["alpha_sha_intacto"] = True
    (salida / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
                                          encoding="utf-8")
    bm.free()
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--brief", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--semilla", type=int, default=7)
    a = p.parse_args(argv)
    brief = json.loads(Path(a.brief).read_text(encoding="utf-8"))
    m = campana(brief, Path(a.salida), a.semilla)
    print(json.dumps({k: m[k] for k in ("estado", "ganador", "tecnicas_disponibles", "generaciones", "segundos")},
                     ensure_ascii=False, indent=2))
    for c in m["candidates"]:
        print(c["id"], c["status"], c.get("score"), " → ".join(s["tecnica"] for s in c["secuencia"]),
              c.get("reason") or "")
    return {"CANDIDATO_PARA_REVISION": 0, "PLATEAU": 2}.get(m["estado"], 9)


if __name__ == "__main__":
    sys.exit(main())
