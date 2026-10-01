"""Publica un asset APROBADO por el usuario (bloque T4 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/publicar.py .linea/crear/manzana --issue 12

Solo se llama cuando el usuario pone la etiqueta `aprobado` en el issue (workflow aprobar-linea.yml).
Sin aprobación no se publica nada. A partir de la receta revisada:
  1. reconstruye en modo FINAL y exporta a assets/<nombre>/: .blend, .glb (raíz ×0.01, Y-up),
     final.png (hoja de 4 vistas) y spec.json (conserva el historial de la versión anterior);
  2. reemplaza las filas del asset en data/medidas.csv con lo medido (aprobado=si);
  3. aprende: capacidades usadas → `dominada` con assets/<nombre>/final.png como evidencia;
  4. memoriza la huella de las 4 vistas (kb/huellas.json).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
MEDIDAS_CSV = RAIZ / "data" / "medidas.csv"


def filas_medidas(receta: dict, dims_mm: dict, s0: float, fecha: str) -> list[dict]:
    """Filas de data/medidas.csv para las medidas que dio el usuario (las demás se derivan de la foto)."""
    k = receta["k"]
    out = []
    for d in receta["medidas_mm"].get("dadas") or ["ancho"]:
        if d not in dims_mm or not receta["medidas_mm"].get(d):
            continue
        real = receta["medidas_mm"][d] / (s0 * k)
        out.append({"asset": receta["nombre"], "categoria": receta["categoria"], "medida": d,
                    "real_mm": f"{real:.0f}", "alth_mm": f"{dims_mm[d]:.2f}",
                    "k_observado": f"{dims_mm[d] / (real * s0):.2f}", "aprobado": "si", "fecha": fecha})
    return out


def reemplazar_filas(nombre: str, nuevas: list[dict], ruta: Path = MEDIDAS_CSV) -> None:
    with ruta.open(encoding="utf-8", newline="") as fh:
        lector = csv.DictReader(fh)
        campos, filas = lector.fieldnames, [f for f in lector if f["asset"] != nombre]
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        w.writerows(filas + nuevas)


def publicar(carpeta: Path, issue: int | None = None, fecha: str | None = None) -> dict:
    import capacidades as cap
    import construir_receta as C
    import reconocer as rec
    import redimensionar as rd

    carpeta = Path(carpeta)
    fecha = fecha or date.today().isoformat()
    receta = json.loads((carpeta / "receta.json").read_text(encoding="utf-8"))
    destino = RAIZ / "assets" / receta["nombre"]
    previo = json.loads((destino / "spec.json").read_text(encoding="utf-8")) if (destino / "spec.json").exists() else {}
    res = C.construir(receta, carpeta / "final", modo="final", exportar=destino)
    if not res["ok"]:
        raise RuntimeError(f"la versión final no pasa la verificación: {res['dif_dimensiones']}, "
                           f"verificación {res['verificacion_ok']}")
    shutil.copyfile(res["hoja"], destino / "final.png")
    spec = json.loads((destino / "spec.json").read_text(encoding="utf-8"))
    spec["historial"] = previo.get("historial", []) + [
        {"vuelta": "línea única", "nota": f"receta por código, IoU {res['iou']}, aprobada por el usuario"
                                          + (f" en el issue #{issue}" if issue else ""), "fecha": fecha}]
    spec["escala"] = {"version": "v2.0", "s0": json.loads((RAIZ / "spec" / "alth_spec.json").read_text())
                      ["escala_alpha"]["s0"]}
    (destino / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    glb = rd.revisar_glb(destino / f"{receta['nombre']}.glb", 0.01)
    if not glb["ok"]:
        raise RuntimeError(f"GLB mal exportado: {glb}")
    s0 = spec["escala"]["s0"]
    reemplazar_filas(receta["nombre"], filas_medidas(receta, res["dimensiones_mm"], s0, fecha))
    evidencia = str((destino / "final.png").relative_to(RAIZ))
    vocab = rec.cargar_vocab()
    registro = cap.cargar_registro()
    aprendidas = []
    for c in receta["origen"].get("capacidades", []):
        if c in vocab["capacidades"]:
            cap.aprender(registro, c, "dominada", f"usada en {receta['nombre']} aprobado"
                         + (f" (issue #{issue})" if issue else ""), [evidencia], vocab=vocab)
            aprendidas.append(c)
    cap.guardar_registro(registro)
    rec.memorizar(destino)
    return {"asset": str(destino.relative_to(RAIZ)), "glb": glb, "iou": res["iou"],
            "dimensiones_mm": res["dimensiones_mm"], "capacidades_aprendidas": aprendidas, "memorizado": True}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("carpeta", help="carpeta de la corrida revisada (receta.json)")
    p.add_argument("--issue", type=int, default=None)
    a = p.parse_args(argv)
    print(json.dumps(publicar(Path(a.carpeta), a.issue), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
