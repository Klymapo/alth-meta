"""ALTH-META · bucle de modelado con CUALQUIER modelo de IA (no depende de Claude).

El ciclo es: correr build.py en Blender → leer hoja, verificación y silueta → pedirle al modelo el
build.py corregido → repetir. Tres formas de usarlo:

  # 1) Automático, con cualquier API compatible con OpenAI (Ollama local, DeepSeek, Gemini, OpenRouter, Groq…)
  python3 tools/bucle.py correr assets/pruebas/joven_rubio_v1 --proveedor ollama --vueltas 4

  # 2) Manual, sin API ni gasto: arma un paquete (prompt.md + imágenes) para pegar en cualquier chat gratis
  python3 tools/bucle.py paquete assets/pruebas/joven_rubio_v1
  python3 tools/bucle.py aplicar assets/pruebas/joven_rubio_v1 respuesta.md     # pega aquí lo que contestó

  # 3) Solo medir la silueta del último render contra la referencia
  python3 tools/bucle.py medir assets/pruebas/joven_rubio_v1

Opciones comunes:
  --ref refs/...png         referencia (si no, la primera ruta refs/… que aparezca en spec.json → "referencia")
  --recorte x0,y0,x1,y1     recorte de la referencia en fracciones (p. ej. 0,0,0.5,0.5 = cuadrante de frente)
  --vista frente            vista del render que se compara en silueta
  --editable alth/pelo.py   archivos extra que el modelo puede reescribir (build.py siempre lo es)
  --nota "texto"            indicación tuya para el modelo ("céntrate en el pelo")

Todo esto también se puede fijar en el spec.json del asset, en un bloque opcional:
  "bucle": {"ref": "refs/…", "recorte": [0, 0, 0.5, 0.5], "vista": "frente", "editables": ["alth/pelo.py"], "nota": "…"}

Configuración del modelo (argumentos o variables de entorno):
  --proveedor / ALTH_PROVEEDOR   ollama | deepseek | gemini | openrouter | groq | personalizado
  --modelo    / ALTH_MODELO      nombre del modelo (cada proveedor trae uno por defecto; revisa el vigente)
  ALTH_API_BASE, ALTH_API_KEY    para "personalizado" o para sobrescribir
  --sin-vision / ALTH_VISION=0   para modelos que no aceptan imágenes (reciben solo números y texto)

El bucle NUNCA corre el modo final ni exporta: al terminar deja build.py con la última versión que
corrió bien y un resumen en renders/<asset>/bucle/. La aprobación sigue siendo tuya.
"""
from __future__ import annotations

import argparse
import ast
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "alth"))
import silueta  # noqa: E402  (módulo puro, sin bpy)

PROVEEDORES = {
    "ollama": {"base": "http://localhost:11434/v1", "clave_env": None, "modelo": "qwen2.5vl:7b", "vision": True},
    "deepseek": {"base": "https://api.deepseek.com/v1", "clave_env": "DEEPSEEK_API_KEY",
                 "modelo": "deepseek-chat", "vision": False},
    "gemini": {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "clave_env": "GEMINI_API_KEY",
               "modelo": "gemini-3.8-flash", "vision": True},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "clave_env": "OPENROUTER_API_KEY",
                   "modelo": None, "vision": True},
    "groq": {"base": "https://api.groq.com/openai/v1", "clave_env": "GROQ_API_KEY", "modelo": None, "vision": False},
    "personalizado": {"base": None, "clave_env": "ALTH_API_KEY", "modelo": None, "vision": True},
}

# Guardia, NO un sandbox: frena lo obvio. El aislamiento real es correr el bucle en GitHub Actions.
PROHIBIDO = ["subprocess", "os.system", "os.popen", "os.remove", "os.unlink", "rmtree", "socket",
             "urllib", "requests", "http.client", "eval(", "exec(", "__import__", "shutil.move"]

LADO_MAX_IMG = 1024
COLA_SALIDA = 60


