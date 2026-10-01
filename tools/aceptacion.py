"""Prueba de aceptación de un objeto (bloque T5 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/aceptacion.py .linea/crear/manzana --contra assets/manzana --max-minutos 15

Criterios automáticos sobre la corrida de tools/crear_asset.py (resumen.json):
  dimensiones dadas ±2 %, tris ≤ tope, paleta, sin flotantes, apoyo Z=0 (verificación alth),
  IoU ≥ el del asset aprobado medido IGUAL (mismas vistas de su final.png contra la misma referencia,
  sin sombra) y tiempo de corrida < max-minutos.
Que el nuevo SUPERE al aprobado lo decide el usuario con la hoja lado a lado: aquí no se decide.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
CUADRANTES = {"frente": (0.0, 0.03, 0.5, 0.5), "tres_cuartos": (0.5, 0.53, 1.0, 1.0)}


def iou_de_hoja(hoja: Path, ref) -> dict:
    """IoU de las vistas de una hoja 2x2 (final.png) contra la máscara de referencia."""
    from alth import silueta
    out = {}
    im = Image.open(hoja).convert("RGB")
    w, h = im.size
    for vista, (x0, y0, x1, y1) in CUADRANTES.items():
        q = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
        tmp = RAIZ / ".linea" / f"_cuadrante_{vista}.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        q.save(tmp)
        m = silueta.mayor_mancha(silueta.mascara(silueta.cargar(tmp)))
        out[vista] = round(float(silueta.comparar(m, ref)["iou"]), 4)
    return out


def evaluar(carpeta: Path, contra: Path | None, max_minutos: float = 15.0) -> dict:
    import construir_receta as C
    carpeta = Path(carpeta)
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    receta = json.loads((carpeta / "receta.json").read_text(encoding="utf-8"))
    f = resumen["final"]
    checks = {c["check"].split(" ")[0]: c["ok"] for c in
              json.loads((Path(f["hoja"]).parent / "resultado.json").read_text(encoding="utf-8"))
              ["verificacion"].get("checks", [])}
    ref = C.mascara_referencia(receta)
    iou_aprobado = iou_de_hoja(Path(contra) / "final.png", ref) if contra else {}
    criterios = {
        "dimensiones_2pct": f["dimensiones_ok"],
        "tris": f["tris"] <= receta["tris_max"],
        "paleta": checks.get("paleta", False),
        "sin_flotantes": checks.get("flotantes", False),
        "apoyo_z0": checks.get("apoyo", False),
        "iou_vs_aprobado": (f["iou"] >= max(iou_aprobado.values())) if iou_aprobado else None,
        "tiempo": resumen["segundos"] / 60.0 < max_minutos,
    }
    return {"criterios": criterios, "automatico_ok": all(v for v in criterios.values() if v is not None),
            "iou_nuevo": f["iou"], "iou_nuevo_por_vista": f["iou_por_vista"],
            "iou_aprobado": max(iou_aprobado.values()) if iou_aprobado else None,
            "iou_aprobado_por_vista": iou_aprobado, "dif_dimensiones": f["dif_dimensiones"], "tris": f["tris"],
            "minutos": round(resumen["segundos"] / 60.0, 2),
            "decision_visual": "PENDIENTE: la decide el usuario con la hoja lado a lado (revision.png)"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta")
    ap.add_argument("--contra", default=None, help="carpeta del asset aprobado (con final.png)")
    ap.add_argument("--max-minutos", type=float, default=15.0)
    a = ap.parse_args()
    r = evaluar(Path(a.carpeta), Path(a.contra) if a.contra else None, a.max_minutos)
    (Path(a.carpeta) / "aceptacion.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    sys.exit(0 if r["automatico_ok"] else 1)
