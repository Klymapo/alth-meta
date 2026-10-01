"""Receta por código (T2): de la ficha a piezas alth, esquema y entrada por issue. Sin Blender.

    python3 -m pytest tests/test_receta.py
"""
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import entrada_issue as ei  # noqa: E402
import receta as R  # noqa: E402
import reconocer as rec  # noqa: E402

MANZANA = ("refs/infografias/objeto-01-manzana.png", (0.52, 0.1, 1.0, 1.0))


@pytest.fixture(scope="module")
def ficha_manzana():
    return rec.reconocer(MANZANA[0], "manzana", "8cm", recorte=MANZANA[1])


@pytest.fixture(scope="module")
def receta_manzana(ficha_manzana):
    return R.armar(ficha_manzana)


def test_receta_manzana_cumple_esquema(receta_manzana):
    assert R.validar(receta_manzana) == []
    assert receta_manzana["origen"]["metodo"].startswith("tools/receta.py")


def test_receta_manzana_piezas_salen_de_la_imagen(receta_manzana):
    piezas = receta_manzana["piezas"]
    assert piezas[0]["id"] == "cuerpo" and piezas[0]["modulo"] == "torno"
    assert {p["modulo"] for p in piezas[1:]} == {"hoja", "prisma"}       # hoja (gota) y tallo (punta roma)
    perfil = piezas[0]["params"]["perfil"]
    assert [z for _, z in perfil] == sorted(z for _, z in perfil)         # de abajo hacia arriba
    assert max(r for r, _ in perfil) * 2 == pytest.approx(receta_manzana["medidas_mm"]["cuerpo_ancho"], rel=0.05)
    hoja = next(p for p in piezas if p["modulo"] == "hoja")
    assert hoja["color"] in {"#7E9B7A", "#7E8B5A", "#A9B288", "#5E7759", "#5F6944"}  # verde de paleta


def test_receta_manzana_medidas_con_s0_de_alpha(receta_manzana):
    s0 = json.loads((RAIZ / "spec" / "alth_spec.json").read_text())["escala_alpha"]["s0"]
    assert receta_manzana["medidas_mm"]["ancho"] == pytest.approx(80 * s0 * 2.0, abs=0.02)   # "8cm", k=2
    assert any("sombra" in a for a in receta_manzana["avisos"])                             # la sombra no cuenta
    assert receta_manzana["tris_max"] == 500


def test_receta_no_inventa(ficha_manzana):
    with pytest.raises(R.RecetaNoSoportada):
        R.armar({**ficha_manzana, "tipo": "personaje"})
    with pytest.raises(R.RecetaNoSoportada):
        R.armar({**ficha_manzana, "capacidades": [{"id": "caja"}]})
    with pytest.raises(R.RecetaNoSoportada):
        R.armar({**ficha_manzana, "tamano_alth_mm": {"alto": None, "ancho": None}})


def test_validar_detecta_errores(receta_manzana):
    mala = json.loads(json.dumps(receta_manzana))
    mala["piezas"][0]["modulo"] = "cubo"
    mala["piezas"][1]["color"] = "rojo"
    del mala["k"]
    mala["extra"] = 1
    e = R.validar(mala)
    assert any("'k'" in x for x in e) and any("cubo" in x for x in e) and any("rojo" in x for x in e)
    assert any("extra" in x for x in e)


def test_fijar_y_obtener(receta_manzana):
    n = R.fijar(receta_manzana, "piezas.0.params.ruido_r", 0.0)
    assert R.obtener(n, "piezas.0.params.ruido_r") == 0.0
    assert R.obtener(receta_manzana, "piezas.0.params.ruido_r") == 0.06       # no muta la original
    for a in receta_manzana["ajustables"]:
        R.obtener(receta_manzana, a["ruta"])                                  # toda ruta ajustable existe


def test_issue_formulario_y_titulo():
    cuerpo = ("### Nombre\n\nmanzana\n\n### Tamaño real\n\n8cm\n\n### Recorte\n\n_No response_\n\n### Imagen\n\n"
              "![IMG_1](https://github.com/user-attachments/assets/abc)\n")
    c = ei.campos("crear: manzana", cuerpo)
    assert c == {"nombre": "manzana", "tamano": "8cm", "recorte": None,
                 "imagen_url": "https://github.com/user-attachments/assets/abc"}
    c = ei.campos("crear: lata de atún, 10cm", '<img width="300" src="https://x.y/z.png">')
    assert c["nombre"] == "lata de atún" and c["tamano"] == "10cm" and c["imagen_url"] == "https://x.y/z.png"
    assert ei.campos("hola", "sin nada")["imagen_url"] is None
