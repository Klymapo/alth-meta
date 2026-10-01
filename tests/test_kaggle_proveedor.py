"""Pruebas del proveedor Kaggle (sin red, sin GPU, sin credenciales, sin la CLI de Kaggle).

    python3 -m pytest tests/test_kaggle_proveedor.py

La CLI se simula inyectando `ejecutar`; el script que corre en Kaggle se compila y se revisa como texto.
"""
import base64
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import kaggle_proveedor as kp  # noqa: E402

FONDO = (227, 226, 233)


def _imagen(d: Path, lleno=False) -> Path:
    im = Image.new("RGB", (400, 400), FONDO)
    if lleno:
        ImageDraw.Draw(im).rectangle((0, 0, 399, 399), fill=(168, 69, 59))
    else:
        ImageDraw.Draw(im).ellipse((120, 110, 280, 290), fill=(168, 69, 59))
    p = Path(d) / "ref.png"
    im.save(p)
    return p


def test_preparar_imagen_da_alfa_valido_para_triposg():
    with tempfile.TemporaryDirectory() as d:
        im, info = kp.preparar_imagen(_imagen(d))
    a = np.asarray(im)
    assert im.mode == "RGBA" and set(np.unique(a[..., 3])) <= {0, 255}
    assert (a[..., 3] == 0).mean() >= 0.01 and (a[..., 3] == 255).mean() >= 0.01
    assert a[200, 200, 3] == 255 and a[5, 5, 3] == 0
    assert "sin RMBG" in info["metodo_fondo"]


def test_preparar_imagen_rechaza_figura_que_llena_todo():
    with tempfile.TemporaryDirectory() as d:
        try:
            kp.preparar_imagen(_imagen(d, lleno=True))
        except ValueError:
            return
    raise AssertionError("debió rechazar una imagen sin fondo")


def test_metadata_kernel():
    m = kp.metadata_kernel("klymapo", "alth-meta-propuesta")
    assert m["id"] == "klymapo/alth-meta-propuesta" and m["code_file"] == "propuesta.py"
    assert m["enable_gpu"] is True and m["enable_internet"] is True and m["is_private"] is True
    assert m["kernel_type"] == "script" and m["language"] == "python"
    for malo in ("", "con espacios", "a" * 60):
        try:
            kp.metadata_kernel(malo, "alth-meta-propuesta")
        except ValueError:
            continue
        raise AssertionError(malo)
    assert kp.slug_valido("ALTH Meta Propuesta!") == "alth-meta-propuesta"


def test_script_del_kernel_compila_y_no_usa_rmbg():
    params = {"nombre": "x", "caras": 20000, "semilla": 42, "pasos": 50, "guia": 7.0,
              "repo": kp.TRIPOSG_REPO, "commit": kp.TRIPOSG_COMMIT, "pesos": kp.TRIPOSG_PESOS}
    src = kp.script_kernel(base64.b64encode(b"png").decode(), params)
    compile(src, "propuesta.py", "exec")
    codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "briarmbg" not in codigo.lower() and "RMBG-1.4" not in codigo and "BriaRMBG" not in codigo
    assert "rmbg_net=None" in codigo
    assert kp.TRIPOSG_COMMIT in src and "checkout" in src
    assert "numpy" in src and 'startswith("numpy")' in src      # no instala el numpy==1.22.3 fijado
    assert "meta.json" in src and "propuesta.glb" in src and "sys.exit(1)" in src


def test_armar_escribe_carpeta_completa_e_imagen_incrustada():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pedido = kp.armar(_imagen(d), "manzana", d / "k", "klymapo", caras=500)
        assert (d / "k" / "kernel-metadata.json").exists() and (d / "k" / "entrada.png").exists()
        src = (d / "k" / "propuesta.py").read_text()
        compile(src, "propuesta.py", "exec")
        b64 = src.split("IMAGEN_B64 = '")[1].split("'")[0]
        im = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert im.mode == "RGBA"
        assert pedido["parametros"]["caras"] == 500 and len(pedido["imagen_sha256"]) == 64
        assert json.loads((d / "k" / "pedido.json").read_text())["kernel"] == "klymapo/alth-meta-propuesta"
        for malo in ({"caras": 10}, {"pasos": 0}):
            try:
                kp.armar(_imagen(d), "m", d / "k2", "klymapo", **malo)
            except ValueError:
                continue
            raise AssertionError(malo)


def test_estado_de():
    assert kp.estado_de('klymapo/x has status "running"') == "corriendo"
    assert kp.estado_de('klymapo/x has status "queued"') == "corriendo"
    assert kp.estado_de('klymapo/x has status "complete"') == "completo"
    assert kp.estado_de('klymapo/x has status "error"') == "fallido"
    assert kp.estado_de('klymapo/x has status "cancelAcknowledged"') == "fallido"
    assert kp.estado_de("algo raro") == "desconocido"


