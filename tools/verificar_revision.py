"""Comprueba que la hoja revisada corresponde exactamente a los archivos de la rama."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("ALTH_REPO", Path(__file__).resolve().parents[1])).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verificar(asset: str) -> dict:
    carpeta = (ROOT / asset).resolve()
    if not carpeta.is_relative_to(ROOT / "assets") or not carpeta.is_dir():
        raise ValueError("Asset fuera de assets/")
    revision = carpeta / "bucle" / "revision.json"
    datos = json.loads(revision.read_text(encoding="utf-8"))
    if datos.get("asset") != carpeta.relative_to(ROOT).as_posix():
        raise ValueError("La revisión pertenece a otro asset")
    if not datos.get("verificacion_ok"):
        raise ValueError("La verificación del modelo no pasó")
    for ruta, esperado in datos["archivos_sha256"].items():
        archivo = (ROOT / ruta).resolve()
        if not archivo.is_relative_to(ROOT) or not archivo.is_file() or sha(archivo) != esperado:
            raise ValueError(f"Cambió el archivo revisado: {ruta}")
    for nombre, clave in (("hoja_ultima.png", "hoja_sha256"),
                          ("reporte_revision.json", "reporte_sha256")):
        archivo = carpeta / "bucle" / nombre
        if not archivo.is_file() or sha(archivo) != datos[clave]:
            raise ValueError(f"Cambió la evidencia revisada: {nombre}")
    return datos


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", help="Ruta desde la raíz, p. ej. assets/manzana")
    args = parser.parse_args()
    print(json.dumps(verificar(args.asset), ensure_ascii=False, indent=2))
