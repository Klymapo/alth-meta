"""Pruebas de la comparación de silueta y de las piezas puras del bucle (sin Blender, sin red).

    python3 -m pytest tests/
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "alth"))
sys.path.insert(0, str(RAIZ / "tools"))
import silueta as s  # noqa: E402
import bucle as b  # noqa: E402


def figura(ancho_cabeza, ancho_cuerpo, lienzo=(300, 300), fondo=(228, 228, 234)):
    im = np.zeros((lienzo[1], lienzo[0], 3), dtype=np.uint8)
    im[:] = fondo
    cx = lienzo[0] // 2
    im[40:120, cx - ancho_cabeza // 2: cx + ancho_cabeza // 2] = (240, 190, 150)   # cabeza
    im[120:260, cx - ancho_cuerpo // 2: cx + ancho_cuerpo // 2] = (50, 50, 60)      # cuerpo
    return im


def test_misma_figura_coincide():
    m = s.mascara(figura(80, 50).astype(np.float32))
    r = s.comparar(m, m)
    assert r["iou"] > 0.99
    assert r["frases"] == ["La silueta coincide con la referencia dentro de la tolerancia."]


def test_detecta_cabeza_angosta_arriba():
    modelo = s.mascara(figura(50, 50).astype(np.float32))
    ref = s.mascara(figura(90, 50).astype(np.float32))
    r = s.comparar(modelo, ref)
    assert r["iou"] < 0.9
    arriba = [f for f in r["frases"] if "arriba" in f]
    assert arriba and "más angosto" in arriba[0]


def test_escala_no_importa():
    grande_im = figura(80, 50)
    chica_im = np.asarray(Image.fromarray(grande_im).resize((130, 130), Image.NEAREST))
    chica = s.mascara(chica_im.astype(np.float32))
    grande = s.mascara(grande_im.astype(np.float32))
    assert s.comparar(chica, grande)["iou"] > 0.9


def test_mayor_mancha_ignora_maniqui():
    im = figura(80, 50)
    im[200:240, 10:30] = (180, 180, 185)  # bloque suelto (maniquí/sombra)
    m = s.mayor_mancha(s.mascara(im.astype(np.float32)))
    assert not m[220, 20]
    assert m[200, 150]


def test_superposicion_y_archivos(tmp_path):
    Image.fromarray(figura(60, 50)).save(tmp_path / "r.png")
    Image.fromarray(figura(90, 50)).save(tmp_path / "ref.png")
    r = s.comparar_archivos(tmp_path / "r.png", tmp_path / "ref.png", superposicion=tmp_path / "sup.png")
    assert (tmp_path / "sup.png").exists() and r["iou"] < 1


# ---------------------------------------------------------------- bucle
RESPUESTA = """CAMBIOS: pelo más ancho arriba
ESTADO: SIGUE

### ARCHIVO: assets/x/build.py
```python
import alth
alth.revisar([], "renders/x")
```

### ARCHIVO: alth/pelo.py
```python
def f():
    return 1
```
"""


def test_extraer_archivos_y_campos():
    arch = b.extraer_archivos(RESPUESTA)
    assert set(arch) == {"assets/x/build.py", "alth/pelo.py"}
    assert arch["alth/pelo.py"].startswith("def f")
    assert b.extraer_campo(RESPUESTA, "CAMBIOS") == "pelo más ancho arriba"
    assert b.extraer_campo(RESPUESTA, "ESTADO") == "SIGUE"


def test_bloque_suelto_es_build():
    arch = b.extraer_archivos("Aquí va:\n```python\nprint(1)\n```\n")
    assert arch == {"": "print(1)\n"}


def test_guardia_de_codigo():
    assert b.revisar_codigo("import alth\nalth.revisar([], 'x')\n") == []
    assert any("prohibido" in p for p in b.revisar_codigo("import subprocess\n"))
    assert any("sintaxis" in p for p in b.revisar_codigo("def (:\n"))


def test_api_alth_sin_bpy():
    api = b.api_alth([RAIZ / "alth" / "__init__.py"])
    assert "alth.torno(" in api and "alth.revisar(" in api


def test_ref_de_spec():
    assert b.ref_de_spec({"referencia": "ver refs/personajes/joven-rubio-4-vistas.jpg (T-pose)"}) == \
        "refs/personajes/joven-rubio-4-vistas.jpg"


def test_seccion_convenciones():
    txt = b.seccion_md((RAIZ / "CLAUDE.md").read_text(encoding="utf-8"), "Convenciones")
    assert "1 unidad de Blender = 1 mm" in txt
