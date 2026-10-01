"""Revisión y publicación (T4), sin Blender: filas de medidas, hoja de revisión y memoria de 4 vistas.

    python3 -m pytest tests/test_publicar.py
"""
import csv
import json
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import hoja_revision as hr  # noqa: E402
import publicar as pub  # noqa: E402
import reconocer as rec  # noqa: E402

RECETA = {"nombre": "manzana", "categoria": "de_mano", "k": 2.0,
          "medidas_mm": {"ancho": 8.51, "alto": 9.62, "dadas": ["ancho"]},
          "origen": {"imagen": "refs/infografias/objeto-01-manzana.png", "recorte": [0.52, 0.1, 1.0, 1.0]}}


def test_filas_medidas_solo_lo_que_dio_el_usuario():
    f = pub.filas_medidas(RECETA, {"ancho": 8.525, "alto": 9.358}, 0.05316, "2026-10-01")
    assert len(f) == 1 and f[0]["medida"] == "ancho" and f[0]["real_mm"] == "80"
    assert f[0]["alth_mm"] == "8.53" and f[0]["k_observado"] == "2.00" and f[0]["aprobado"] == "si"


def test_reemplazar_filas_no_duplica(tmp_path):
    ruta = tmp_path / "m.csv"
    ruta.write_text((RAIZ / "data" / "medidas.csv").read_text(encoding="utf-8"), encoding="utf-8")
    nuevas = pub.filas_medidas(RECETA, {"ancho": 8.525}, 0.05316, "2026-10-01")
    pub.reemplazar_filas("manzana", nuevas, ruta)
    pub.reemplazar_filas("manzana", nuevas, ruta)
    filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    assert [f["medida"] for f in filas if f["asset"] == "manzana"] == ["ancho"]
    assert len([f for f in filas if f["asset"] == "lata"]) == 2           # lo demás no se toca


def test_hoja_revision(tmp_path):
    (tmp_path / "receta.json").write_text(json.dumps(RECETA), encoding="utf-8")
    hoja = RAIZ / "assets" / "taza" / "final.png"                          # cualquier hoja 2x2 sirve
    (tmp_path / "resumen.json").write_text(json.dumps({"final": {"hoja": str(hoja), "iou": 0.88}}), encoding="utf-8")
    out = hr.componer(tmp_path, tmp_path / "revision.png")
    im = Image.open(out)
    assert im.width == 3 * hr.PANEL and im.height > hr.PANEL


def test_memoria_de_cuatro_vistas():
    memoria = rec.cargar_huellas()
    for h in memoria["huellas"]:
        assert set(h["vistas"]) == {"frente", "lateral", "espalda", "tres_cuartos"}, h["asset"]
        assert h["vistas"]["frente"]["forma"] == h["forma"]
    # la lateral de la taza (asa de perfil) se reconoce por su propia vista
    f = rec.reconocer(RAIZ / "assets/taza/final.png", "algo", None, None, rec.VISTAS_HOJA["lateral"], huellas=memoria)
    assert f["parecidos"][0]["nombre"] == "taza" and f["parecidos"][0]["vista"] == "lateral"