# ---------------------------------------------------------------- utilidades puras (probadas en tests/)
def extraer_archivos(respuesta: str) -> dict[str, str]:
    """Bloques `### ARCHIVO: ruta` + ```python … ```. Si no hay encabezados y hay un solo bloque de
    código, se toma como build.py (clave "")."""
    archivos = {}
    patron = re.compile(r"###\s*ARCHIVO:\s*`?([^\n`]+?)`?\s*\n+```(?:python|py)?\s*\n(.*?)\n```", re.S)
    for ruta, codigo in patron.findall(respuesta):
        archivos[ruta.strip()] = codigo.rstrip() + "\n"
    if not archivos:
        bloques = re.findall(r"```(?:python|py)?\s*\n(.*?)\n```", respuesta, re.S)
        if len(bloques) >= 1:
            archivos[""] = max(bloques, key=len).rstrip() + "\n"
    return archivos


def extraer_campo(respuesta: str, campo: str) -> str:
    m = re.search(rf"^\s*\**{campo}\**\s*:\s*(.+)$", respuesta, re.M | re.I)
    return m.group(1).strip() if m else ""


def revisar_codigo(codigo: str) -> list[str]:
    """Problemas que impiden correr el código: sintaxis y usos prohibidos."""
    problemas = []
    try:
        ast.parse(codigo)
    except SyntaxError as e:
        problemas.append(f"error de sintaxis en la línea {e.lineno}: {e.msg}")
    for p in PROHIBIDO:
        if p in codigo:
            problemas.append(f"usa algo prohibido: {p}")
    return problemas


def api_alth(modulos: list[Path]) -> str:
    """Firmas y primera línea del docstring de cada función pública, leídas con ast (sin importar bpy)."""
    lineas = []
    for ruta in modulos:
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        prefijo = "alth" if ruta.name == "__init__.py" else f"alth.{ruta.stem}"
        for nodo in arbol.body:
            if isinstance(nodo, ast.FunctionDef) and not nodo.name.startswith("_"):
                args = ast.unparse(nodo.args)
                doc = (ast.get_docstring(nodo) or "").strip().split("\n")[0]
                lineas.append(f"- {prefijo}.{nodo.name}({args})" + (f" — {doc}" if doc else ""))
    return "\n".join(lineas)


