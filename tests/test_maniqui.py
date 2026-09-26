"""Pruebas del plan del maniquí (sin Blender)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "alth"))
import cuerpo as m  # noqa: E402


def test_alturas_por_arquetipo():
    esperado = {"menuda": 88, "media": 90, "estandar": 95, "alta": 100}
    for arq, h in esperado.items():
        assert abs(m.plan(arq)["anclas"]["altura"] - h) < 1e-6


def test_anclas_estandar_coinciden_con_el_pdf():
    a = m.plan("estandar")["anclas"]
    assert a["rodilla"] == 21.0 and a["cadera"] == 33.0 and a["cuello"] == 60.5


def test_la_cabeza_no_cambia_entre_arquetipos():
    cab = lambda arq: next(p for p in m.plan(arq)["piezas"] if p["nombre"] == "cabeza")["tam"]
    assert cab("menuda") == cab("alta") == (40.0, 29.8, 34.5)


def test_zapato_puntera_y_talon():
    z = next(p for p in m.plan()["piezas"] if p["nombre"] == "zapato_der")
    y_centro, largo = z["pos"][1], z["tam"][1]
    assert abs((y_centro - largo / 2) + 13.2) < 1e-6 and abs((y_centro + largo / 2) - 4.8) < 1e-6
