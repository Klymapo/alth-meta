"""Pruebas del cuerpo real de personaje (sin Blender)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "alth"))
import personaje as p  # noqa: E402
import cuerpo as base  # noqa: E402


def test_trae_todas_las_piezas_del_cuerpo():
    piezas = p.plan()["piezas"]
    esperadas = {"torso", "pelvis", "cabeza", "nariz"}
    for lado in ("izq", "der"):
        esperadas |= {f"pierna_{lado}", f"zapato_{lado}", f"oreja_{lado}",
                      f"brazo_{lado}", f"antebrazo_{lado}"}
        for parte in ("palma", "indice", "medio", "anular", "menique", "pulgar"):
            esperadas.add(f"mano_{lado}_{parte}")
    assert esperadas <= piezas.keys()


def test_anclas_coinciden_con_alth_cuerpo():
    pl = p.plan("estandar")
    a = pl["anclas"]
    assert a["cadera"] == 33.0 and a["cuello"] == 60.5 and a["altura"] == 95.0


def test_brazos_en_t_quedan_horizontales_y_simetricos():
    piezas = p.plan()["piezas"]
    bd, bi = piezas["brazo_der"], piezas["brazo_izq"]
    assert bd["pos"][2] == bi["pos"][2]              # mismo hombro en Z
    assert bd["rot"] == (0, 90, 0) and bi["rot"] == (0, -90, 0)
    assert bd["pos"][0] == base.HOMBRO_X and bi["pos"][0] == -base.HOMBRO_X


def test_la_mano_queda_al_final_del_brazo_extendido():
    pl = p.plan()
    piezas = pl["piezas"]
    x_hombro = base.HOMBRO_X
    largo_total = base.BRAZO[0][1] + base.BRAZO[1][1]
    x_muneca_esperado = x_hombro + largo_total
    assert math.isclose(piezas["_punta_mano_der"] - base.PALMA["L"], x_muneca_esperado, abs_tol=1e-6)


def test_dedos_y_pulgar_no_se_repiten_y_estan_dentro_de_la_palma_en_z():
    piezas = p.plan()["piezas"]
    z_hombro = piezas["brazo_der"]["pos"][2]
    for lado in ("izq", "der"):
        nombres = {f"mano_{lado}_{n}" for n in ("indice", "medio", "anular", "menique")}
        alturas = {piezas[n]["pos"][2] for n in nombres}
        assert len(alturas) == 4  # cada dedo a su propia altura, sin solaparse
        assert all(abs(z - z_hombro) < base.PALMA["W"] for z in alturas)


def test_la_cabeza_no_cambia_entre_arquetipos():
    cab = lambda arq: p.plan(arq)["piezas"]["cabeza"]["tam"]
    assert cab("menuda") == cab("alta") == (40.0, 29.8, 34.5)


def test_orejas_simetricas_y_fuera_del_eje_central():
    piezas = p.plan()["piezas"]
    oi, od = piezas["oreja_izq"]["pos"], piezas["oreja_der"]["pos"]
    assert oi[0] == -od[0] and od[0] > 0
    assert oi[2] == od[2]