def seccion_md(texto: str, titulo: str) -> str:
    """Una sección `## titulo` de un markdown, hasta la siguiente `## `."""
    m = re.search(rf"^## {re.escape(titulo)}\s*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    return m.group(1).strip() if m else ""


def ref_de_spec(spec: dict) -> str | None:
    m = re.search(r"refs/[\w\-/\.]+\.(?:png|jpe?g)", json.dumps(spec, ensure_ascii=False))
    return m.group(0) if m else None


def medidas_compactas(medidas: dict, max_piezas: int = 60) -> str:
    filas = []
    for nombre, m in list(medidas.items())[:max_piezas]:
        filas.append(f"{nombre}: W {m.get('W', m.get('w', '?'))} · D {m.get('D', m.get('d', '?'))} · "
                     f"H {m.get('H', m.get('h', '?'))} · tris {m.get('tris_sin_modificadores', m.get('tris', '?'))}")
    if len(medidas) > max_piezas:
        filas.append(f"… y {len(medidas) - max_piezas} piezas más")
    return "\n".join(filas)


# ---------------------------------------------------------------- estado del asset
class Asset:
    def __init__(self, ruta: str, args):
        p = Path(ruta)
        if not p.is_absolute():
            p = RAIZ / p if (RAIZ / p).exists() else RAIZ / "assets" / ruta
        self.dir = p.resolve()
        self.build = self.dir / "build.py"
        self.spec_path = self.dir / "spec.json"
        if not self.build.exists():
            sys.exit(f"[bucle] no existe {self.build}")
        self.spec = json.loads(self.spec_path.read_text(encoding="utf-8")) if self.spec_path.exists() else {}
        conf = self.spec.get("bucle", {})
        self.nombre = self.dir.name
        self.ref = args.ref or conf.get("ref") or ref_de_spec(self.spec)
        rec = args.recorte or conf.get("recorte")
        self.recorte = tuple(float(x) for x in rec.split(",")) if isinstance(rec, str) else (tuple(rec) if rec else None)
        self.vista = args.vista or conf.get("vista", "frente")
        self.nota = args.nota or conf.get("nota", "")
        extra = list(args.editable or []) + list(conf.get("editables", []))
        self.editables = [self.rel(self.build)] + [e for e in dict.fromkeys(extra) if e != self.rel(self.build)]
        self.trabajo = RAIZ / "renders" / self.nombre / "bucle"
        self.trabajo.mkdir(parents=True, exist_ok=True)
        self.historial_path = self.trabajo / "historial.json"
        self.historial = (json.loads(self.historial_path.read_text(encoding="utf-8"))
                          if self.historial_path.exists() else [])

    @staticmethod
    def rel(p: Path) -> str:
        return str(Path(p).resolve().relative_to(RAIZ))

    def guardar_historial(self):
        self.historial_path.write_text(json.dumps(self.historial, indent=2, ensure_ascii=False), encoding="utf-8")

    def modulos_usados(self) -> list[Path]:
        """alth/__init__.py + los submódulos de alth que cualquier editable importe."""
        texto = "\n".join((RAIZ / e).read_text(encoding="utf-8") for e in self.editables if (RAIZ / e).exists())
        mods = [RAIZ / "alth" / "__init__.py"]
        for sub in sorted((RAIZ / "alth").glob("*.py")):
            if sub.name in ("__init__.py", "verificacion.py", "silueta.py"):
                continue
            if re.search(rf"\b{sub.stem}\b", texto):
                mods.append(sub)
        return mods


# ---------------------------------------------------------------- correr Blender y medir
def correr_build(asset: Asset, timeout: int) -> dict:
    """Corre build.py en modo iteración. Devuelve salida, código y el reporte.json nuevo (si hubo)."""
    exe = os.environ.get("ALTH_PYTHON") or shutil.which("alth-python")
    if not exe:
        return {"ok": False, "salida": "No encontré `alth-python`. Corre primero: bash tools/ensure_blender.sh",
                "reporte": None, "carpeta": None}
    antes = {p: p.stat().st_mtime for p in (RAIZ / "renders").rglob("reporte.json")} \
        if (RAIZ / "renders").exists() else {}
    try:
        r = subprocess.run([exe, str(asset.build)], cwd=RAIZ, capture_output=True, text=True, timeout=timeout)
        salida, codigo = (r.stdout + "\n" + r.stderr).strip(), r.returncode
    except subprocess.TimeoutExpired:
        salida, codigo = f"El script tardó más de {timeout} s y se detuvo.", -1
    reporte, carpeta = None, None
    candidatos = [p for p in (RAIZ / "renders").rglob("reporte.json") if antes.get(p) != p.stat().st_mtime]
    if candidatos:
        rp = max(candidatos, key=lambda p: p.stat().st_mtime)
        reporte, carpeta = json.loads(rp.read_text(encoding="utf-8")), rp.parent
    return {"ok": codigo == 0 and reporte is not None, "codigo": codigo,
            "salida": "\n".join(salida.splitlines()[-COLA_SALIDA:]), "reporte": reporte, "carpeta": carpeta}


def medir_silueta(asset: Asset, resultado: dict, destino: Path) -> dict | None:
    rep = resultado.get("reporte")
    if not rep or not asset.ref:
        return None
    vista = rep.get("vistas", {}).get(asset.vista)
    ref = RAIZ / asset.ref
    if not vista or not ref.exists():
        return None
    try:
        return silueta.comparar_archivos(vista, ref, recorte_ref=asset.recorte, superposicion=destino)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e), "frases": [f"No se pudo medir la silueta: {e}"], "iou": None}


