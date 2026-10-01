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

# Versión fijada de TripoSG: último commit de main al 1 oct 2026 (licencia MIT).
TRIPOSG_REPO = "https://github.com/VAST-AI-Research/TripoSG.git"
TRIPOSG_COMMIT = "fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c"
TRIPOSG_PESOS = "VAST-AI/TripoSG"          # Hugging Face, licencia MIT
ACELERADOR = "NvidiaTeslaT4"                # TripoSG pide >= 8 GB de VRAM; una T4 tiene 16 GB
LADO_ENTRADA = 1024                          # lado mayor de la imagen que se manda
SLUG_DEFECTO = "alth-meta-propuesta"
SOMBRA_DESDE = 0.40      # la sombra del piso sólo se busca en el 60 % inferior de la figura
BORDE_SOMBRA_DE = 11.0   # contraste de borde (ΔE) bajo el cual una mancha gris es sombra, no pieza

EXIT_OK, EXIT_ENTRADA, EXIT_FALLO, EXIT_TIEMPO, EXIT_CREDENCIALES, EXIT_SIN_SALIDA = 0, 2, 5, 6, 7, 8


# ================================================================ 1. imagen
def quitar_sombra_pegada(rgb: np.ndarray, figura: np.ndarray, fondo_rgb) -> tuple[np.ndarray, float]:
    """Quita la sombra del piso que queda PEGADA a la figura (separar_figura sólo quita la que se
    desvanece hacia el fondo). Una sombra de render es gris neutro (mismo tinte que el fondo), un poco
    más oscura que él, en la parte baja, y no tiene figura debajo en su misma columna.

    Se conserva lo oscuro de verdad (zapatos negros: L muy bajo), cualquier gris que tenga figura
    debajo, y toda mancha gris de BORDE NÍTIDO: una sombra se desvanece hacia el fondo (contraste de
    borde ΔE ≈ 6-8 en las referencias del repo), una pieza real no (aro metálico de la lata: 16.8).
    Calibrado el 1 oct 2026 con joven-rubio, alastor, manzana y lata (infografías) y taza/lata (renders).
    Devuelve (figura_limpia, fracción quitada).
    """
    import reconocer
    from scipy import ndimage
    lab = reconocer._srgb_a_lab(rgb)
    lab_f = reconocer._srgb_a_lab(np.asarray(fondo_rgb, dtype=np.float64))
    croma = np.hypot(lab[..., 1] - lab_f[1], lab[..., 2] - lab_f[2])
    de = np.linalg.norm(lab - lab_f, axis=-1)
    L = lab[..., 0]
    filas = np.where(figura.any(1))[0]
    if len(filas) == 0:
        return figura, 0.0
    corte = filas[0] + SOMBRA_DESDE * (filas[-1] - filas[0])
    abajo = np.zeros_like(figura)
    abajo[int(corte):] = True
    candidata = figura & abajo & (croma < 8) & (L < lab_f[0] - 2) & (L > lab_f[0] - 50)
    solida = figura & ~candidata
    # ¿hay figura sólida más abajo en la misma columna? (acumulado desde abajo)
    hay_debajo = np.flipud(np.cumsum(np.flipud(solida), axis=0)) - solida > 0
    posible = candidata & ~hay_debajo
    fuera = ndimage.binary_dilation(~figura, iterations=2)
    et, n = ndimage.label(posible)
    sombra = np.zeros_like(figura)
    for i in range(1, n + 1):
        comp = et == i
        borde = comp & fuera
        if borde.any() and float(de[borde].mean()) < BORDE_SOMBRA_DE:
            sombra |= comp
    limpia = ndimage.binary_opening(figura & ~sombra, iterations=1)
    et, n = ndimage.label(limpia)
    if n > 1:
        tam = ndimage.sum(limpia, et, range(1, n + 1))
        limpia = et == (int(np.argmax(tam)) + 1)
    return limpia, float(sombra.sum() / max(figura.sum(), 1))


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
# TripoSG (MIT) en commit fijo; la imagen ya trae el fondo quitado en el canal alfa, así que
# NO se descarga ni se usa briaai/RMBG-1.4 (uso comercial con licencia de pago).
import base64, json, os, subprocess, sys, time, traceback
from pathlib import Path

