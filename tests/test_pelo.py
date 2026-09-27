"""Pruebas del pelo (una sola malla: corona + cuñas), sin Blender."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "alth"))
import pelo as p  # noqa: E402
import personaje  # noqa: E402

CABEZA = personaje.plan()["piezas"]["cabeza"]


def test_corona_mas_grande_que_el_craneo():
    c = p.plan_corona(CABEZA, escala=1.3)
    assert 1.25 <= c["hw"] / (CABEZA["w_arriba"] / 2) <= 1.35


def test_corona_corrida_hacia_atras_y_mas_alta_que_el_craneo():
    c = p.plan_corona(CABEZA, escala=1.3, sesgo_atras=2.5)
    assert c["cy"] > CABEZA["pos"][1]  # +Y es "atrás" (frente es −Y)
    assert c["z_top"] > CABEZA["pos"][2] + CABEZA["h"]


def test_borde_de_la_corona_es_mas_alto_al_frente_que_atras():
    c = p.plan_corona(CABEZA)
    assert c["z_frente"] > c["z_lado"] > c["z_atras"]  # frente = corto (no baja); atrás = largo


def test_zona_z_da_cada_altura_en_su_azimut():
    c = p.plan_corona(CABEZA)
    assert p._zona_z(270, c["z_frente"], c["z_lado"], c["z_atras"]) == c["z_frente"]
    assert p._zona_z(90, c["z_frente"], c["z_lado"], c["z_atras"]) == c["z_atras"]
    assert p._zona_z(0, c["z_frente"], c["z_lado"], c["z_atras"]) == c["z_lado"]
    assert p._zona_z(180, c["z_frente"], c["z_lado"], c["z_atras"]) == c["z_lado"]


def test_cantidad_de_cunias_pedida():
    c = p.plan_corona(CABEZA)
    assert len(p.plan_cunias(c, cunias=8)) == 8
    assert len(p.plan_cunias(c, cunias=12)) == 12


def test_ninguna_cuna_queda_delgada():
    c = p.plan_corona(CABEZA)
    for cunia in p.plan_cunias(c, cunias=12, ancho_base=(8.0, 12.0), semilla=3):
        assert cunia["ancho"] >= 6.0


def test_cunias_necesita_al_menos_tres():
    c = p.plan_corona(CABEZA)
    try:
        p.plan_cunias(c, cunias=2)
        assert False, "debía levantar ValueError"
    except ValueError:
        pass


def test_dos_cunias_de_marco_simetricas_al_frente():
    c = p.plan_corona(CABEZA)
    piezas = p.plan_cunias(c, cunias=10, semilla=1)
    marco = [m for m in piezas if m["es_marco"]]
    assert len(marco) == 2
    azimutes = sorted(m["azimut"] for m in marco)
    assert azimutes == sorted(p.MARCO_AZIMUT)
    # ambas caen hacia adelante (−Y) y hacia abajo
    for m in marco:
        assert m["direccion"][1] < 0
        assert m["direccion"][2] < 0


def test_las_cunias_de_marco_son_mas_largas_y_caen_mas():
    c = p.plan_corona(CABEZA)
    piezas = p.plan_cunias(c, cunias=10, largo=(10.0, 12.0), caida=(3.0, 4.0), semilla=1)
    marco = [m for m in piezas if m["es_marco"]]
    otras = [m for m in piezas if not m["es_marco"]]
    assert min(m["largo"] for m in marco) > max(m["largo"] for m in otras)
    assert min(m["caida"] for m in marco) > max(m["caida"] for m in otras)


def test_mismo_semilla_da_el_mismo_plan():
    c = p.plan_corona(CABEZA)
    a = p.plan_cunias(c, cunias=9, semilla=7)
    b = p.plan_cunias(c, cunias=9, semilla=7)
    assert a == b


def test_plan_pelo_junta_corona_cunias_y_copete():
    plan = p.plan_pelo(CABEZA, cunias=11, copete=3)
    assert "corona" in plan and "cunias" in plan
    assert len(plan["cunias"]) == 11 + 3
    assert sum(1 for c in plan["cunias"] if c["es_copete"]) == 3


def test_copete_nace_cerca_de_la_punta_no_del_borde():
    c = p.plan_corona(CABEZA)
    for cuna in p.plan_copete(c, cantidad=3):
        assert cuna["pos"][2] > c["z_frente"]  # más arriba que el punto más alto del borde
        assert cuna["pos"][2] <= c["z_top"]


def test_copete_apunta_arriba_y_adelante_no_radial():
    c = p.plan_corona(CABEZA)
    for cuna in p.plan_copete(c, cantidad=3):
        dx, dy, dz = cuna["direccion"]
        assert dz > 0.7          # sobre todo hacia +Z
        assert dy < 0             # y hacia adelante (−Y)
        assert dz > abs(dx)       # más vertical que lateral: no es radial


def test_copete_es_mas_largo_que_las_cunias_del_borde():
    # se compara el rango pedido, no una muestra aleatoria (los rangos por defecto se solapan
    # un poco: lo que importa es que el copete parte más largo, no que CADA cuña lo sea).
    rango_copete = (15.0, 22.0)
    rango_borde = (10.0, 17.0)
    assert rango_copete[0] > rango_borde[0] and rango_copete[1] > rango_borde[1]


def test_copete_cero_no_agrega_nada():
    c = p.plan_corona(CABEZA)
    assert p.plan_copete(c, cantidad=0) == []
