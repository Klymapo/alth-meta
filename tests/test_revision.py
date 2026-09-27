"""La hoja revisada y los archivos que se aprobarán deben ser la misma versión."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import bucle  # noqa: E402
import verificar_revision  # noqa: E402


def test_revision_detecta_cambio_de_codigo_o_imagen(tmp_path, monkeypatch):
    monkeypatch.setattr(bucle, "RAIZ", tmp_path)
    monkeypatch.setattr(verificar_revision, "ROOT", tmp_path)
    carpeta = tmp_path / "assets" / "manzana"
    carpeta.mkdir(parents=True)
    (carpeta / "build.py").write_text("print('modelo')\n")
    (carpeta / "spec.json").write_text('{"nombre":"manzana"}\n')
    render = tmp_path / "renders" / "manzana" / "iteracion"
    render.mkdir(parents=True)
    (render / "hoja.png").write_bytes(b"PNG de prueba")
    (render / "reporte.json").write_text('{"verificacion":{"ok":true}}')
    asset = SimpleNamespace(
        dir=carpeta, spec_path=carpeta / "spec.json",
        editables=["assets/manzana/build.py"],
        trabajo=tmp_path / "renders" / "manzana" / "bucle",
        rel=lambda p: p.relative_to(tmp_path).as_posix(),
    )
    asset.trabajo.mkdir()
    resultado = {"ok": True, "carpeta": render, "reporte": {"verificacion": {"ok": True}}}
    datos = bucle.guardar_revision(asset, resultado, 3, "mejor silueta")
    destino = carpeta / "bucle"
    destino.mkdir()
    (destino / "hoja_ultima.png").write_bytes((asset.trabajo / "revision" / "hoja.png").read_bytes())
    (destino / "reporte_revision.json").write_bytes((asset.trabajo / "revision" / "reporte.json").read_bytes())
    (destino / "revision.json").write_text(json.dumps(datos))
    assert verificar_revision.verificar("assets/manzana")["vuelta_origen"] == 3

    (carpeta / "build.py").write_text("print('otro modelo')\n")
    with pytest.raises(ValueError, match="archivo revisado"):
        verificar_revision.verificar("assets/manzana")
    (carpeta / "build.py").write_text("print('modelo')\n")
    (destino / "hoja_ultima.png").write_bytes(b"otra imagen")
    with pytest.raises(ValueError, match="evidencia revisada"):
        verificar_revision.verificar("assets/manzana")
