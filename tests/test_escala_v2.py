"""Escala v2 (bloque T0): spec con escala_alpha, assets re-dimensionados y medidas.csv coherentes.

    python3 -m pytest tests/test_escala_v2.py

Sin Blender: lee la spec, los spec.json de los assets, data/medidas.csv y los GLB como bytes.
La medición de Alpha en Blender (tools/medir_alpha.py) corre en la auditoría con alth-python.
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import medir_alpha as ma  # noqa: E402
import redimensionar as rd  # noqa: E402

SPEC = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))


def test_spec_v2_trae_s0_de_alpha():
    ea = SPEC["escala_alpha"]
    assert SPEC["version"] == "2.0"
    assert ea["alto_real_theo_mm"] == 1800.0
    assert abs(ea["s0"] - ea["alto_cuerpo_alpha_mm"] / ea["alto_real_theo_mm"]) < 1e-5
    assert 0.052 < ea["s0"] < 0.054          # 95.7 / 1800 ≈ 0.0532 (brief, 1 oct 2026)
    assert SPEC["unidades"]["s0_real_a_alth"] == ea["s0"]
    assert "escala_alpha.s0" in SPEC["conversion_k"]["formula"]
    assert SPEC["escala_congelada"]["anterior"]["version"] == "v1.0"   # la v1 queda como historial


def test_piezas_de_alpha_son_coherentes():
    p = SPEC["escala_alpha"]["piezas_mm"]
    a = SPEC["escala_alpha"]["anclas_z_mm"]
    assert 0 < a["tobillo"] < a["cadera"] < a["cintura"] < a["hombro"] < a["cuello"] < a["cabeza_tope"]
    assert abs(p["piernas_L"] + p["torso_H"] + p["cabeza_WHD"][1] - a["cabeza_tope"]) < 0.1
    assert p["cabeza_WHD"][0] > p["torso_W"]            # chibi: cabeza más ancha que el torso
    assert 10 < p["mano_L"] < 25


def test_dedos_reescalados_con_la_mano_de_alpha():
    mano = SPEC["escala_alpha"]["mano_mm"]
    v1 = SPEC["cuerpo_base_95mm"]["dedos_L"]
    f = mano["factor_vs_95"]
    assert abs(f - SPEC["escala_alpha"]["piezas_mm"]["mano_L"] / (7.5 + 6.0)) < 1e-3
    for dedo, largo in v1.items():
        assert abs(mano["dedos_L"][dedo] - largo * f) < 0.01


def test_arquetipos_relativos_a_alpha():
    arq = SPEC["arquetipos_alpha"]
    assert arq["estandar"]["factor_vs_alpha"] == 1.0
    assert arq["estandar"]["alto_mm"] == SPEC["escala_alpha"]["alto_cuerpo_alpha_mm"]
    assert arq["menuda"]["factor_vs_alpha"] < arq["media"]["factor_vs_alpha"] < 1 < arq["alta"]["factor_vs_alpha"]


def test_spec_v2_es_idempotente():
    med = json.loads((RAIZ / "data" / "alpha_medidas.json").read_text(encoding="utf-8"))
    otra = ma.spec_v2(SPEC, med)
    assert otra["escala_alpha"] == SPEC["escala_alpha"]
    assert otra["escala_congelada"]["anterior"] == SPEC["escala_congelada"]["anterior"]


def test_ancho_central_ignora_brazos_separados():
    rng = np.random.default_rng(0)
    torso = np.c_[rng.uniform(-5, 5, 2000), rng.uniform(-2, 2, 2000), rng.uniform(0, 10, 2000)]
    brazo = np.c_[rng.uniform(8, 12, 500), rng.uniform(-1, 1, 500), rng.uniform(4, 6, 500)]
    filas = ma.ancho_central(np.r_[torso, brazo], 0, 10, paso=1.0)
    assert all(9.5 < w <= 10 for _, w in filas)


def test_primero_estable():
    xs = np.arange(10.0)
    frac = np.array([0, 0.2, 0.9, 0.1, 0.6, 0.8, 1, 1, 0.7, 1])
    assert ma._primero_estable(xs, frac) == 4.0


def test_alpha_intacto():
    assert hashlib.sha256((RAIZ / ma.ALPHA.relative_to(RAIZ)).read_bytes()).hexdigest() == ma.SHA_ALPHA


def test_assets_aprobados_en_escala_v2():
    s0 = SPEC["escala_alpha"]["s0"]
    for nombre in rd.APROBADOS:
        a = json.loads((RAIZ / "assets" / nombre / "spec.json").read_text(encoding="utf-8"))
        assert rd.ya_redimensionado(a), nombre
        assert a["escala"]["s0"] == s0
        assert f"* {s0} *" in a["medidas_alth_mm"]["formula"]
        k = a["k"]
        reales = a["medidas_reales_mm"]
        for clave, mm in a["medidas_alth_mm"].items():
            if clave in reales:
                assert abs(mm - reales[clave] * s0 * k) / mm < 0.02, (nombre, clave)


def test_glb_unificados():
    for nombre in rd.APROBADOS:
        r = rd.revisar_glb(RAIZ / "assets" / nombre / f"{nombre}.glb", 0.01)
        assert r["ok"], (nombre, r)


def test_medidas_csv_con_s0_nuevo():
    s0 = SPEC["escala_alpha"]["s0"]
    with (RAIZ / "data" / "medidas.csv").open(encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    assert len(filas) == 11
    for f in filas:
        k_esperado = float(f["alth_mm"]) / (float(f["real_mm"]) * s0)
        assert abs(k_esperado - float(f["k_observado"])) < 0.01
        assert abs(k_esperado - 2.0) < 0.03, f      # todos son de_mano (k=2)


def test_csv_puro_y_spec_asset_puro():
    filas = [{"asset": "x", "real_mm": "80", "alth_mm": "8.94", "k_observado": "2.00", "fecha": "a"},
             {"asset": "y", "real_mm": "80", "alth_mm": "8.94", "k_observado": "2.00", "fecha": "a"}]
    out = rd.filas_csv_nuevas(filas, {"x": 0.5}, 0.0559)
    assert out[0]["alth_mm"] == "4.47" and out[0]["k_observado"] == "1.00" and out[1] == filas[1]
    a = {"k": 2.0, "medidas_alth_mm": {"d": 10.0, "formula": "mm_real * 0.0559 * 2.0"},
         "cotas": [{"pieza": "p", "eje": "W", "mm": 10.0}]}
    assert rd.s0_viejo(a, {}) == 0.0559
    n = rd.spec_asset_nueva(a, 0.9, 0.05, 0.0559)
    assert n["medidas_alth_mm"]["d"] == 9.0 and n["cotas"][0]["mm"] == 9.0 and rd.ya_redimensionado(n)
    assert not rd.ya_redimensionado(a)