def resumen_verificacion(rep: dict | None) -> str:
    if not rep:
        return "Sin reporte (el script no llegó a renderizar)."
    v = rep.get("verificacion")
    if not v:
        return "El build no pidió verificación (falta asset=… en alth.revisar)."
    if v.get("error"):
        return f"La verificación falló: {v['error']}"
    lineas = [f"VERIFICACIÓN {'OK' if v.get('ok') else 'CON FALLAS'}"]
    for c in v.get("checks", []):
        if not c.get("ok", True):
            lineas.append(f"- FALLA {c.get('check', '')}: {c.get('detalle', '')}")
    return "\n".join(lineas)


# ---------------------------------------------------------------- prompt
def imagen_dataurl(ruta: Path, recorte=None) -> str:
    from PIL import Image
    im = Image.open(ruta).convert("RGB")
    if recorte:
        w, h = im.size
        im = im.crop((int(recorte[0] * w), int(recorte[1] * h), int(recorte[2] * w), int(recorte[3] * h)))
    im.thumbnail((LADO_MAX_IMG, LADO_MAX_IMG))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def texto_sistema() -> str:
    base = (RAIZ / "tools" / "bucle_sistema.md").read_text(encoding="utf-8")
    conv = seccion_md((RAIZ / "CLAUDE.md").read_text(encoding="utf-8"), "Convenciones")
    return base + "\n\n## Convenciones del repositorio (de CLAUDE.md)\n\n" + conv


def armar_prompt(asset: Asset, resultado: dict, sil: dict | None, vuelta: int, total: int | None = None) -> str:
    spec_global = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))
    partes = [f"# Vuelta {vuelta}{f' de {total}' if total else ''} · asset `{asset.rel(asset.dir)}`"]
    if asset.nota:
        partes.append(f"## Indicación del humano\n{asset.nota}")
    partes.append("## Objetivo (spec.json del asset)\n```json\n"
                  + json.dumps(asset.spec, indent=1, ensure_ascii=False) + "\n```")
    partes.append(f"## Referencia\n{asset.ref or 'sin imagen de referencia'}"
                  + (f" (recorte {asset.recorte})" if asset.recorte else ""))
    partes.append("## Paleta permitida\n```json\n" + json.dumps(spec_global["paleta"], ensure_ascii=False) + "\n```")
    if asset.historial:
        h = [f"- v{e['vuelta']}: {e.get('cambios') or '(sin nota)'} → build {'OK' if e.get('build_ok') else 'FALLÓ'}"
             f", IoU {e.get('iou')}" for e in asset.historial[-8:]]
        partes.append("## Lo que ya se intentó\n" + "\n".join(h))
    partes.append("## Resultado de la última corrida")
    if not resultado.get("ok"):
        partes.append("EL SCRIPT FALLÓ. Salida:\n```\n" + resultado.get("salida", "") + "\n```")
    else:
        rep = resultado["reporte"]
        partes.append(resumen_verificacion(rep))
        partes.append("Medidas por pieza (mm):\n```\n" + medidas_compactas(rep.get("medidas_mm", {})) + "\n```")
        partes.append("Salida (últimas líneas):\n```\n" + resultado.get("salida", "")[-2500:] + "\n```")
    if sil:
        partes.append(f"## Silueta de la vista `{asset.vista}` contra la referencia\n" + silueta.texto(sil))
    partes.append("## Archivos editables (devuélvelos COMPLETOS si los cambias)")
    for e in asset.editables:
        partes.append(f"### {e}\n```python\n{(RAIZ / e).read_text(encoding='utf-8')}\n```")
    solo_lectura = [m for m in asset.modulos_usados()
                    if asset.rel(m) not in asset.editables and m.name != "__init__.py"]
    for m in solo_lectura:
        partes.append(f"### {asset.rel(m)} (solo lectura)\n```python\n{m.read_text(encoding='utf-8')}\n```")
    partes.append("## API de alth disponible\n" + api_alth(asset.modulos_usados()))
    partes.append("Responde con el formato obligatorio (CAMBIOS, ESTADO y bloques ### ARCHIVO).")
    return "\n\n".join(partes)