class _CLIFalsa:
    """Simula `kaggle kernels push/status/output`."""

    def __init__(self, estados, deja_glb=True, push_ok=True, meta=None):
        self.estados, self.deja_glb, self.push_ok, self.meta = list(estados), deja_glb, push_ok, meta
        self.llamadas = []

    def __call__(self, cmd, **kw):
        self.llamadas.append(cmd)
        sub = cmd[2]
        if sub == "push":
            return subprocess.CompletedProcess(cmd, 0 if self.push_ok else 1, "Kernel version 1 successfully pushed", "")
        if sub == "status":
            return subprocess.CompletedProcess(cmd, 0, f'x has status "{self.estados.pop(0)}"', "")
        if sub == "output":
            dest = Path(cmd[cmd.index("-p") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            if self.deja_glb:
                (dest / "propuesta.glb").write_bytes(b"glTF")
            (dest / "meta.json").write_text(json.dumps(self.meta or {"estado": "OK", "caras": 500, "traza": "x"}))
            return subprocess.CompletedProcess(cmd, 0, "Output file downloaded", "")
        raise AssertionError(cmd)


def _kernel(d: Path) -> Path:
    k = d / "k"
    k.mkdir()
    (k / "kernel-metadata.json").write_text(json.dumps(kp.metadata_kernel("klymapo", "alth-meta-propuesta")))
    return k


def _lanzar(d, cli, minutos=90):
    reloj = iter(range(0, 10**6, 30))
    return kp.lanzar(_kernel(d), d / "out", minutos=minutos, cada=30, ejecutar=cli,
                     dormir=lambda s: None, reloj=lambda: next(reloj))


def test_lanzar_ok_vigila_y_baja_la_propuesta():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = _CLIFalsa(["queued", "running", "complete"])
        codigo, r = _lanzar(d, cli)
        assert codigo == kp.EXIT_OK and r["estado"] == "OK" and r["intentos_status"] == 3
        assert (d / "out" / "propuesta.glb").exists() and "traza" not in r["meta"]
        push = cli.llamadas[0]
        assert push[:3] == ["kaggle", "kernels", "push"] and "--accelerator" in push and kp.ACELERADOR in push


def test_lanzar_fallos():
    with tempfile.TemporaryDirectory() as d:
        assert _lanzar(Path(d), _CLIFalsa([], push_ok=False))[0] == kp.EXIT_FALLO
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), _CLIFalsa(["running", "error"], meta={"estado": "ERROR", "error": "CUDA"}))
        assert codigo == kp.EXIT_FALLO and r["estado"] == "KERNEL_FALLIDO" and r["meta"]["error"] == "CUDA"
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), _CLIFalsa(["running"] * 500), minutos=2)
        assert codigo == kp.EXIT_TIEMPO and r["estado"] == "TIEMPO_AGOTADO"
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), _CLIFalsa(["complete"], deja_glb=False))
        assert codigo == kp.EXIT_SIN_SALIDA and r["estado"] == "SIN_PROPUESTA"


def test_cli_sin_credenciales_y_armar_sin_red():
    import os
    viejas = {k: os.environ.pop(k, None) for k in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_CONFIG_DIR")}
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            os.environ["KAGGLE_CONFIG_DIR"] = str(d / "sin_config")
            img = _imagen(d)
            assert kp.main(["lanzar", str(img), "--nombre", "manzana"]) == kp.EXIT_CREDENCIALES
            assert kp.main(["armar", str(img), "--nombre", "manzana", "--usuario", "klymapo",
                            "--carpeta", str(d / "k")]) == kp.EXIT_OK
            assert kp.main(["armar", str(d / "no_existe.png"), "--nombre", "x", "--usuario", "klymapo",
                            "--carpeta", str(d / "k2")]) == kp.EXIT_ENTRADA
            os.environ["KAGGLE_USERNAME"], os.environ["KAGGLE_KEY"] = "klymapo", "x"
            assert kp.credenciales() == "klymapo"
    finally:
        for k, v in viejas.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------- imágenes reales (regresión de la sombra)
def _pegada(ruta, recorte):
    return kp.preparar_imagen(RAIZ / ruta, recorte)[1]["sombra_pegada_quitada"]


def test_real_quita_la_sombra_del_piso_en_referencias():
    assert _pegada("refs/personajes/joven-rubio.jpg", None) > 0.05
    assert _pegada("refs/infografias/objeto-01-manzana.png", [0.52, 0.1, 1, 1]) > 0.05
    assert _pegada("assets/taza/final.png", [0.5, 0.53, 1, 1]) > 0.15      # sombra larga del render 3/4


def test_real_conserva_piezas_grises_de_borde_nitido():
    # el aro metálico inferior de la lata es gris y no tiene nada debajo, pero su borde es nítido
    assert _pegada("assets/lata/final.png", [0, 0.03, 0.5, 0.5]) == 0
