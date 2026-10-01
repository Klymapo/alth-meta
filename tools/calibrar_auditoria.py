"""ALTH-META · calibra los umbrales de la auditoría visual con veredictos reales (aprobado / rechazado).

Los umbrales de spec/auditoria_visual.json nacen provisionales. Este script los recalcula con pares
etiquetados en kb/pares_auditoria.json:

  {"pares": [{"id": "manzana-ok", "ref": "refs/...png", "recorte": [0.52, 0.1, 1, 1],
              "hoja": "assets/manzana/final.png", "veredicto": "aprobado", "fuente": "dueño 2026-10-01"}]}

Por cada medida que veta busca el umbral que separa mejor (estadístico J de Youden = sensibilidad +
especificidad − 1) y, si hay empate, el que deja más margen hasta el positivo más cercano. Una medida
que no separa (J bajo) se reporta: no se inventa un umbral que la haga parecer útil.

`calibrado: true` sólo si hay al menos MIN_POSITIVOS aprobados y MIN_NEGATIVOS rechazados; si no, los
umbrales se escriben igual pero siguen marcados como provisionales.

  python3 tools/calibrar_auditoria.py                      # reporte, no escribe
  python3 tools/calibrar_auditoria.py --escribir           # actualiza spec/auditoria_visual.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditoria_visual as A  # noqa: E402
import mascaras  # noqa: E402

PARES_RUTA = RAIZ / "kb" / "pares_auditoria.json"
MIN_POSITIVOS, MIN_NEGATIVOS = 10, 10
J_MINIMO = 0.5          # por debajo, la medida casi no separa: se avisa
# sentido de cada medida: "min" = más alto es mejor; "max" = más bajo es mejor
SENTIDO = {"silueta_iou": "min"}


def medir_par(par: dict, raiz: Path = RAIZ) -> dict:
    """Medidas del par en la vista que la auditoría elegiría (sin depender de los umbrales)."""
    ref_rgb, ref_m, _ = mascaras.cargar_con_mascara(raiz / par["ref"], tuple(par["recorte"]) if par.get("recorte") else None)
    if par.get("hoja"):
        vistas = A.vistas_de_hoja(raiz / par["hoja"])
    else:
        vistas = {v: mascaras.cargar_con_mascara(raiz / r) for v, r in par["render"].items()}
    neutro = {"umbrales": {}, "calibrado": False}
    r = A.auditar(ref_rgb, ref_m, vistas, neutro, par.get("vista"))
    return r["medidas"]


def umbral_optimo(pos: list[float], neg: list[float], sentido: str) -> dict:
    """Umbral con mejor J de Youden. Para 'max' pasa v <= u; para 'min' pasa v >= u."""
    s = 1.0 if sentido == "max" else -1.0          # se trabaja como 'max' cambiando el signo
    p, n = np.array(pos) * s, np.array(neg) * s
    candidatos = np.unique(np.concatenate([p, n]))
    # puntos medios entre valores consecutivos, más los extremos
    cortes = np.concatenate([[candidatos[0] - 1e-9], (candidatos[:-1] + candidatos[1:]) / 2, [candidatos[-1] + 1e-9]])
    mejor = None
    for u in cortes:
        sens = float((p <= u).mean()) if len(p) else 0.0
        esp = float((n > u).mean()) if len(n) else 0.0
        j = sens + esp - 1
        margen = float(u - p[p <= u].max()) if (p <= u).any() else -np.inf
        clave = (round(j, 9), margen)
        if mejor is None or clave > mejor[0]:
            mejor = (clave, u, sens, esp)
    (_, _), u, sens, esp = mejor
    # entre el peor positivo aceptado y el mejor negativo rechazado, el punto medio exacto
    aceptados = p[p <= u]
    rechazados = n[n > u]
    if len(aceptados) and len(rechazados):
        u = (aceptados.max() + rechazados.min()) / 2
    return {"umbral": round(float(u * s), 4), "sensibilidad": round(sens, 3), "especificidad": round(esp, 3),
            "j": round(sens + esp - 1, 3), "separa": bool(sens == 1.0 and esp == 1.0)}


def calibrar(pares: list[dict], raiz: Path = RAIZ) -> dict:
    medidas = []
    for par in pares:
        if par.get("veredicto") not in ("aprobado", "rechazado"):
            raise ValueError(f"par {par.get('id')}: veredicto debe ser 'aprobado' o 'rechazado'")
        medidas.append((par, medir_par(par, raiz)))
    pos = [m for p, m in medidas if p["veredicto"] == "aprobado"]
    neg = [m for p, m in medidas if p["veredicto"] == "rechazado"]
    res = {}
    for k in A.VETO:
        vp = [m[k] for m in pos if m.get(k) is not None]
        vn = [m[k] for m in neg if m.get(k) is not None]
        if not vp or not vn:
            res[k] = {"umbral": None, "aviso": "sin pares de las dos clases para esta medida"}
            continue
        res[k] = umbral_optimo(vp, vn, SENTIDO.get(k, "max"))
        if res[k]["j"] < J_MINIMO:
            res[k]["aviso"] = f"J={res[k]['j']} < {J_MINIMO}: esta medida casi no separa con estos pares"
    # conjunto: ¿la regla 'un FAIL veta' con estos umbrales clasifica bien cada par?
    errores = []
    for par, m in medidas:
        pasa = all(m.get(k) is None or res[k].get("umbral") is None or
                   (m[k] >= res[k]["umbral"] if SENTIDO.get(k, "max") == "min" else m[k] <= res[k]["umbral"])
                   for k in A.VETO)
        if pasa != (par["veredicto"] == "aprobado"):
            errores.append({"id": par.get("id"), "veredicto": par["veredicto"], "auditoria": "PASS" if pasa else "FAIL"})
    return {"positivos": len(pos), "negativos": len(neg), "por_medida": res, "errores_conjunto": errores,
            "suficiente": len(pos) >= MIN_POSITIVOS and len(neg) >= MIN_NEGATIVOS,
            "medidas_por_par": [{"id": p.get("id"), "veredicto": p["veredicto"],
                                 **{k: m.get(k) for k in A.VETO}} for p, m in medidas]}


def escribir(cal: dict, ruta: Path = A.UMBRALES_RUTA) -> dict:
    spec = json.loads(ruta.read_text(encoding="utf-8"))
    for k, r in cal["por_medida"].items():
        if r.get("umbral") is None:
            continue
        lado = "min" if SENTIDO.get(k, "max") == "min" else "max"
        spec["umbrales"][k] = {lado: r["umbral"],
                               "por_que": f"calibrado {date.today().isoformat()}: J={r['j']}, "
                                          f"sens={r['sensibilidad']}, esp={r['especificidad']}"
                                          f" con {cal['positivos']}+/{cal['negativos']}-"}
    spec["calibrado"] = bool(cal["suficiente"] and not cal["errores_conjunto"])
    spec["nota"] = (f"Calibrado con tools/calibrar_auditoria.py el {date.today().isoformat()} con "
                    f"{cal['positivos']} aprobados y {cal['negativos']} rechazados"
                    + ("." if spec["calibrado"] else
                       f"; sigue PROVISIONAL (mínimo {MIN_POSITIVOS}+/{MIN_NEGATIVOS}- y cero errores del conjunto)."))
    ruta.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return spec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pares", default=str(PARES_RUTA))
    ap.add_argument("--escribir", action="store_true", help="actualiza spec/auditoria_visual.json")
    a = ap.parse_args(argv)
    pares = json.loads(Path(a.pares).read_text(encoding="utf-8"))["pares"]
    cal = calibrar(pares)
    for k, r in cal["por_medida"].items():
        print(f"  {k:18} umbral={r.get('umbral')}  J={r.get('j')}  {r.get('aviso', '')}")
    print(f"  pares: {cal['positivos']} aprobados, {cal['negativos']} rechazados · "
          f"errores del conjunto: {len(cal['errores_conjunto'])} · suficiente: {cal['suficiente']}")
    if a.escribir:
        spec = escribir(cal)
        print(f"  escrito spec/auditoria_visual.json · calibrado={spec['calibrado']}")
    return 0 if not cal["errores_conjunto"] else 1


if __name__ == "__main__":
    sys.exit(main())
