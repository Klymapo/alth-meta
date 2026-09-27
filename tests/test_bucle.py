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


# ---------------------------------------------------------------- saturación de proveedores (503)
import io as _io  # noqa: E402
import json as _json  # noqa: E402
import urllib.error as _ue  # noqa: E402

import pytest  # noqa: E402


def _http(code):
    return _ue.HTTPError("u", code, "x", {}, _io.BytesIO(b'{"error":"high demand"}'))


class _Resp:
    def __init__(self, datos):
        self._d = _json.dumps(datos).encode()

    def read(self):
        return self._d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cfg_gemini():
    return {"nombre": "gemini", "base": "https://x/v1", "clave": "k", "modelo": "gemini-3.8-flash", "vision": True}


def test_elegir_alternos_filtra_y_ordena():
    ids = ["models/gemini-3.8-flash", "models/gemini-3.8-flash-lite", "models/gemini-3.5-flash",
           "models/gemini-3.8-flash-image", "models/gemini-3.8-pro", "models/gemini-3.9-flash-preview",
           "models/text-embedding-004"]
    assert b.elegir_alternos(ids, "gemini-3.8-flash", 3) == [
        "gemini-3.5-flash", "gemini-3.9-flash-preview", "gemini-3.8-flash-lite"]


def test_503_reintenta_y_luego_responde(monkeypatch):
    monkeypatch.setattr(b, "_dormir", lambda s: None)
    llamadas = []

    def urlopen(req, timeout=0):
        llamadas.append(req.full_url)
        if len(llamadas) < 3:
            raise _http(503)
        return _Resp({"choices": [{"message": {"content": "hola"}}]})

    monkeypatch.setattr(b.urllib.request, "urlopen", urlopen)
    assert b.llamar_modelo(_cfg_gemini(), "s", "t", []) == "hola"
    assert len(llamadas) == 3


def test_gemini_saturado_brinca_a_modelo_hermano(monkeypatch):
    monkeypatch.setattr(b, "_dormir", lambda s: None)
    usados = []

    def urlopen(req, timeout=0):
        if req.full_url.endswith("/models"):
            return _Resp({"data": [{"id": "models/gemini-3.8-flash"}, {"id": "models/gemini-3.5-flash"}]})
        modelo = _json.loads(req.data)["model"]
        usados.append(modelo)
        if modelo == "gemini-3.8-flash":
            raise _http(503)
        return _Resp({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(b.urllib.request, "urlopen", urlopen)
    texto, cfg = b.llamar_con_respaldo([_cfg_gemini()], "s", "t", [])
    assert texto == "ok" and cfg["modelo"] == "gemini-3.5-flash"
    assert usados.count("gemini-3.8-flash") == 1 + len(b.ESPERAS_SATURADO)


def test_todo_saturado_explica_que_hacer(monkeypatch):
    monkeypatch.setattr(b, "_dormir", lambda s: None)

    def urlopen(req, timeout=0):
        if req.full_url.endswith("/models"):
            return _Resp({"data": []})
        raise _http(503)

    monkeypatch.setattr(b.urllib.request, "urlopen", urlopen)
    with pytest.raises(SystemExit) as e:
        b.llamar_con_respaldo([_cfg_gemini()], "s", "t", [])
    msg = str(e.value)
    assert "saturado" in msg and "15–30 min" in msg and "GROQ_API_KEY" in msg


# ---------------------------------------------------------------- qué versión se queda
def test_se_queda_con_la_verificada_aunque_otra_tenga_mejor_silueta(tmp_path, monkeypatch):
    """Caso de la corrida 7: la última vuelta tiene mejor IoU pero reprueba la verificación."""
    import argparse
    (tmp_path / "assets" / "muñeco").mkdir(parents=True)
    build = tmp_path / "assets" / "muñeco" / "build.py"
    build.write_text("V = 0\n", encoding="utf-8")
    monkeypatch.setattr(b, "RAIZ", tmp_path)
    # vuelta: (verificación ok, IoU)
    plan = {0: (True, 0.60), 1: (True, 0.66), 2: (False, 0.70), 3: (False, 0.72)}

    def version():
        return int(build.read_text().split("=")[1])

    monkeypatch.setattr(b, "correr_build", lambda a, t: {
        "ok": True, "salida": "", "carpeta": None,
        "reporte": {"verificacion": {"ok": plan[version()][0]}}})
    monkeypatch.setattr(b, "medir_silueta", lambda a, r, dest: {"iou": plan[version()][1]})
    monkeypatch.setattr(b, "config_cadena", lambda a: [{"nombre": "falso", "modelo": "m", "vision": False}])
    monkeypatch.setattr(b, "texto_sistema", lambda: "")
    monkeypatch.setattr(b, "imagenes_para", lambda *a: [])
    monkeypatch.setattr(b, "armar_prompt", lambda *a, **k: "")
    monkeypatch.setattr(b, "llamar_con_respaldo", lambda *a, **k: ("CAMBIOS: x\nESTADO: SIGUE", a[0][0]))

    def aplicar(asset, respuesta):
        build.write_text(f"V = {version() + 1}\n", encoding="utf-8")
        return True, "ok", {}

    monkeypatch.setattr(b, "aplicar", aplicar)
    args = argparse.Namespace(asset="muñeco", ref=None, recorte=None, vista=None, nota=None, editable=None,
                              timeout=5, vueltas=3, proveedor="auto", modelo=None, sin_vision=False,
                              continuar=False)
    b.cmd_correr(args)
    assert version() == 1                                   # verificada, no la de IoU 0.72
    trabajo = tmp_path / "renders" / "muñeco" / "bucle"
    assert (trabajo / "elegida.txt").read_text().strip() == "v01"
    assert "vuelta 1 · verificación OK" in (trabajo / "resumen.md").read_text()