T0 = time.time()
SALIDA = Path("/kaggle/working")
PARAMS = json.loads({params!r})
IMAGEN_B64 = {imagen_b64!r}
META = {{"estado": "ERROR", "parametros": PARAMS, "pasos": {{}}}}


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
    req = [r for r in req if r.strip() and not r.strip().startswith("numpy")]
    Path("/kaggle/tmp/req.txt").write_text("\\n".join(req) + "\\n")
    sh("pip install -q -r /kaggle/tmp/req.txt")
    paso("instalar", t)

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
    if isinstance(img, str) or img is None:
        raise RuntimeError(f"prepare_image rechazó la entrada: {{img}}")
    with torch.no_grad():
        out = pipe(image=img, generator=torch.Generator(device=pipe.device).manual_seed(PARAMS["semilla"]),
                   num_inference_steps=PARAMS["pasos"], guidance_scale=PARAMS["guia"]).samples[0]
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
    params = {"nombre": nombre, "caras": int(caras), "semilla": int(semilla), "pasos": int(pasos),
              "guia": float(guia), "repo": TRIPOSG_REPO, "commit": TRIPOSG_COMMIT, "pesos": TRIPOSG_PESOS}
    (carpeta / "kernel-metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    (carpeta / "propuesta.py").write_text(script_kernel(b64, params), encoding="utf-8")
    im.save(carpeta / "entrada.png")
    sha = hashlib.sha256(Path(imagen).read_bytes()).hexdigest()
    pedido = {"kernel": meta["id"], "nombre": nombre, "imagen": str(imagen), "imagen_sha256": sha,
              "recorte": recorte, "entrada": info, "parametros": params, "acelerador": ACELERADOR,
              "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (carpeta / "pedido.json").write_text(json.dumps(pedido, ensure_ascii=False, indent=2) + "\n")
    return pedido


# ================================================================ 3. lanzar y vigilar
def credenciales() -> str | None:
    """Usuario de Kaggle si hay credenciales (variables de entorno o ~/.kaggle/kaggle.json)."""
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return os.environ["KAGGLE_USERNAME"]
    archivo = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle")) / "kaggle.json"
    if archivo.exists():
        try:
            return json.loads(archivo.read_text()).get("username")
        except (json.JSONDecodeError, OSError):
            return None
    return None


def estado_de(texto: str) -> str:
    """Normaliza la salida de `kaggle kernels status` a: corriendo | completo | fallido | desconocido."""
    t = texto.lower()
    if "complete" in t:
        return "completo"
    if "error" in t or "fail" in t or "cancel" in t:
        return "fallido"
    if "running" in t or "queued" in t or "pending" in t:
        return "corriendo"
    return "desconocido"


def _kaggle(args: list[str], ejecutar=subprocess.run) -> subprocess.CompletedProcess:
    return ejecutar(["kaggle", *args], capture_output=True, text=True, timeout=600)


def lanzar(carpeta, salida, minutos: int = 90, cada: int = 30, ejecutar=subprocess.run,
           dormir=time.sleep, reloj=time.monotonic) -> tuple[int, dict]:
    """push → status (cada `cada` s, hasta `minutos`) → output. Devuelve (código, resumen)."""
    carpeta, salida = Path(carpeta), Path(salida)
    if shutil.which("kaggle") is None and ejecutar is subprocess.run:
        return EXIT_CREDENCIALES, {"estado": "SIN_CLI", "detalle": "instala la CLI: pip install kaggle"}
    kid = json.loads((carpeta / "kernel-metadata.json").read_text())["id"]
    resumen: dict = {"kernel": kid, "intentos_status": 0}
    r = _kaggle(["kernels", "push", "-p", str(carpeta), "--accelerator", ACELERADOR], ejecutar)
    resumen["push"] = (r.stdout + r.stderr).strip()[-1000:]
    if r.returncode != 0:
        resumen["estado"] = "PUSH_FALLIDO"
        return EXIT_FALLO, resumen
    inicio = reloj()
    estado = "corriendo"
    while estado in ("corriendo", "desconocido"):
        if reloj() - inicio > minutos * 60:
            resumen["estado"] = "TIEMPO_AGOTADO"
            return EXIT_TIEMPO, resumen
        dormir(cada)
        s = _kaggle(["kernels", "status", kid], ejecutar)
        resumen["intentos_status"] += 1
        resumen["ultimo_status"] = (s.stdout + s.stderr).strip()[-300:]
        estado = estado_de(resumen["ultimo_status"]) if s.returncode == 0 else "desconocido"
    salida.mkdir(parents=True, exist_ok=True)
    o = _kaggle(["kernels", "output", kid, "-p", str(salida)], ejecutar)
    resumen["output"] = (o.stdout + o.stderr).strip()[-500:]
    meta_ruta = salida / "meta.json"
    if meta_ruta.exists():
        try:
            resumen["meta"] = {k: v for k, v in json.loads(meta_ruta.read_text()).items() if k != "traza"}
        except json.JSONDecodeError:
            resumen["meta"] = {"estado": "META_ILEGIBLE"}
    resumen["minutos"] = round((reloj() - inicio) / 60, 1)
    if estado == "fallido":
        resumen["estado"] = "KERNEL_FALLIDO"
        return EXIT_FALLO, resumen
    if not (salida / "propuesta.glb").exists():
        resumen["estado"] = "SIN_PROPUESTA"
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
        if nombre == "lanzar":
            s.add_argument("--salida", default=None, help="por defecto propuestas/<nombre>")
            s.add_argument("--minutos", type=int, default=90)
        else:
            s.add_argument("--usuario", default=None, help="usuario de Kaggle (si no, el de las credenciales)")
    a = p.parse_args(argv)
    nid = re.sub(r"[^a-z0-9_]+", "_", a.nombre.lower()).strip("_") or "propuesta"
    carpeta = Path(a.carpeta or f".kaggle/{nid}/kernel")
    usuario = getattr(a, "usuario", None) or credenciales()
    if a.cmd == "lanzar" and not usuario:
        print("[kaggle] faltan credenciales: define KAGGLE_USERNAME y KAGGLE_KEY "
              "(Settings → Secrets → Actions) o ~/.kaggle/kaggle.json", file=sys.stderr)
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
