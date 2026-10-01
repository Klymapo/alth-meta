"""ALTH-META · proveedor de propuestas en Kaggle (GPU gratuita) con TripoSG.

Aprobado por el usuario el 1 oct 2026 como **proveedor opcional de propuestas**: genera una malla densa
a partir de la imagen de referencia en la GPU gratuita de Kaggle. Esa malla NO es un asset: entra a la
post-producción clásica (remesh, simetría, manos, flat shading, presupuesto de tris) y a la auditoría
visual como cualquier otro candidato, y no hereda ninguna aprobación.

Flujo (todo desatendido, desde un runner de GitHub Actions o una terminal):
  1. preparar  → quita el fondo con el código del repo (tools/reconocer.separar_figura) y escribe un PNG
                 RGBA. TripoSG usa ese canal alfa y **nunca llama a RMBG-1.4** (cuyo uso comercial exige
                 licencia de pago de BRIA). Por eso el kernel no descarga RMBG.
  2. armar     → carpeta con kernel-metadata.json + propuesta.py (la imagen va incrustada en base64).
  3. lanzar    → `kaggle kernels push`, vigila `kaggle kernels status` y baja `kaggle kernels output`.

Lo que corre dentro de Kaggle (propuesta.py, generado por `script_kernel`):
  clona TripoSG en un commit fijo (MIT, VAST-AI-Research) → instala dependencias → descarga los pesos
  VAST-AI/TripoSG (MIT) → genera → reduce a --caras con pymeshlab → escribe propuesta.glb + meta.json.

Credenciales: KAGGLE_USERNAME y KAGGLE_KEY (o ~/.kaggle/kaggle.json). Sin ellas sale con código 7.
Cuota: GPU gratuita de Kaggle (~30 h/semana según fuentes secundarias; la doc oficial no se pudo leer
el 1 oct 2026). Cada corrida reinstala dependencias y re-descarga pesos.

  python3 tools/kaggle_proveedor.py lanzar refs/personajes/joven-rubio.jpg --nombre theo --caras 20000
  python3 tools/kaggle_proveedor.py armar  refs/infografias/objeto-01-manzana.png --nombre manzana \
      --recorte 0.52,0.1,1,1 --carpeta /tmp/kernel        # solo arma, sin credenciales ni red

Códigos de salida: 0 ok · 2 entrada inválida · 5 el kernel falló en Kaggle · 6 se acabó el tiempo
· 7 faltan credenciales o la CLI de Kaggle · 8 el kernel terminó pero no dejó propuesta.glb
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mascaras import BORDE_SOMBRA_DE, SOMBRA_DESDE, quitar_sombra_pegada  # noqa: E402,F401  (compartido con la auditoría)

# Versión fijada de TripoSG: último commit de main al 1 oct 2026 (licencia MIT).
TRIPOSG_REPO = "https://github.com/VAST-AI-Research/TripoSG.git"
TRIPOSG_COMMIT = "fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c"
TRIPOSG_PESOS = "VAST-AI/TripoSG"          # Hugging Face, licencia MIT
ACELERADOR = "NvidiaTeslaT4"                # T4 ×2 (16 GB cada una); TripoSG pide >= 8 GB y usa una
LADO_ENTRADA = 1024                          # lado mayor de la imagen que se manda
SLUG_DEFECTO = "alth-meta-propuesta"
MAX_FALLOS_STATUS = 5    # `kaggle kernels status` fallando seguido (401/404…) → abortar, no esperar 90 min
SONDEOS_SIN_VER_CORRER = 4  # estado final sin haber visto QUEUED/RUNNING: puede ser de la versión anterior

EXIT_OK, EXIT_ENTRADA, EXIT_FALLO, EXIT_TIEMPO, EXIT_CREDENCIALES, EXIT_SIN_SALIDA = 0, 2, 5, 6, 7, 8


# ================================================================ 1. imagen
def preparar_imagen(ruta, recorte=None, lado: int = LADO_ENTRADA) -> tuple[Image.Image, dict]:
    """RGBA con el fondo y la sombra quitados por el código del repo (sin RMBG).

    TripoSG sólo usa el alfa si es 'válido': al menos 1 % de píxeles totalmente transparentes y 1 %
    totalmente opacos (`is_valid_alpha` en scripts/image_process.py). Un alfa binario lo cumple siempre
    que la figura no llene toda la imagen; se verifica aquí para no gastar cuota de GPU en balde.
    """
    import reconocer
    rgb = reconocer.cargar(ruta, recorte, lado=lado)
    figura, sep = reconocer.separar_figura(rgb)
    if figura.sum() < 200:
        raise ValueError("no encontré una figura sobre el fondo (¿fondo no liso? prueba con --recorte)")
    figura, sombra_pegada = quitar_sombra_pegada(rgb, figura, reconocer._fondo(rgb))
    sep["sombra_pegada_quitada"] = round(sombra_pegada, 4)
    alfa = np.where(figura, 255, 0).astype(np.uint8)
    transparente, opaco = float((alfa == 0).mean()), float((alfa == 255).mean())
    if transparente < 0.01 or opaco < 0.01:
        raise ValueError(f"alfa no válido para TripoSG (transparente {transparente:.1%}, opaco {opaco:.1%}); "
                         "la figura llena la imagen o es diminuta: ajusta --recorte")
    rgba = np.dstack([rgb.astype(np.uint8), alfa])
    info = {"ancho": int(rgb.shape[1]), "alto": int(rgb.shape[0]), "fraccion_figura": round(opaco, 4),
            "sombra_quitada": sep.get("sombra_quitada"), "sombra_pegada_quitada": sep["sombra_pegada_quitada"],
            "componentes": sep.get("componentes"),
            "metodo_fondo": "tools/reconocer.separar_figura (sin RMBG)"}
    return Image.fromarray(rgba, "RGBA"), info


def png_base64(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ================================================================ 2. kernel
def slug_valido(texto: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", texto.lower()).strip("-")
    if not 5 <= len(s) <= 50:
        raise ValueError(f"slug de kernel inválido: {texto!r} (5-50 caracteres a-z, 0-9, -)")
    return s


def metadata_kernel(usuario: str, slug: str) -> dict:
    """kernel-metadata.json según la CLI oficial (docs/kernels.md de Kaggle/kaggle-cli)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,50}", usuario or ""):
        raise ValueError(f"usuario de Kaggle inválido: {usuario!r}")
    slug = slug_valido(slug)
    return {"id": f"{usuario}/{slug}", "title": slug, "code_file": "propuesta.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
            "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}


def script_kernel(imagen_b64: str, parametros: dict) -> str:
    """Código que corre dentro de Kaggle. Sin RMBG: usa el alfa que ya trae la imagen."""
    params = json.dumps(parametros, ensure_ascii=False, sort_keys=True)
    return f'''# Generado por tools/kaggle_proveedor.py (ALTH-META). No editar a mano.
# TripoSG (MIT) en commit fijo. Dos exclusiones por licencia:
#  - briaai/RMBG-1.4 (uso comercial con licencia de pago): la imagen ya trae el fondo quitado en el
#    canal alfa, así que prepare_image no la llama y aquí no se descarga.
#  - diso (CC BY-NC 4.0, no comercial): solo lo usa el "flash decoder"; se reemplaza por un módulo vacío
#    y se genera con use_flash_decoder=False (extracción jerárquica con skimage.marching_cubes).
import base64, json, os, subprocess, sys, time, traceback, types
from pathlib import Path

T0 = time.time()
SALIDA = Path("/kaggle/working")
PARAMS = json.loads({params!r})
IMAGEN_B64 = {imagen_b64!r}
META = {{"estado": "ERROR", "pedido_id": PARAMS["pedido_id"], "parametros": PARAMS, "pasos": {{}}}}


def paso(nombre, t):
    META["pasos"][nombre] = round(time.time() - t, 1)


def sh(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


try:
    t = time.time()
    os.makedirs("/kaggle/tmp", exist_ok=True)
    sh(f"git clone -q {{PARAMS['repo']}} /kaggle/tmp/TripoSG")
    sh(f"git -C /kaggle/tmp/TripoSG checkout -q {{PARAMS['commit']}}")
    # numpy==1.22.3 del requirements no instala en el Python de Kaggle: se respeta el numpy del entorno.
    req = Path("/kaggle/tmp/TripoSG/requirements.txt").read_text().splitlines()
    req = [r for r in req if r.strip() and not r.strip().startswith(("numpy", "diso"))]
    Path("/kaggle/tmp/req.txt").write_text("\\n".join(req) + "\\n")
    # Restringe a lo que ya trae la imagen de Kaggle para no arrastrar actualizaciones de torch/numpy.
    sh("pip freeze | grep -v ' @ ' > /kaggle/tmp/base.txt || true")
    try:
        sh("pip install -q -r /kaggle/tmp/req.txt -c /kaggle/tmp/base.txt")
        META["instalacion"] = "restringida a la imagen de Kaggle"
    except subprocess.CalledProcessError:
        # alguna dependencia pide una versión distinta a la que trae Kaggle: se instala sin restricción
        sh("pip install -q -r /kaggle/tmp/req.txt")
        META["instalacion"] = "sin restricción (la restringida falló)"
    sh("pip freeze > /kaggle/working/pip_freeze.txt")
    paso("instalar", t)

    # Sustituto vacío de diso (no comercial): si algo intentara usarlo, falla con un mensaje claro.
    class _SinDiso:
        def __init__(self, *a, **k):
            raise RuntimeError("diso (CC BY-NC) está excluido; usa use_flash_decoder=False")
    sys.modules["diso"] = types.SimpleNamespace(DiffDMC=_SinDiso)

    sys.path.insert(0, "/kaggle/tmp/TripoSG")
    sys.path.insert(0, "/kaggle/tmp/TripoSG/scripts")
    import numpy as np, torch, trimesh, pymeshlab
    from huggingface_hub import snapshot_download
    from triposg.pipelines.pipeline_triposg import TripoSGPipeline
    from image_process import prepare_image

    t = time.time()
    pesos = snapshot_download(repo_id=PARAMS["pesos"], local_dir="/kaggle/tmp/pesos_triposg")
    paso("descargar_pesos", t)

    entrada = Path("/kaggle/tmp/entrada.png")
    entrada.write_bytes(base64.b64decode(IMAGEN_B64))

    t = time.time()
    pipe = TripoSGPipeline.from_pretrained(pesos).to("cuda", torch.float16)
    img = prepare_image(str(entrada), bg_color=np.array([1.0, 1.0, 1.0]), rmbg_net=None)
    with torch.no_grad():
        out = pipe(image=img, generator=torch.Generator(device=pipe.device).manual_seed(PARAMS["semilla"]),
                   num_inference_steps=PARAMS["pasos"], guidance_scale=PARAMS["guia"],
                   use_flash_decoder=False).samples[0]
    malla = trimesh.Trimesh(out[0].astype(np.float32), np.ascontiguousarray(out[1]))
    META["caras_crudas"] = int(malla.faces.shape[0])
    paso("generar", t)

    t = time.time()
    if PARAMS["caras"] > 0 and malla.faces.shape[0] > PARAMS["caras"]:
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(vertex_matrix=malla.vertices, face_matrix=malla.faces))
        ms.meshing_merge_close_vertices()
        ms.meshing_decimation_quadric_edge_collapse(targetfacenum=PARAMS["caras"])
        m = ms.current_mesh()
        malla = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix())
    malla.export(SALIDA / "propuesta.glb")
    paso("reducir_exportar", t)

    META.update(estado="OK", caras=int(malla.faces.shape[0]), vertices=int(malla.vertices.shape[0]),
                watertight=bool(malla.is_watertight), bbox=malla.bounds.round(5).tolist(),
                gpu=torch.cuda.get_device_name(0), torch=torch.__version__)
except Exception as e:  # el error queda en meta.json y el kernel sale con código 1
    META["error"] = f"{{type(e).__name__}}: {{e}}"
    META["traza"] = traceback.format_exc()[-4000:]
finally:
    META["segundos"] = round(time.time() - T0, 1)
    (SALIDA / "meta.json").write_text(json.dumps(META, ensure_ascii=False, indent=2))
    print(json.dumps({{k: v for k, v in META.items() if k != "traza"}}, ensure_ascii=False, indent=2))

if META["estado"] != "OK":
    sys.exit(1)
'''


def armar(imagen, nombre: str, carpeta, usuario: str, slug: str = SLUG_DEFECTO, caras: int = 20000,
          semilla: int = 42, pasos: int = 50, guia: float = 7.0, recorte=None) -> dict:
    """Escribe la carpeta del kernel. No necesita red ni credenciales."""
    if caras != -1 and caras < 100:
        raise ValueError("caras debe ser -1 (sin reducir) o >= 100")
    if not 1 <= pasos <= 200:
        raise ValueError("pasos fuera de rango (1-200)")
    im, info = preparar_imagen(imagen, recorte)
    b64 = png_base64(im)
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    meta = metadata_kernel(usuario, slug)
    sha = hashlib.sha256(Path(imagen).read_bytes()).hexdigest()
    fecha = datetime.now(timezone.utc).isoformat(timespec="seconds")
    params = {"nombre": nombre, "caras": int(caras), "semilla": int(semilla), "pasos": int(pasos),
              "guia": float(guia), "repo": TRIPOSG_REPO, "commit": TRIPOSG_COMMIT, "pesos": TRIPOSG_PESOS}
    # Identificador único de ESTE pedido: el kernel lo copia a meta.json y lanzar() lo exige al bajar,
    # para no confundir nunca la salida de una corrida anterior con la nueva.
    params["pedido_id"] = hashlib.sha256(
        (sha + json.dumps(params, sort_keys=True) + fecha + os.urandom(8).hex()).encode()).hexdigest()[:16]
    (carpeta / "kernel-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    (carpeta / "propuesta.py").write_text(script_kernel(b64, params), encoding="utf-8")
    im.save(carpeta / "entrada.png")
    pedido = {"kernel": meta["id"], "nombre": nombre, "imagen": str(imagen), "imagen_sha256": sha,
              "recorte": recorte, "entrada": info, "parametros": params, "pedido_id": params["pedido_id"],
              "acelerador": ACELERADOR, "fecha": fecha}
    (carpeta / "pedido.json").write_text(json.dumps(pedido, ensure_ascii=False, indent=2) + "\n")
    return pedido


# ================================================================ 3. lanzar y vigilar
def credenciales() -> str | None:
    """Usuario de Kaggle si hay alguna credencial válida para la CLI. Acepta las dos formas vigentes:

    - token nuevo ("Generate New Token" en Kaggle): KAGGLE_API_TOKEN o ~/.kaggle/access_token. El token no
      trae el usuario, así que hace falta KAGGLE_USERNAME (o --usuario) para armar el id del kernel;
    - llave legacy ("Create Legacy API Key"): KAGGLE_USERNAME + KAGGLE_KEY o ~/.kaggle/kaggle.json.
    """
    dir_conf = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))
    usuario = os.environ.get("KAGGLE_USERNAME") or None
    if os.environ.get("KAGGLE_API_TOKEN") or (Path.home() / ".kaggle" / "access_token").exists():
        return usuario
    if usuario and os.environ.get("KAGGLE_KEY"):
        return usuario
    archivo = dir_conf / "kaggle.json"
    if archivo.exists():
        try:
            return json.loads(archivo.read_text()).get("username") or usuario
        except (json.JSONDecodeError, OSError):
            return None
    return None


