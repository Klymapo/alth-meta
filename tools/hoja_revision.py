"""Hoja de revisión para el usuario (bloque T4): referencia | nuevo | anterior, y la hoja de 4 vistas.

    python3 tools/hoja_revision.py .linea/crear/manzana --salida revision.png

Arriba, tres paneles del mismo alto: la referencia (con su recorte), la vista de frente del asset nuevo
y la vista de frente de la versión aprobada anterior (assets/<nombre>/final.png) si existe. Abajo, la
hoja completa de 4 vistas del nuevo. Solo Pillow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[1]
FONDO = (227, 226, 233)
TEXTO = (89, 91, 102)
PANEL = 360
FRENTE = (0.0, 0.03, 0.5, 0.5)     # cuadrante de frente en la hoja 2x2 de alth.hoja_contacto


def _recortar(im: Image.Image, r) -> Image.Image:
    if not r:
        return im
    w, h = im.size
    return im.crop((int(r[0] * w), int(r[1] * h), int(r[2] * w), int(r[3] * h)))


def _panel(im: Image.Image | None, titulo: str, fuente) -> Image.Image:
    p = Image.new("RGB", (PANEL, PANEL + 28), FONDO)
    d = ImageDraw.Draw(p)
    d.text((8, 6), titulo, fill=TEXTO, font=fuente)
    if im is None:
        d.text((PANEL // 2 - 60, PANEL // 2), "(no hay versión anterior)", fill=TEXTO, font=fuente)
        return p
    im = im.convert("RGB")
    im.thumbnail((PANEL - 16, PANEL - 16))
    p.paste(im, ((PANEL - im.width) // 2, 28 + (PANEL - im.height) // 2))
    return p


def _fuente(tam=16):
    for f in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            pass
    return ImageFont.load_default()


def componer(carpeta: Path, salida: Path, raiz: Path = RAIZ) -> Path:
    carpeta = Path(carpeta)
    receta = json.loads((carpeta / "receta.json").read_text(encoding="utf-8"))
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    hoja = Path(resumen["final"]["hoja"])
    hoja = hoja if hoja.is_absolute() else raiz / hoja
    ref = _recortar(Image.open(raiz / receta["origen"]["imagen"]), receta["origen"].get("recorte"))
    nuevo = _recortar(Image.open(hoja), FRENTE)
    previo_ruta = raiz / "assets" / receta["nombre"] / "final.png"
    previo = _recortar(Image.open(previo_ruta), FRENTE) if previo_ruta.exists() else None
    f = _fuente()
    fila = [_panel(ref, "referencia", f), _panel(nuevo, f"nuevo · IoU {resumen['final']['iou']}", f),
            _panel(previo, "aprobado anterior", f)]
    completa = Image.open(hoja).convert("RGB")
    ancho = PANEL * 3
    completa = completa.resize((ancho, int(completa.height * ancho / completa.width)))
    out = Image.new("RGB", (ancho, fila[0].height + completa.height), FONDO)
    for i, p in enumerate(fila):
        out.paste(p, (i * PANEL, 0))
    out.paste(completa, (0, fila[0].height))
    salida = Path(salida)
    out.save(salida)
    return salida


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    print(componer(Path(a.carpeta), Path(a.salida)))
