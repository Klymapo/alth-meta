"""Pruebas de la lógica de verificación (no necesitan Blender): python3 -m pytest tests/"""
import copy
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "alth"))
import verificacion as v  # noqa: E402

SPEC = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))
ASSET = {"categoria": "de_mano",
         "cotas": [{"pieza": "cuerpo", "eje": "H", "mm": 8.05}, {"pieza": "cuerpo", "eje": "W", "mm": 8.94}]}
BIEN = {"piezas": {
    "cuerpo": {"W": 8.92, "D": 8.64, "H": 8.05, "z_min": 0.0, "tris": 160, "colores": ["#A8453B"], "toca": ["tallo"]},
    "tallo": {"W": 1.5, "D": 1.5, "H": 3.2, "z_min": 5.6, "tris": 20, "colores": ["#69472D"], "toca": ["cuerpo", "hoja"]},
    "hoja": {"W": 3.9, "D": 2.5, "H": 3.9, "z_min": 7.0, "tris": 48, "colores": ["#7E9B7A"], "toca": ["tallo"]},
}}


def fallas(datos, asset=ASSET):
    return {c["check"] for c in v.evaluar(datos, SPEC, asset)["checks"] if not c["ok"]}


def test_manzana_aprobada_pasa():
    assert v.evaluar(BIEN, SPEC, ASSET)["ok"]


def test_manzana_v4_detecta_alto_corto():
    d = copy.deepcopy(BIEN)
    d["piezas"]["cuerpo"]["H"] = 7.69  # lo que medía la v4
    assert fallas(d) == {"cota cuerpo.H"}


def test_pieza_flotante_por_cadena():
    d = copy.deepcopy(BIEN)
    d["piezas"]["tallo"]["toca"] = ["cuerpo"]
    d["piezas"]["hoja"]["toca"] = []
    assert fallas(d) == {"flotantes"}


def test_color_fuera_de_paleta_y_tope():
    d = copy.deepcopy(BIEN)
    d["piezas"]["hoja"]["colores"] = ["#123456"]
    d["piezas"]["cuerpo"]["tris"] = 999
    assert fallas(d) == {"paleta", "triangulos"}


def test_hundido_bajo_el_piso():
    d = copy.deepcopy(BIEN)
    d["piezas"]["cuerpo"]["z_min"] = -0.3
    assert "apoyo" in fallas(d)


def test_sin_cotas_avisa():
    assert fallas(BIEN, {"categoria": "de_mano"}) == {"cotas"}
