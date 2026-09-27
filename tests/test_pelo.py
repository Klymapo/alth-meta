"""Pruebas del pelo grueso faceteado (sin Blender)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "alth"))
import pelo as p  # noqa: E402
import personaje  # noqa: E402

CABEZA = personaje.plan()["piezas"]["cabeza"]


def test_casco_es_mas_grande_que_el_craneo():
    d = p.plan_casco(CABEZA, escala=1.3)
    assert 1.25 <= d["radio_ecuador"] / (CABEZA["w_arriba"] / 2) <= 1.35


def test_casco_se_corre_hacia_atras_no_hacia_la_cara():
    d = p.plan_casco(CABEZA, escala=1.3, sesgo_atras=1.6)
    assert d["pos"][1] > CABEZA["pos"][1]  # +Y es "atrás" (frente es −Y)


def test_casco_no_baja_mas_que_la_ceja():
    d = p.plan_casco(CABEZA)
    assert d["z_base"] > CABEZA["pos"][2] + CABEZA["h"] * 0.3


def test_cantidad_de_mechones_pedida():
    casco = p.plan_casco(CABEZA)
    m = p.plan_mechones(casco, CABEZA, cantidad=17)
    assert len(m) == 17


def test_mechones_no_crecen_por_debajo_del_borde_del_casco():
    casco = p.plan_casco(CABEZA)
    for m in p.plan_mechones(casco, CABEZA, cantidad=30, semilla=5):
        assert m["pos"][2] >= casco["z_base"] - 1e-6


def test_mechones_respetan_los_rangos_pedidos():
    casco = p.plan_casco(CABEZA)
    rango_largo, rango_ancho, rango_caida = (10.0, 14.0), (4.0, 5.0), (1.0, 2.0)
    for m in p.plan_mechones(casco, CABEZA, cantidad=12, largo=rango_largo, ancho=rango_ancho,
                              caida=rango_caida, semilla=2):
        assert rango_largo[0] <= m["largo"] <= rango_largo[1]
        assert rango_ancho[0] <= m["ancho"] <= rango_ancho[1]
        assert rango_caida[0] <= m["caida"] <= rango_caida[1]


def test_mismo_semilla_da_los_mismos_mechones():
    casco = p.plan_casco(CABEZA)
    a = p.plan_mechones(casco, CABEZA, cantidad=8, semilla=9)
    b = p.plan_mechones(casco, CABEZA, cantidad=8, semilla=9)
    assert a == b


def test_marco_de_cara_son_dos_mechones_simetricos_y_largos():
    piezas = p.mechones_marco_cara(CABEZA, largo=17.0)
    assert len(piezas) == 2
    (a, b) = piezas
    assert a["pos"][0] == -b["pos"][0]
    assert a["largo"] == b["largo"] == 17.0
    # cuelgan hacia el frente (−Y) y un poco hacia abajo
    for m in piezas:
        assert m["direccion"][1] < 0
        assert m["direccion"][2] > 0
        norma = math.sqrt(sum(v * v for v in m["direccion"]))
        assert math.isclose(norma, 1.0, rel_tol=1e-9)


def test_marco_de_cara_enmarca_ambos_lados_de_la_cabeza():
    piezas = p.mechones_marco_cara(CABEZA)
    xs = sorted(m["pos"][0] for m in piezas)
    assert xs[0] < 0 < xs[1]


def test_factor_frente_no_reduce_en_los_lados_y_reduce_de_frente():
    assert p._factor_frente(0, 0.6) == 1.0    # lado (+X)
    assert p._factor_frente(180, 0.6) == 1.0  # lado (−X)
    assert math.isclose(p._factor_frente(270, 0.6), 0.4)  # de frente (−Y): 1 − 0.6


def test_el_casco_no_monta_sobre_la_cara():
    """Por ser una revolución, lo ancho que sea atrás/lados se repite al frente salvo por
    `_factor_frente`: en el anillo más ancho, el borde de-frente debe quedar detrás de la cara."""
    d = p.plan_casco(CABEZA, escala=1.3)
    radio_mas_ancho = max(r for r, _ in d["perfil"])
    y_frente_casco = d["pos"][1] - radio_mas_ancho * (1 - d["reduccion_frente"]) * d["ovalo"][1]
    y_cara = CABEZA["pos"][1] - CABEZA["d_arriba"] / 2
    assert y_frente_casco > y_cara  # más atrás que la cara (frente es −Y)


def test_el_casco_si_cubre_bien_los_lados():
    """A los lados (sin reducción) debe ganarle claramente al ancho del cráneo."""
    d = p.plan_casco(CABEZA, escala=1.3)
    radio_mas_ancho = max(r for r, _ in d["perfil"])
    assert radio_mas_ancho > CABEZA["w_arriba"] / 2 * 1.2
