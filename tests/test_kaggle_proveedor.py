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
    params = {"nombre": "x", "caras": 20000, "semilla": 42, "pasos": 50, "guia": 7.0, "pedido_id": "p",
              "repo": kp.TRIPOSG_REPO, "commit": kp.TRIPOSG_COMMIT, "pesos": kp.TRIPOSG_PESOS}
    src = kp.script_kernel(base64.b64encode(b"png").decode(), params)
    compile(src, "propuesta.py", "exec")
    codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert "briarmbg" not in codigo.lower() and "RMBG-1.4" not in codigo and "BriaRMBG" not in codigo
    assert "rmbg_net=None" in codigo
    assert kp.TRIPOSG_COMMIT in src and "checkout" in src
    assert "meta.json" in src and "propuesta.glb" in src and "sys.exit(1)" in src
    # diso (CC BY-NC) excluido: no se instala, se sustituye y se usa el decodificador jerárquico
    assert 'startswith(("numpy", "diso"))' in src and 'sys.modules["diso"]' in src
    assert "use_flash_decoder=False" in src
    assert "-c /kaggle/tmp/base.txt" in src and "pip_freeze.txt" in src
    assert src.index('sys.modules["diso"]') < src.index("from triposg")


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


def test_estado_de_lee_solo_el_estado_entrecomillado():
    # formato real: `owner/slug has status "KernelWorkerStatus.X"` (+ "Failure message" si falló)
    e = lambda x: kp.estado_de(f'klymapo/alth-meta-propuesta has status "KernelWorkerStatus.{x}"')
    assert e("QUEUED") == e("RUNNING") == e("NEW_SCRIPT") == "corriendo"
    assert e("COMPLETE") == "completo"
    assert e("ERROR") == e("CANCEL_REQUESTED") == e("CANCEL_ACKNOWLEDGED") == "fallido"
    # el id o el mensaje de fallo no confunden la lectura
    assert kp.estado_de('error-complete/x has status "KernelWorkerStatus.RUNNING"') == "corriendo"
    assert kp.estado_de('k/x has status "KernelWorkerStatus.ERROR"\nFailure message: "complete failure"') == "fallido"
    assert kp.estado_de("algo raro sin estado") == "desconocido"


def test_version_empujada():
    assert kp.version_empujada("Kernel version 3 successfully pushed.  Please check progress at ...") == 3
    assert kp.version_empujada("Kernel push error: Phone verification required to use GPU") is None
    assert kp.version_empujada("Kernel successfully pushed") == 0          # sin número: aceptado
    assert kp.version_empujada("") is None


def test_complete_inmediato_de_la_version_anterior_no_se_acepta_a_la_primera():
    # justo después del push Kaggle puede mostrar todavía el COMPLETE de la corrida anterior
    with tempfile.TemporaryDirectory() as d:
        cli = _CLIFalsa(["COMPLETE", "QUEUED", "RUNNING", "COMPLETE"], pedido_id="abc123")
        codigo, r = _lanzar(Path(d), cli)
        assert codigo == kp.EXIT_OK and r["intentos_status"] == 4
    with tempfile.TemporaryDirectory() as d:   # si nunca se ve correr, se acepta tras 4 consultas
        cli = _CLIFalsa(["COMPLETE"] * 4, pedido_id="abc123")
        codigo, r = _lanzar(Path(d), cli)
        assert codigo == kp.EXIT_OK and r["intentos_status"] == kp.SONDEOS_SIN_VER_CORRER