def hay_credencial() -> bool:
    """¿La CLI de Kaggle tiene con qué autenticarse? (token nuevo, llave legacy o kaggle.json)."""
    dir_conf = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))
    return bool(os.environ.get("KAGGLE_API_TOKEN") or (Path.home() / ".kaggle" / "access_token").exists()
                or (os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"))
                or (dir_conf / "kaggle.json").exists())


def estado_de(texto: str) -> str:
    """Normaliza la salida de `kaggle kernels status` a: corriendo | completo | fallido | desconocido.

    La CLI imprime `owner/slug has status "KernelWorkerStatus.COMPLETE"` y, si falló, una línea
    `Failure message: "..."`. Sólo se mira el estado entrecomillado, nunca el id ni el mensaje.
    Estados de la CLI: QUEUED, RUNNING, COMPLETE, ERROR, CANCEL_REQUESTED, CANCEL_ACKNOWLEDGED, NEW_SCRIPT.
    """
    m = re.search(r'has status "([^"]+)"', texto)
    if not m:
        return "desconocido"
    t = m.group(1).lower().rsplit(".", 1)[-1]
    if t == "complete":
        return "completo"
    if t in ("error", "cancel_requested", "cancel_acknowledged") or "cancel" in t:
        return "fallido"
    if t in ("queued", "running", "new_script"):
        return "corriendo"
    return "desconocido"


def version_empujada(texto: str) -> int | None:
    """Número de versión si el push se aceptó (0 si la CLI no lo dio), None si se rechazó.
    Ojo: un push rechazado imprime `Kernel push error: ...` y la CLI sale con código 0 igual."""
    if "push error" in texto.lower():
        return None
    m = re.search(r"Kernel version (\d+) successfully pushed", texto)
    if m:
        return int(m.group(1))
    return 0 if "successfully pushed" in texto.lower() else None


def _kaggle(args: list[str], ejecutar=subprocess.run, timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        return ejecutar(["kaggle", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["kaggle", *args], 124, "", f"la CLI no respondió en {timeout} s")


def lanzar(carpeta, salida, minutos: int = 90, cada: int = 30, ejecutar=subprocess.run,
           dormir=time.sleep, reloj=time.monotonic) -> tuple[int, dict]:
    """push → status (cada `cada` s, hasta `minutos`) → output. Devuelve (código, resumen)."""
    carpeta, salida = Path(carpeta), Path(salida)
    if shutil.which("kaggle") is None and ejecutar is subprocess.run:
        return EXIT_CREDENCIALES, {"estado": "SIN_CLI", "detalle": "instala la CLI: pip install kaggle"}
    kid = json.loads((carpeta / "kernel-metadata.json").read_text())["id"]
    pedido_id = json.loads((carpeta / "pedido.json").read_text()).get("pedido_id") \
        if (carpeta / "pedido.json").exists() else None
    resumen: dict = {"kernel": kid, "pedido_id": pedido_id, "intentos_status": 0}
    # -t: tope de la sesión EN Kaggle (la CLI no tiene comando para cancelar; sin esto, si aquí se agota
    # el tiempo, la GPU seguiría corriendo y gastando cuota).
    r = _kaggle(["kernels", "push", "-p", str(carpeta), "--accelerator", ACELERADOR,
                 "-t", str(int(minutos * 60))], ejecutar)
    texto_push = (r.stdout + r.stderr).strip()
    resumen["push"] = texto_push[-1000:]
    version = version_empujada(texto_push) if r.returncode == 0 else None
    if version is None:
        resumen["estado"] = "PUSH_FALLIDO"
        return EXIT_FALLO, resumen
    # La CLI 2.2.x acepta owner/slug/N pero consulta la ÚLTIMA versión igual; la protección real contra
    # tomar una salida vieja es el pedido_id (abajo) y no aceptar un estado final sin haber visto correr.
    kid_v = f"{kid}/{version}" if version else kid
    resumen["version"] = version or None
    inicio = reloj()
    estado, fallos_seguidos, visto_correr = "corriendo", 0, False
    while estado in ("corriendo", "desconocido") or (
            not visto_correr and resumen["intentos_status"] < SONDEOS_SIN_VER_CORRER):
        if reloj() - inicio > minutos * 60:
            resumen["estado"] = "TIEMPO_AGOTADO"
            return EXIT_TIEMPO, resumen
        dormir(cada)
        s = _kaggle(["kernels", "status", kid_v], ejecutar)
        resumen["intentos_status"] += 1
        resumen["ultimo_status"] = (s.stdout + s.stderr).strip()[-300:]
        if s.returncode != 0:
            fallos_seguidos += 1
            if fallos_seguidos >= MAX_FALLOS_STATUS:
                resumen["estado"] = "STATUS_FALLIDO"
                return EXIT_FALLO, resumen
            estado = "desconocido"
            continue
        fallos_seguidos = 0
        estado = estado_de(resumen["ultimo_status"])
        visto_correr = visto_correr or estado == "corriendo"
    if salida.exists():                 # nunca mezclar con la salida de una corrida anterior
        for viejo in ("propuesta.glb", "meta.json", "pip_freeze.txt"):
            (salida / viejo).unlink(missing_ok=True)
    salida.mkdir(parents=True, exist_ok=True)
    o = _kaggle(["kernels", "output", kid_v, "-p", str(salida), "-o"], ejecutar)
    resumen["output"] = (o.stdout + o.stderr).strip()[-500:]
    meta_ruta = salida / "meta.json"
    meta = None
    if meta_ruta.exists():
        try:
            meta = json.loads(meta_ruta.read_text())
            resumen["meta"] = {k: v for k, v in meta.items() if k != "traza"}
        except json.JSONDecodeError:
            resumen["meta"] = {"estado": "META_ILEGIBLE"}
    resumen["minutos"] = round((reloj() - inicio) / 60, 1)
    if estado == "fallido":
        resumen["estado"] = "KERNEL_FALLIDO"
        return EXIT_FALLO, resumen
    if not (salida / "propuesta.glb").exists() or not meta:
        resumen["estado"] = "SIN_PROPUESTA"
        return EXIT_SIN_SALIDA, resumen
    if pedido_id and meta.get("pedido_id") != pedido_id:
        resumen["estado"] = "SALIDA_DE_OTRO_PEDIDO"
        return EXIT_SIN_SALIDA, resumen
    resumen["estado"] = "OK"
    return EXIT_OK, resumen


# ================================================================ CLI
def _recorte(txt):
    if not txt:
        return None
    v = [float(x) for x in txt.split(",")]
    if len(v) != 4 or not all(0 <= x <= 1 for x in v) or v[0] >= v[2] or v[1] >= v[3]:
        raise ValueError("--recorte es x0,y0,x1,y1 en fracciones 0-1")
    return v


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Propuestas de malla con TripoSG en la GPU gratuita de Kaggle.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("armar", "lanzar"):
        s = sub.add_parser(nombre)
        s.add_argument("imagen")
        s.add_argument("--nombre", required=True)
        s.add_argument("--caras", type=int, default=20000, help="caras tras reducir (-1 = sin reducir)")
        s.add_argument("--semilla", type=int, default=42)
        s.add_argument("--pasos", type=int, default=50)
        s.add_argument("--recorte", default=None)
        s.add_argument("--slug", default=SLUG_DEFECTO)
        s.add_argument("--carpeta", default=None, help="carpeta del kernel (por defecto .kaggle/<nombre>/kernel)")
        s.add_argument("--usuario", default=None, help="usuario de Kaggle (si no, KAGGLE_USERNAME o kaggle.json)")
        if nombre == "lanzar":
            s.add_argument("--salida", default=None, help="por defecto propuestas/<nombre>")
            s.add_argument("--minutos", type=int, default=90)
    a = p.parse_args(argv)
    nid = re.sub(r"[^a-z0-9_]+", "_", a.nombre.lower()).strip("_") or "propuesta"
    carpeta = Path(a.carpeta or f".kaggle/{nid}/kernel")
    usuario = a.usuario or credenciales()
    if a.cmd == "lanzar" and not (usuario and hay_credencial()):
        print("[kaggle] faltan credenciales: KAGGLE_USERNAME + KAGGLE_API_TOKEN (token nuevo) o "
              "KAGGLE_USERNAME + KAGGLE_KEY (llave legacy), o ~/.kaggle/kaggle.json. Ver docs/KAGGLE.md",
              file=sys.stderr)
        return EXIT_CREDENCIALES
    try:
        pedido = armar(a.imagen, a.nombre, carpeta, usuario or "usuario-sin-definir", a.slug, a.caras,
                       a.semilla, a.pasos, recorte=_recorte(a.recorte))
    except (ValueError, FileNotFoundError) as e:
        print(f"[kaggle] {e}", file=sys.stderr)
        return EXIT_ENTRADA
    print(f"[kaggle] kernel armado en {carpeta} ({pedido['kernel']}, {pedido['parametros']['caras']} caras)")
    if a.cmd == "armar":
        return EXIT_OK
    salida = Path(a.salida or f"propuestas/{nid}")
    codigo, resumen = lanzar(carpeta, salida, a.minutos)
    resumen["pedido"] = pedido
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n")
    shutil.copy(carpeta / "entrada.png", salida / "entrada.png")
    print(json.dumps({k: v for k, v in resumen.items() if k != "pedido"}, ensure_ascii=False, indent=2))
    return codigo


if __name__ == "__main__":
    sys.exit(main())
