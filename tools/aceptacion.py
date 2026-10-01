"""Prueba de aceptación de un objeto (bloque T5 de docs/BRIEF_LINEA_UNICA.md).

    python3 tools/aceptacion.py .linea/crear/manzana --contra assets/manzana --max-minutos 15

Criterios sobre la corrida de tools/crear_asset.py (resumen.json):
  dimensiones dadas ±2 %, tris ≤ tope, paleta, sin flotantes, apoyo Z=0 (verificación alth),
  AUDITORÍA VISUAL PASS contra la referencia (tools/auditoria_visual.py, la que decide), no quedar peor
  que el asset aprobado medido IGUAL (mismo encuadre y mismas medidas) y tiempo de corrida < max-minutos.
Si la corrida no trae auditoría (corridas viejas), se audita aquí. Sin Blender: sólo numpy/scipy/Pillow.
Código de salida: 0 = aceptado, 1 = no.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))


def auditoria_de(carpeta: Path, resumen: dict, contra: Path | None) -> dict:
    """La auditoría de la corrida; si falta, o si hay que comparar contra otro aprobado, se rehace."""
    import auditoria_visual as AV
    au = resumen.get("auditoria")
    aprobado = Path(contra) / "final.png" if contra else None
    if au and au.get("decision") and (aprobado is None or au.get("aprobado")):
        return au
    rec = resumen.get("recorte")
    try:
        r = AV.auditar_archivos(resumen["imagen"], Path(carpeta) / "auditoria_aceptacion",
                                tuple(rec) if rec else None, hoja=resumen["final"]["hoja"],
                                aprobado=aprobado if aprobado and aprobado.exists() else None)
    except (ValueError, OSError, KeyError) as e:
        return {"decision": "FAIL", "fallas": ["entrada"], "error": str(e)}
    return r


def evaluar(carpeta: Path, contra: Path | None, max_minutos: float = 15.0) -> dict:
    carpeta = Path(carpeta)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    receta = json.loads((carpeta / "receta.json").read_text(encoding="utf-8"))
    f = resumen["final"]
    checks = {c["check"].split(" ")[0]: c["ok"] for c in
              json.loads((Path(f["hoja"]).parent / "resultado.json").read_text(encoding="utf-8"))
              ["verificacion"].get("checks", [])}
    au = auditoria_de(carpeta, resumen, contra)
    criterios = {
        "dimensiones_2pct": f["dimensiones_ok"],
        "tris": f["tris"] <= receta["tris_max"],
        "paleta": checks.get("paleta", False),
        "sin_flotantes": checks.get("flotantes", False),
        "apoyo_z0": checks.get("apoyo", False),
        "auditoria_visual": au.get("decision") == "PASS",
        "no_peor_que_aprobado": au.get("no_peor_que_aprobado") if contra else None,
        "tiempo": resumen["segundos"] / 60.0 < max_minutos,
    }
    return {"criterios": criterios, "aceptado": all(v for v in criterios.values() if v is not None),
            "auditoria": {k: au.get(k) for k in ("decision", "fallas", "vista", "supera_aprobado", "calibrado",
                                                 "error")},
            "dif_dimensiones": f["dif_dimensiones"], "tris": f["tris"],
            "minutos": round(resumen["segundos"] / 60.0, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta")
    ap.add_argument("--contra", default=None, help="carpeta del asset aprobado (con final.png)")
    ap.add_argument("--max-minutos", type=float, default=15.0)
    a = ap.parse_args()
    r = evaluar(Path(a.carpeta), Path(a.contra) if a.contra else None, a.max_minutos)
    (Path(a.carpeta) / "aceptacion.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["aceptado"] else 1)