class _CLIFalsa:
    """Imita la salida REAL de `kaggle kernels push/status/output` (cli.py / kaggle_api_extended.py)."""

    def __init__(self, estados, deja_glb=True, push="ok", meta=None, version=4, status_rc=0, pedido_id=None):
        self.estados, self.deja_glb, self.push, self.meta = list(estados), deja_glb, push, meta
        self.version, self.status_rc, self.pedido_id = version, status_rc, pedido_id
        self.llamadas = []

    def __call__(self, cmd, **kw):
        self.llamadas.append(cmd)
        sub = cmd[2]
        if sub == "push":
            if self.push == "rechazado":     # la CLI real sale con 0 aunque Kaggle rechace el push
                return subprocess.CompletedProcess(cmd, 0, "Kernel push error: Phone verification required", "")
            if self.push == "rc1":
                return subprocess.CompletedProcess(cmd, 1, "", "401 Unauthorized")
            return subprocess.CompletedProcess(
                cmd, 0, f"Kernel version {self.version} successfully pushed.  Please check progress at ...", "")
        if sub == "status":
            if self.status_rc:
                return subprocess.CompletedProcess(cmd, self.status_rc, "", "404 Not Found")
            return subprocess.CompletedProcess(
                cmd, 0, f'{cmd[3]} has status "KernelWorkerStatus.{self.estados.pop(0)}"', "")
        if sub == "output":
            dest = Path(cmd[cmd.index("-p") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            if self.deja_glb:
                (dest / "propuesta.glb").write_bytes(b"glTF")
            meta = self.meta or {"estado": "OK", "caras": 500, "traza": "x", "pedido_id": self.pedido_id}
            (dest / "meta.json").write_text(json.dumps(meta))
            return subprocess.CompletedProcess(cmd, 0, "Output file downloaded", "")
        raise AssertionError(cmd)


def _kernel(d: Path, pedido_id="abc123") -> Path:
    k = d / "k"
    k.mkdir(exist_ok=True)
    (k / "kernel-metadata.json").write_text(json.dumps(kp.metadata_kernel("klymapo", "alth-meta-propuesta")))
    (k / "pedido.json").write_text(json.dumps({"pedido_id": pedido_id}))
    return k


def _lanzar(d, cli, minutos=90, pedido_id="abc123"):
    reloj = iter(range(0, 10**6, 30))
    return kp.lanzar(_kernel(d, pedido_id), d / "out", minutos=minutos, cada=30, ejecutar=cli,
                     dormir=lambda s: None, reloj=lambda: next(reloj))


def test_lanzar_ok_usa_la_version_empujada_y_el_tope_de_tiempo():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = _CLIFalsa(["QUEUED", "RUNNING", "COMPLETE"], pedido_id="abc123")
        codigo, r = _lanzar(d, cli, minutos=30)
        assert codigo == kp.EXIT_OK and r["estado"] == "OK" and r["version"] == 4
        assert (d / "out" / "propuesta.glb").exists() and "traza" not in r["meta"]
        push = cli.llamadas[0]
        assert push[:3] == ["kaggle", "kernels", "push"] and kp.ACELERADOR in push
        assert push[push.index("-t") + 1] == "1800"                       # tope en Kaggle = minutos
        assert all(c[3] == "klymapo/alth-meta-propuesta/4" for c in cli.llamadas[1:])   # status/output de v4


def test_push_rechazado_con_codigo_0_no_baja_la_salida_vieja():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "out").mkdir()
        (d / "out" / "propuesta.glb").write_bytes(b"VIEJO")                # de una corrida anterior
        cli = _CLIFalsa(["COMPLETE"] * 4, push="rechazado")
        codigo, r = _lanzar(d, cli)
        assert codigo == kp.EXIT_FALLO and r["estado"] == "PUSH_FALLIDO"
        assert len(cli.llamadas) == 1                                      # ni status ni output
    with tempfile.TemporaryDirectory() as d:
        assert _lanzar(Path(d), _CLIFalsa([], push="rc1"))[1]["estado"] == "PUSH_FALLIDO"


def test_salida_de_otro_pedido_se_rechaza_y_se_borra_la_vieja():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        codigo, r = _lanzar(d, _CLIFalsa(["RUNNING", "COMPLETE"], pedido_id="OTRO"))
        assert codigo == kp.EXIT_SIN_SALIDA and r["estado"] == "SALIDA_DE_OTRO_PEDIDO"
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "out").mkdir()
        (d / "out" / "propuesta.glb").write_bytes(b"VIEJO")
        codigo, r = _lanzar(d, _CLIFalsa(["RUNNING", "COMPLETE"], deja_glb=False, pedido_id="abc123"))
        assert codigo == kp.EXIT_SIN_SALIDA and r["estado"] == "SIN_PROPUESTA"
        assert not (d / "out" / "propuesta.glb").exists()


