"""T6 sin Blender: marco de la mano, muestreo determinista y criterios de la reducción.

    python3 -m pytest tests/test_campana_dedos.py
"""
import random
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import campana_dedos as cd  # noqa: E402
import reducir_sam as rs  # noqa: E402

TEC = {"name": "bmesh.ops.bisect_plane", "params_doc": ["geom", "dist", "plane_co", "plane_no", "clear_inner"],
       "tipos": {"geom": "elementos", "dist": "float", "plane_co": "vector", "plane_no": "vector",
                 "clear_inner": "bool"}, "parametros": {"clear_inner": False}}


def test_marco_de_la_mano_ordena_ejes_por_tamano():
    rng = np.random.default_rng(0)
    pts = rng.normal(size=(500, 3)) * [10, 4, 1] + [40, 0, 44]
    mf = cd.marco(pts)
    assert mf["L"][0] > mf["L"][1] > mf["L"][2]
    assert abs(abs(mf["ejes"][0][0]) - 1) < 0.05            # el largo va sobre X, como la mano en pose T


def test_muestreo_determinista_y_respeta_literales():
    mf = cd.marco(np.random.default_rng(1).normal(size=(100, 3)))
    a = cd.muestrear_params(TEC, mf, random.Random(3))
    assert a == cd.muestrear_params(TEC, mf, random.Random(3))
    assert a["clear_inner"] is False                          # literal del ejemplo publicado
    assert "region" in a["geom"] and "frac_largo" in a["dist"] and "punto" in a["plane_co"] and "eje" in a["plane_no"]


def test_tipos_por_nombre_sin_tabla():
    assert cd._tipo("use_snap_center", {}) == "bool" and cd._tipo("faces", {}) == "elementos"
    assert cd._tipo("use_verts", {}) == "bool"                 # bool aunque termine en _verts
    assert cd._tipo("plane_no", {}) == "vector" and cd._tipo("cuts", {}) == "int" and cd._tipo("dist", {}) == "float"


def test_reduccion_acepta_solo_sin_violaciones():
    base = {"no_manifold": 0, "degeneradas": 0, "aristas_sueltas": 0, "borde": 10}
    m = {"iou_min": 0.98, "volumen_rel": -0.01, "protegido_intacto": True,
         "integridad": {"no_manifold": 0, "degeneradas": 0, "aristas_sueltas": 0, "borde": 10}}
    assert rs.aceptable(m, base)[0]
    for cambio in ({"iou_min": 0.9}, {"volumen_rel": 0.05}, {"protegido_intacto": False}):
        assert not rs.aceptable({**m, **cambio}, base)[0]
    assert not rs.aceptable({**m, "integridad": {**m["integridad"], "borde": 11}}, base)[0]   # agujero nuevo