def imagenes_para(asset: Asset, resultado: dict, sil: dict | None) -> list[tuple[str, Path, tuple | None]]:
    imgs = []
    if resultado.get("reporte") and resultado["reporte"].get("hoja"):
        imgs.append(("Hoja de contacto de la última vuelta (frente, lateral, espalda, 3/4)",
                     Path(resultado["reporte"]["hoja"]), None))
    if asset.ref and (RAIZ / asset.ref).exists():
        imgs.append(("Referencia objetivo", RAIZ / asset.ref, asset.recorte))
    if sil and sil.get("superposicion"):
        imgs.append(("Siluetas encimadas: gris = coinciden, rojo = sobra en el modelo, azul = le falta al modelo",
                     Path(sil["superposicion"]), None))
    return imgs


# ---------------------------------------------------------------- modelo
def config_modelo(args) -> dict:
    nombre = args.proveedor or os.environ.get("ALTH_PROVEEDOR", "ollama")
    if nombre not in PROVEEDORES:
        sys.exit(f"[bucle] proveedor desconocido: {nombre}. Opciones: {', '.join(PROVEEDORES)}")
    p = dict(PROVEEDORES[nombre])
    p["nombre"] = nombre
    p["base"] = os.environ.get("ALTH_API_BASE") or p["base"]
    p["modelo"] = args.modelo or os.environ.get("ALTH_MODELO") or p["modelo"]
    p["clave"] = os.environ.get("ALTH_API_KEY") or (os.environ.get(p["clave_env"]) if p["clave_env"] else None)
    if args.sin_vision or os.environ.get("ALTH_VISION") == "0":
        p["vision"] = False
    if not p["base"] or not p["modelo"]:
        sys.exit(f"[bucle] falta base o modelo para '{nombre}': usa --modelo y/o ALTH_API_BASE.")
    if p["clave_env"] and not p["clave"] and nombre not in ("ollama", "personalizado"):
        sys.exit(f"[bucle] falta la clave: exporta {p['clave_env']} (o ALTH_API_KEY).")
    return p


