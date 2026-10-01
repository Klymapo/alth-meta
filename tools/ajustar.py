"""Ajuste numérico de la receta contra la silueta de la referencia (bloque T3 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/ajustar.py receta.json --salida .linea/ajuste/manzana

Torneo con las reglas de COPOX (docs/COPOX_LOOP_ENGINE.md), sin IA y sin respaldo de IA:
  - cada ronda genera CANDIDATOS HERMANOS desde la misma baseline, variando parámetros de
    `receta.ajustables` (más una corrección de escala en forma cerrada si las medidas no cuadran);
  - auditores aplicables por candidato: dimensiones (±2 %), verificación alth (cotas, tris, paleta,
    flotantes, apoyo), tope de triángulos y no-regresión de IoU. 100 % PASS o queda RECHAZADO;
    el puntaje (IoU) nunca compensa un FAIL;
  - gana el de mayor IoU entre los unánimes y pasa a ser la baseline; los rechazados nunca son padres;
  - una ronda sin ganador no corta: la siguiente prueba otros hermanos desde la misma baseline;
  - máximo 3 rondas. Si al final no hay un resultado unánime: PLATEAU, se conserva la baseline y se reporta.
Escribe <salida>/manifest.json con la forma del manifest de copox/engine.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import receta as R  # noqa: E402

MAX_RONDAS = 3
HERMANOS = 3
TOL_IOU = 0.01        # no-regresión: un candidato no puede perder más de 1 pp de IoU
MEJORA_MIN = 0.002    # si la baseline ya es unánime, el ganador debe mejorarla al menos esto


# ---------------------------------------------------------------- lógica pura
def auditar(res: dict, iou_base: float | None) -> list[dict]:
    """Auditores del candidato (PASS/FAIL). Ninguno es N-A en esta campaña."""
    a = [{"id": "dimensiones", "status": "PASS" if res["dimensiones_ok"] else "FAIL", "detalle": res["dif_dimensiones"]},
         {"id": "verificacion_alth", "status": "PASS" if res["verificacion_ok"] else "FAIL",
          "detalle": [c["detalle"] for c in res.get("verificacion", {}).get("checks", []) if not c["ok"]]},
         {"id": "tris", "status": "PASS" if res["tris"] <= res["tris_max"] else "FAIL",
          "detalle": f"{res['tris']} de {res['tris_max']}"}]
    if iou_base is not None:
        a.append({"id": "regresion_iou", "status": "PASS" if res["iou"] >= iou_base - TOL_IOU else "FAIL",
                  "detalle": f"{res['iou']} vs baseline {iou_base}", "score": res["iou"]})
    return a


def unanime(auditoria: list[dict]) -> bool:
    aplicables = [x for x in auditoria if x["status"] != "N-A"]
    return bool(aplicables) and all(x["status"] == "PASS" for x in aplicables)


def movimientos(receta: dict) -> list[tuple[str, float]]:
    """Todas las variaciones de un paso (ruta, valor nuevo) dentro de los límites de cada ajustable."""
    out = []
    for a in receta["ajustables"]:
        v = R.obtener(receta, a["ruta"])
        paso = a.get("paso") or (a["max"] - a["min"]) / 4
        for s in (+1, -1):
            nuevo = round(min(a["max"], max(a["min"], v + s * paso)), 6)
            if nuevo != v:
                out.append((a["ruta"], nuevo))
    return out


def correccion_escala(receta: dict, res: dict) -> list[tuple[str, float]]:
    """Corrección en forma cerrada: si el ancho del cuerpo no cuadra, escala_r ← escala_r × pedido / medido."""
    ruta = "piezas.0.params.escala_r"
    d = (res.get("dif_cuerpo") or {}).get("W", res["dif_dimensiones"].get("ancho"))
    if d is None or abs(d) <= 0.005:
        return []
    try:
        v = R.obtener(receta, ruta)
    except (KeyError, IndexError):
        return []
    return [(ruta, round(v / (1 + d), 4))]


def hermanos(receta: dict, res_base: dict, ronda: int, n: int = HERMANOS) -> list[list[tuple[str, float]]]:
    """Cambios de cada hermano (todos parten de la misma baseline). Determinista: misma entrada, mismos hermanos."""
    corr = correccion_escala(receta, res_base)
    rutas_corr = {r for r, _ in corr}
    movs = [m for m in movimientos(receta) if m[0] not in rutas_corr]
    cands: list[list[tuple[str, float]]] = []
    if corr and ronda == 1:
        cands.append(corr)
    i = (ronda - 1) * n
    while len(cands) < n and movs and i < (ronda - 1) * n + 2 * len(movs):
        c = corr + [movs[i % len(movs)]]          # cada movimiento va con la corrección de escala
        if c not in cands:
            cands.append(c)
        i += 1
    return cands[:n]


def aplicar(receta: dict, cambios: list[tuple[str, float]]) -> dict:
    for ruta, v in cambios:
        receta = R.fijar(receta, ruta, v)
    return receta


def elegir(base_res: dict, base_unanime: bool, candidatos: list[dict]) -> dict | None:
    elegibles = [c for c in candidatos if c["status"] == "ELIGIBLE"]
    if not elegibles:
        return None
    mejor = max(elegibles, key=lambda c: c["score"])
    if base_unanime and mejor["score"] < base_res["iou"] + MEJORA_MIN:
        return None
    return mejor


# ---------------------------------------------------------------- torneo (Blender)
def ajustar(receta: dict, salida: Path, ref=None, base: dict | None = None, plazo: float | None = None,
            max_rondas: int = MAX_RONDAS, construir=None) -> dict:
    """Devuelve {estado, rondas, iou_base, iou_final, ganador, receta, resultado}."""
    if construir is None:
        import construir_receta as C
        ref = C.mascara_referencia(receta) if ref is None else ref

        def construir(rc, carpeta):
            return C.construir(rc, carpeta, ref=ref)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    base_res = base or construir(receta, salida / "baseline")
    base_aud = auditar(base_res, None)
    base_un = unanime(base_aud)
    manifest = {"engine": "copox-loop-engine", "version": "0.3.0", "cassette": "alth-receta-ajuste",
                "kind": "parametric", "run_id": f"ajuste-{receta['nombre']}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}",
                "baseline": {"iou": base_res["iou"], "unanime": base_un, "auditoria": base_aud},
                "started_at": int(t0), "status": "RUNNING", "candidates": [], "rondas": []}
    actual, actual_res, iou_inicial = receta, base_res, base_res["iou"]
    estado, rondas = "AJUSTADO", 0
    for ronda in range(1, max_rondas + 1):
        if plazo is not None and time.time() > plazo - 60:
            estado = "SIN_TIEMPO"
            break
        rondas = ronda
        cands = []
        for k, cambios in enumerate(hermanos(actual, actual_res, ronda), 1):
            cid = f"t{ronda:02d}-c{k:02d}"
            rc = aplicar(actual, cambios)
            rec = {"id": cid, "tournament": ronda, "padre": "baseline", "cambios": cambios}
            try:
                res = construir(rc, salida / cid)
                aud = auditar(res, actual_res["iou"])
                rec.update(audit=aud, score=res["iou"], status="ELIGIBLE" if unanime(aud) else "REJECTED",
                           hoja=res["hoja"])
                if rec["status"] == "REJECTED":
                    rec["reason"] = "auditor_veto: " + ", ".join(x["id"] for x in aud if x["status"] == "FAIL")
                rec["_receta"], rec["_res"] = rc, res
            except Exception as e:  # noqa: BLE001 — un candidato que truena queda rechazado
                rec.update(status="ERROR", reason=repr(e)[:300], score=0.0)
            cands.append(rec)
        ganador = elegir(actual_res, unanime(auditar(actual_res, None)), cands)
        manifest["candidates"] += [{k: v for k, v in c.items() if not k.startswith("_")} for c in cands]
        manifest["rondas"].append({"ronda": ronda, "ganador": ganador["id"] if ganador else None,
                                   "iou_baseline": actual_res["iou"]})
        if not ganador:
            continue                               # mismos padres, otros hermanos en la siguiente ronda
        actual, actual_res = ganador["_receta"], ganador["_res"]
        manifest["winner"] = ganador["id"]
    final_un = unanime(auditar(actual_res, None))
    if estado == "AJUSTADO" and not final_un:
        estado = "PLATEAU"
    manifest.update(status="PROMOTED" if manifest.get("winner") else "PLATEAU", estado=estado,
                    finished_at=int(time.time()), iou_final=actual_res["iou"], final_unanime=final_un)
    (salida / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
                                          encoding="utf-8")
    return {"estado": estado, "rondas": rondas, "iou_base": iou_inicial, "iou_final": actual_res["iou"],
            "ganador": manifest.get("winner"), "receta": actual if manifest.get("winner") else None,
            "resultado": actual_res, "manifest": str(salida / "manifest.json"), "segundos": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("receta")
    p.add_argument("--salida", required=True)
    p.add_argument("--rondas", type=int, default=MAX_RONDAS)
    a = p.parse_args(argv)
    receta = json.loads(Path(a.receta).read_text(encoding="utf-8"))
    r = ajustar(receta, Path(a.salida), max_rondas=min(a.rondas, MAX_RONDAS))
    if r["receta"]:
        (Path(a.salida) / "receta_ajustada.json").write_text(json.dumps(r["receta"], ensure_ascii=False, indent=2)
                                                             + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if k not in ("receta", "resultado")}, ensure_ascii=False, indent=2))
    return 0 if r["estado"] == "AJUSTADO" else 2


if __name__ == "__main__":
    sys.exit(main())