def test_lanzar_fallos():
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), _CLIFalsa(["RUNNING", "ERROR"], meta={"estado": "ERROR", "error": "CUDA"}))
        assert codigo == kp.EXIT_FALLO and r["estado"] == "KERNEL_FALLIDO" and r["meta"]["error"] == "CUDA"
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), _CLIFalsa(["RUNNING"] * 500), minutos=2)
        assert codigo == kp.EXIT_TIEMPO and r["estado"] == "TIEMPO_AGOTADO"
    with tempfile.TemporaryDirectory() as d:
        cli = _CLIFalsa([], status_rc=1)
        codigo, r = _lanzar(Path(d), cli)
        assert codigo == kp.EXIT_FALLO and r["estado"] == "STATUS_FALLIDO"
        assert r["intentos_status"] == kp.MAX_FALLOS_STATUS               # no espera los 90 minutos


def test_cli_que_no_responde_no_revienta():
    def colgada(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    with tempfile.TemporaryDirectory() as d:
        codigo, r = _lanzar(Path(d), colgada)
        assert codigo == kp.EXIT_FALLO and r["estado"] == "PUSH_FALLIDO"


def test_credenciales_token_nuevo_y_llave_legacy():
    import os
    claves = ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN", "KAGGLE_CONFIG_DIR")
    viejas = {k: os.environ.pop(k, None) for k in claves}
    try:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            os.environ["KAGGLE_CONFIG_DIR"] = str(d / "sin_config")
            img = _imagen(d)
            assert not kp.hay_credencial() and kp.credenciales() is None
            assert kp.main(["lanzar", str(img), "--nombre", "manzana"]) == kp.EXIT_CREDENCIALES
            # token nuevo sin usuario: hay credencial pero falta el usuario para el id del kernel
            os.environ["KAGGLE_API_TOKEN"] = "t"
            assert kp.hay_credencial() and kp.credenciales() is None
            assert kp.main(["lanzar", str(img), "--nombre", "manzana"]) == kp.EXIT_CREDENCIALES
            os.environ["KAGGLE_USERNAME"] = "klymapo"
            assert kp.credenciales() == "klymapo"
            # llave legacy
            os.environ.pop("KAGGLE_API_TOKEN")
            os.environ["KAGGLE_KEY"] = "k"
            assert kp.hay_credencial() and kp.credenciales() == "klymapo"
            # kaggle.json
            for k in ("KAGGLE_USERNAME", "KAGGLE_KEY"):
                os.environ.pop(k)
            (d / "sin_config").mkdir()
            (d / "sin_config" / "kaggle.json").write_text(json.dumps({"username": "klymapo", "key": "k"}))
            assert kp.hay_credencial() and kp.credenciales() == "klymapo"
            # armar no necesita credenciales; entrada inválida da código 2
            assert kp.main(["armar", str(img), "--nombre", "manzana", "--usuario", "klymapo",
                            "--carpeta", str(d / "k")]) == kp.EXIT_OK
            assert kp.main(["armar", str(d / "no_existe.png"), "--nombre", "x", "--usuario", "klymapo",
                            "--carpeta", str(d / "k2")]) == kp.EXIT_ENTRADA
    finally:
        for k, v in viejas.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_pedido_id_unico_y_en_el_script():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        a = kp.armar(_imagen(d), "m", d / "a", "klymapo")
        b = kp.armar(_imagen(d), "m", d / "b", "klymapo")
        assert a["pedido_id"] != b["pedido_id"] and len(a["pedido_id"]) == 16
        assert a["pedido_id"] in (d / "a" / "propuesta.py").read_text()


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