def llamar_modelo(cfg: dict, sistema: str, texto: str, imagenes, temperatura=0.3, reintentos=3) -> str:
    contenido: list | str
    if cfg["vision"] and imagenes:
        contenido = [{"type": "text", "text": texto}]
        for etiqueta, ruta, recorte in imagenes:
            contenido.append({"type": "text", "text": f"[Imagen] {etiqueta}"})
            contenido.append({"type": "image_url", "image_url": {"url": imagen_dataurl(ruta, recorte)}})
    else:
        contenido = texto
    cuerpo = json.dumps({"model": cfg["modelo"], "temperature": temperatura,
                         "messages": [{"role": "system", "content": sistema},
                                      {"role": "user", "content": contenido}]}).encode()
    cab = {"Content-Type": "application/json"}
    if cfg.get("clave"):
        cab["Authorization"] = f"Bearer {cfg['clave']}"
    url = cfg["base"].rstrip("/") + "/chat/completions"
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(url, data=cuerpo, headers=cab, method="POST")
            with urllib.request.urlopen(req, timeout=900) as r:
                datos = json.loads(r.read())
            return datos["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and intento < reintentos - 1:
                espera = 20 * (intento + 1)
                print(f"[bucle] el proveedor respondió {e.code}; reintento en {espera} s")
                time.sleep(espera)
                continue
            raise SystemExit(f"[bucle] el proveedor respondió {e.code}: {detalle}")
        except urllib.error.URLError as e:
            if intento < reintentos - 1:
                time.sleep(10)
                continue
            raise SystemExit(f"[bucle] no pude conectar con {url}: {e.reason}")
    raise SystemExit("[bucle] sin respuesta del modelo")


# ---------------------------------------------------------------- aplicar respuesta
def aplicar(asset: Asset, respuesta: str) -> tuple[bool, str, dict[str, str]]:
    """Escribe los archivos de la respuesta si pasan la guardia. Devuelve (ok, mensaje, respaldo)."""
    archivos = extraer_archivos(respuesta)
    if not archivos:
        return False, "La respuesta no traía ningún bloque de código.", {}
    destinos = {}
    for ruta, codigo in archivos.items():
        destino = asset.editables[0] if ruta in ("", "build.py") else ruta
        destino = destino.removeprefix("./")
        if destino not in asset.editables:
            coincide = [e for e in asset.editables if e.endswith(destino)]
            if not coincide:
                return False, f"Intentó escribir {ruta}, que no es editable ({', '.join(asset.editables)}).", {}
            destino = coincide[0]
        problemas = revisar_codigo(codigo)
        if destino == asset.editables[0] and "revisar(" not in codigo:
            problemas.append("build.py ya no llama a alth.revisar(...)")
        if problemas:
            return False, f"{destino}: " + "; ".join(problemas), {}
        destinos[destino] = codigo
    respaldo = {d: (RAIZ / d).read_text(encoding="utf-8") for d in destinos}
    for d, codigo in destinos.items():
        (RAIZ / d).write_text(codigo, encoding="utf-8")
    return True, f"Escribí: {', '.join(destinos)}", respaldo


def guardar_vuelta(asset: Asset, n: int, resultado: dict, respuesta: str | None = None) -> Path:
    d = asset.trabajo / f"v{n:02d}"
    d.mkdir(parents=True, exist_ok=True)
    for e in asset.editables:
        shutil.copy(RAIZ / e, d / Path(e).name)
    if resultado.get("carpeta"):
        for f in ("hoja.png", "reporte.json"):
            if (resultado["carpeta"] / f).exists():
                shutil.copy(resultado["carpeta"] / f, d / f)
    (d / "salida.txt").write_text(resultado.get("salida", ""), encoding="utf-8")
    if respuesta:
        (d / "respuesta.md").write_text(respuesta, encoding="utf-8")
    return d


def escribir_resumen(asset: Asset):
    filas = ["| vuelta | build | verificación | IoU silueta | cambios |", "|---|---|---|---|---|"]
    for e in asset.historial:
        filas.append(f"| {e['vuelta']} | {'OK' if e.get('build_ok') else 'falló'} | "
                     f"{'OK' if e.get('verificacion_ok') else '—'} | {e.get('iou')} | {e.get('cambios', '')} |")
    (asset.trabajo / "resumen.md").write_text(f"# Bucle · {asset.nombre}\n\n" + "\n".join(filas) + "\n",
                                              encoding="utf-8")


def registrar(asset: Asset, n: int, resultado: dict, sil, cambios="", modelo=""):
    rep = resultado.get("reporte") or {}
    asset.historial.append({
        "vuelta": n, "build_ok": resultado.get("ok"), "cambios": cambios, "modelo": modelo,
        "verificacion_ok": bool((rep.get("verificacion") or {}).get("ok")),
        "iou": (sil or {}).get("iou"), "fecha": time.strftime("%Y-%m-%d %H:%M"),
    })
    asset.guardar_historial()
    escribir_resumen(asset)


# ---------------------------------------------------------------- comandos
def cmd_correr(args):
    asset = Asset(args.asset, args)
    cfg = config_modelo(args)
    sistema = texto_sistema()
    print(f"[bucle] {asset.nombre} · {cfg['nombre']}/{cfg['modelo']} · visión {'sí' if cfg['vision'] else 'no'}"
          f" · hasta {args.vueltas} vueltas")
    n0 = (asset.historial[-1]["vuelta"] + 1) if asset.historial else 0
    resultado = correr_build(asset, args.timeout)
    sil = medir_silueta(asset, resultado, asset.trabajo / "superposicion.png")
    guardar_vuelta(asset, n0, resultado)
    if not asset.historial or not args.continuar:
        registrar(asset, n0, resultado, sil, "punto de partida", cfg["modelo"])
    ultimo_bueno = {e: (RAIZ / e).read_text(encoding="utf-8") for e in asset.editables} if resultado["ok"] else None
    fallos_seguidos = 0
    for i in range(1, args.vueltas + 1):
        n = n0 + i
        texto = armar_prompt(asset, resultado, sil, i, args.vueltas)
        print(f"[bucle] vuelta {n}: pidiendo corrección al modelo…")
        try:
            respuesta = llamar_modelo(cfg, sistema, texto, imagenes_para(asset, resultado, sil))
        except SystemExit as e:
            # Deja el motivo a la vista (resumen de GitHub Actions, rama de resultado) y termina.
            (asset.trabajo / "error.txt").write_text(f"{cfg['nombre']}/{cfg['modelo']}: {e}\n", encoding="utf-8")
            raise
        cambios, estado = extraer_campo(respuesta, "CAMBIOS"), extraer_campo(respuesta, "ESTADO").upper()
        ok, msg, _ = aplicar(asset, respuesta)
        if not ok:
            print(f"[bucle] respuesta rechazada: {msg}")
            resultado = {"ok": False, "salida": f"Tu respuesta anterior se rechazó sin correr: {msg}",
                         "reporte": resultado.get("reporte"), "carpeta": resultado.get("carpeta")}
            registrar(asset, n, resultado, sil, f"RECHAZADA: {msg}", cfg["modelo"])
            continue
        resultado = correr_build(asset, args.timeout)
        sil = medir_silueta(asset, resultado, asset.trabajo / "superposicion.png")
        guardar_vuelta(asset, n, resultado, respuesta)
        registrar(asset, n, resultado, sil, cambios, cfg["modelo"])
        ver = (resultado.get("reporte") or {}).get("verificacion") or {}
        print(f"[bucle] v{n}: build {'OK' if resultado['ok'] else 'FALLÓ'} · verificación "
              f"{'OK' if ver.get('ok') else '—'} · IoU {(sil or {}).get('iou')} · {cambios}")
        if resultado["ok"]:
            ultimo_bueno = {e: (RAIZ / e).read_text(encoding="utf-8") for e in asset.editables}
            fallos_seguidos = 0
            if estado.startswith("LISTO") and ver.get("ok"):
                print("[bucle] el modelo dice LISTO y la verificación pasó. Revisa la hoja y aprueba tú.")
                break
        else:
            fallos_seguidos += 1
            if fallos_seguidos >= 2 and ultimo_bueno:
                print("[bucle] dos fallos seguidos: vuelvo a la última versión que corrió bien.")
                for e, t in ultimo_bueno.items():
                    (RAIZ / e).write_text(t, encoding="utf-8")
                resultado = correr_build(asset, args.timeout)
                sil = medir_silueta(asset, resultado, asset.trabajo / "superposicion.png")
                fallos_seguidos = 0
    if ultimo_bueno and not resultado.get("ok"):
        for e, t in ultimo_bueno.items():
            (RAIZ / e).write_text(t, encoding="utf-8")
        print("[bucle] la última vuelta falló; dejé los archivos en la última versión buena.")
    print(f"[bucle] listo. Resumen: {asset.rel(asset.trabajo / 'resumen.md')}")


def cmd_paquete(args, asset: Asset | None = None, resultado: dict | None = None):
    asset = asset or Asset(args.asset, args)
    if resultado is None:
        resultado = correr_build(asset, args.timeout) if not args.sin_correr else _ultimo_resultado(asset)
    paq = asset.trabajo / "paquete"
    if paq.exists():
        shutil.rmtree(paq)
    paq.mkdir(parents=True)
    sil = medir_silueta(asset, resultado, paq / "3_siluetas.png")
    n = (asset.historial[-1]["vuelta"] + 1) if asset.historial else 0
    if resultado.get("reporte") and resultado["reporte"].get("hoja"):
        shutil.copy(resultado["reporte"]["hoja"], paq / "1_hoja.png")
    if asset.ref and (RAIZ / asset.ref).exists():
        from PIL import Image
        im = Image.open(RAIZ / asset.ref).convert("RGB")
        if asset.recorte:
            w, h = im.size
            r = asset.recorte
            im = im.crop((int(r[0] * w), int(r[1] * h), int(r[2] * w), int(r[3] * h)))
        im.save(paq / "2_referencia.png")
    prompt = texto_sistema() + "\n\n---\n\n" + armar_prompt(asset, resultado, sil, n)
    (paq / "prompt.md").write_text(prompt, encoding="utf-8")
    guardar_vuelta(asset, n, resultado)
    print(f"[bucle] paquete listo en {asset.rel(paq)}/")
    print("  1. Abre cualquier chat de IA (DeepSeek, Gemini, ChatGPT, Qwen, Le Chat…).")
    print("  2. Pega el contenido de prompt.md y adjunta las imágenes 1_, 2_ y 3_ si el chat acepta imágenes.")
    print("  3. Guarda la respuesta completa en un archivo y corre:")
    print(f"     python3 tools/bucle.py aplicar {asset.rel(asset.dir)} respuesta.md")
    return resultado, sil


def _ultimo_resultado(asset: Asset) -> dict:
    candidatos = sorted((RAIZ / "renders").rglob("reporte.json"), key=lambda p: p.stat().st_mtime)
    for rp in reversed(candidatos):
        rep = json.loads(rp.read_text(encoding="utf-8"))
        if asset.nombre in str(rp):
            return {"ok": True, "reporte": rep, "carpeta": rp.parent, "salida": "(render previo, no se volvió a correr)"}
    return {"ok": False, "reporte": None, "carpeta": None, "salida": "No hay render previo; corre sin --sin-correr."}


def cmd_aplicar(args):
    asset = Asset(args.asset, args)
    respuesta = Path(args.respuesta).read_text(encoding="utf-8")
    ok, msg, respaldo = aplicar(asset, respuesta)
    print(f"[bucle] {msg}")
    if not ok:
        sys.exit(1)
    resultado = correr_build(asset, args.timeout)
    cambios = extraer_campo(respuesta, "CAMBIOS")
    if not resultado["ok"]:
        print("[bucle] el script falló; el siguiente paquete incluye el error para que el modelo lo corrija.")
    res, sil = cmd_paquete(args, asset, resultado)
    registrar(asset, (asset.historial[-1]["vuelta"] + 1) if asset.historial else 1, resultado, sil, cambios, "manual")


def cmd_medir(args):
    asset = Asset(args.asset, args)
    res = _ultimo_resultado(asset)
    sil = medir_silueta(asset, res, asset.trabajo / "superposicion.png")
    print(resumen_verificacion(res.get("reporte")))
    print(silueta.texto(sil) if sil else "Sin silueta: falta render o referencia.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Bucle de modelado ALTH-META con cualquier modelo de IA.",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for nombre in ("correr", "paquete", "aplicar", "medir"):
        s = sub.add_parser(nombre)
        s.add_argument("asset", help="carpeta del asset (assets/lata o solo 'lata')")
        if nombre == "aplicar":
            s.add_argument("respuesta", help="archivo con la respuesta completa del modelo")
        s.add_argument("--ref")
        s.add_argument("--recorte")
        s.add_argument("--vista")
        s.add_argument("--editable", action="append")
        s.add_argument("--nota")
        s.add_argument("--timeout", type=int, default=900)
        s.add_argument("--sin-correr", action="store_true", help="paquete: usa el último render sin volver a correr")
        if nombre == "correr":
            s.add_argument("--vueltas", type=int, default=4)
            s.add_argument("--proveedor")
            s.add_argument("--modelo")
            s.add_argument("--sin-vision", action="store_true")
            s.add_argument("--continuar", action="store_true", help="sigue el historial previo")
    a = p.parse_args(argv)
    {"correr": cmd_correr, "paquete": cmd_paquete, "aplicar": cmd_aplicar, "medir": cmd_medir}[a.cmd](a)


if __name__ == "__main__":
    main()
