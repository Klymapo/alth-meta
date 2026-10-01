"""Lee un issue "crear asset" (imagen adjunta + nombre + tamaño) y descarga la imagen.

    python3 tools/entrada_issue.py evento.json --destino refs/pendientes   # imprime JSON con los campos

Formato del cuerpo (lo arma la plantilla .github/ISSUE_TEMPLATE/crear-asset.yml, o a mano desde el celular):
    nombre: manzana
    tamaño: 8cm
    recorte: 0.52,0.1,1,1        (opcional, para infografías)
    ![foto](https://github.com/user-attachments/assets/…)
El título "crear: manzana, 8cm" también sirve si el cuerpo no trae nombre/tamaño.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

IMAGEN = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)|<img[^>]+src=\"(https?://[^\"]+)\"", re.I)


def _norm(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def campos(titulo: str, cuerpo: str) -> dict:
    """nombre, tamaño, recorte e imagen (URL) del issue. Acepta 'clave: valor' y las secciones '### Clave'."""
    out: dict = {}
    texto = cuerpo or ""
    # formulario de issue: "### Nombre\n\nmanzana"
    for m in re.finditer(r"^###\s*(.+?)\s*\n+(.+?)\s*$", texto, flags=re.M):
        out.setdefault(_norm(m.group(1)).strip(), m.group(2).strip())
    for m in re.finditer(r"^\s*([A-Za-zñÑáéíóú ]+?)\s*:\s*(.+?)\s*$", texto, flags=re.M):
        out.setdefault(_norm(m.group(1)).strip(), m.group(2).strip())
    res = {"nombre": out.get("nombre"), "tamano": out.get("tamano") or out.get("tamano real"),
           "recorte": out.get("recorte")}
    if res["recorte"] in ("_No response_", "", "-", "ninguno"):
        res["recorte"] = None
    if not res["nombre"] or not res["tamano"]:
        m = re.match(r"\s*crear\s*:?\s*([^,]+?)\s*(?:,\s*(.+))?$", titulo or "", flags=re.I)
        if m:
            res["nombre"] = res["nombre"] or m.group(1).strip()
            res["tamano"] = res["tamano"] or (m.group(2) or "").strip() or None
    img = IMAGEN.search(texto)
    res["imagen_url"] = (img.group(1) or img.group(2)) if img else None
    return res


def descargar(url: str, destino: Path, nombre: str, token: str | None = None) -> Path:
    h = {"User-Agent": "alth-meta-crear-asset"}
    if token and ("github.com" in url or "githubusercontent.com" in url):
        h["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        datos = r.read(25_000_000)
        tipo = r.headers.get("Content-Type", "")
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(tipo.split(";")[0], ".png")
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / (re.sub(r"[^a-z0-9_]+", "_", _norm(nombre)).strip("_") + ext)
    ruta.write_bytes(datos)
    return ruta


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("evento", help="JSON del evento de GitHub (GITHUB_EVENT_PATH)")
    p.add_argument("--destino", default="refs/pendientes")
    a = p.parse_args(argv)
    ev = json.loads(Path(a.evento).read_text(encoding="utf-8"))
    issue = ev.get("issue") or {}
    c = campos(issue.get("title", ""), issue.get("body", ""))
    faltan = [k for k in ("nombre", "tamano", "imagen_url") if not c.get(k)]
    if faltan:
        print(json.dumps({"error": f"faltan en el issue: {', '.join(faltan)}", **c}, ensure_ascii=False))
        return 2
    c["imagen"] = str(descargar(c["imagen_url"], Path(a.destino), c["nombre"], os.environ.get("GITHUB_TOKEN")))
    c["issue"] = issue.get("number")
    print(json.dumps(c, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
