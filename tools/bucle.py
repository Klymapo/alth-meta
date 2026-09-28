"""ALTH-META · bucle de modelado con CUALQUIER modelo de IA (no depende de Claude).

El ciclo es: correr build.py en Blender → leer hoja, verificación y silueta → pedirle al modelo el
build.py corregido → repetir. Tres formas de usarlo:

  # 1) Automático. Por defecto usa --proveedor auto: prueba Gemini y, si se quedó sin cuota o falla,
  #    brinca solo a Groq (ambos gratis). Cualquier otra API compatible con OpenAI también sirve:
  python3 tools/bucle.py correr assets/pruebas/joven_rubio_v1 --vueltas 4
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
  --proveedor / ALTH_PROVEEDOR   auto (por defecto, cadena Gemini→Groq) | ollama | deepseek | gemini |
                                 openrouter | groq | personalizado
  --modelo    / ALTH_MODELO      nombre del modelo (solo aplica si NO usas "auto"; cada proveedor
                                 trae uno por defecto, revisa el vigente)
  ALTH_API_BASE, ALTH_API_KEY    para "personalizado" o para sobrescribir
  --sin-vision / ALTH_VISION=0   para modelos que no aceptan imágenes (reciben solo números y texto)

El bucle NUNCA corre el modo final ni exporta: al terminar deja build.py con la última versión que
corrió bien y un resumen en renders/<asset>/bucle/. La aprobación sigue siendo tuya.
"""
from __future__ import annotations

import argparse
import ast
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
    "groq": {"base": "https://api.groq.com/openai/v1", "clave_env": "GROQ_API_KEY",
             "modelo": "llama-3.3-70b-versatile", "vision": False},
    "personalizado": {"base": None, "clave_env": "ALTH_API_KEY", "modelo": None, "vision": True},
}

# "auto" (el modo por defecto de `correr`) intenta estos en orden y brinca al siguiente si el que
# está probando se queda sin cuota, falla o no tiene clave configurada. Solo entran proveedores
# gratis y con un modelo de fábrica confiable; deja fuera a OpenRouter porque sus modelos gratis
# cambian de nombre muy seguido (agrégalo a mano con --proveedor openrouter --modelo … si quieres).
CADENA_AUTO = ["gemini", "groq"]

# Reintentos. Un 503 "high demand" de Gemini suele durar minutos, no segundos: con estas esperas
# el bucle aguanta ~7 min por modelo antes de rendirse (antes solo ~1 min y tumbaba la corrida).
SATURADO = (500, 502, 503, 504)
ESPERAS_SATURADO = (30, 60, 120, 180)
ESPERAS_CUOTA = (20, 40)
# Si el modelo de fábrica de Gemini sigue saturado, prueba hasta este número de modelos
# "flash" hermanos que la propia API anuncie en /models (otros servidores, otra saturación).
ALTERNOS_MAX = 2
PRESUPUESTO_MAX = {"objeto_simple": 3, "objeto": 4, "mueble_vehiculo": 5, "personaje": 8}


def _dormir(segundos: float) -> None:
    time.sleep(segundos)  # separado para que las pruebas no esperen de verdad


# Para avisar CUÁNDO reintentar cuando un proveedor se quedó sin cuota del día (no es exacto,
# es la referencia pública de cada uno).
CUANDO_SE_REINICIA = {
    "gemini": "a medianoche hora del Pacífico (~2–3 am en CDMX)",
    "groq": "a medianoche UTC (~6 pm en CDMX)",
    "openrouter": "unas 24 h después de tu primer uso del día",
}

# Guardia, NO un sandbox: frena lo obvio. El aislamiento real es correr el bucle en GitHub Actions.
PROHIBIDO = ["subprocess", "os.system", "os.popen", "os.remove", "os.unlink", "rmtree", "socket",
             "urllib", "requests", "http.client", "eval(", "exec(", "__import__", "shutil.move"]

LADO_MAX_IMG = 1024
COLA_SALIDA = 60


# ---------------------------------------------------------------- utilidades puras (probadas en tests/)
def extraer_archivos(respuesta: str) -> dict[str, str]:
    """Bloques `### ARCHIVO: ruta` + ``` … ``` (cualquier lenguaje de cerca, incluido json para
    spec.json). Si no hay encabezados y hay un solo bloque de código, se toma como build.py (clave "")."""
    archivos = {}
    patron = re.compile(r"###\s*ARCHIVO:\s*`?([^\n`]+?)`?\s*\n+```(?:\w+)?\s*\n(.*?)\n```", re.S)
    for ruta, codigo in patron.findall(respuesta):
        archivos[ruta.strip()] = codigo.rstrip() + "\n"
    if not archivos:
        bloques = re.findall(r"```(?:\w+)?\s*\n(.*?)\n```", respuesta, re.S)
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
        brief_config = conf.get("brief")
        if brief_config:
            brief_path = Path(brief_config)
            self.brief_path = brief_path if brief_path.is_absolute() else RAIZ / brief_path
        else:
            self.brief_path = self.dir / "brief_final.md"
        self.brief = (self.brief_path.read_text(encoding="utf-8").strip()
                      if self.brief_path.exists() else "")
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
        # El código propuesto por la IA no debe heredar las claves usadas para llamarla.
        entorno = {k: v for k, v in os.environ.items()
                   if not (k.endswith("_API_KEY") or k in {"GH_TOKEN", "GITHUB_TOKEN", "ALTH_API_KEY"})}
        r = subprocess.run([exe, str(asset.build)], cwd=RAIZ, env=entorno,
                           capture_output=True, text=True, timeout=timeout)
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
    if asset.brief:
        partes.append(f"## Brief final versionado · `{asset.rel(asset.brief_path)}`\n{asset.brief}")
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


def _cfg_de_cadena(nombre: str) -> dict | None:
    """Como config_modelo, pero para 'auto': si le falta la clave o el modelo, regresa None
    en vez de terminar el programa (ese proveedor simplemente no entra a la cadena)."""
    p = dict(PROVEEDORES[nombre])
    p["nombre"] = nombre
    p["base"] = os.environ.get("ALTH_API_BASE") or p["base"]
    p["clave"] = os.environ.get(p["clave_env"]) if p["clave_env"] else None
    if not p["base"] or not p["modelo"] or (p["clave_env"] and not p["clave"]):
        return None
    return p


def config_cadena(args) -> list[dict]:
    """La cadena de proveedores para 'correr'. 'auto' (por defecto) prueba, en orden, los de
    CADENA_AUTO que sí tengan clave configurada. Cualquier otro nombre usa ese único proveedor,
    igual que antes (falla de una vez si le falta la clave)."""
    nombre = args.proveedor or os.environ.get("ALTH_PROVEEDOR", "auto")
    if nombre != "auto":
        return [config_modelo(args)]
    cadena = [c for c in (_cfg_de_cadena(n) for n in CADENA_AUTO) if c]
    if not cadena:
        sys.exit("[bucle] proveedor 'auto': no encontré ninguna clave configurada de "
                 f"{', '.join(CADENA_AUTO)}. Define al menos una (p. ej. GEMINI_API_KEY) "
                 "o usa --proveedor para elegir uno directo.")
    return cadena


class _FalloProveedor(Exception):
    """Un proveedor de la cadena no respondió tras sus reintentos. Uso interno de llamar_con_respaldo."""
    def __init__(self, codigo, detalle):
        self.codigo, self.detalle = codigo, detalle
        super().__init__(f"{codigo}: {detalle}")


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
    intento = 0
    while True:
        try:
            req = urllib.request.Request(url, data=cuerpo, headers=cab, method="POST")
            with urllib.request.urlopen(req, timeout=900) as r:
                datos = json.loads(r.read())
            return datos["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:500]
            # 5xx = servidor saturado (temporal): vale la pena esperar varios minutos.
            # 429 = cuota: reintentar poco, casi nunca se libera en segundos.
            esperas = ESPERAS_SATURADO if e.code in SATURADO else ESPERAS_CUOTA if e.code == 429 else ()
            if intento < len(esperas):
                espera = esperas[intento]
                intento += 1
                print(f"[bucle] {cfg['nombre']}/{cfg['modelo']} respondió {e.code}; "
                      f"reintento {intento}/{len(esperas)} en {espera} s")
                _dormir(espera)
                continue
            raise _FalloProveedor(e.code, detalle)
        except urllib.error.URLError as e:
            if intento < reintentos - 1:
                intento += 1
                _dormir(10)
                continue
            raise _FalloProveedor("conexión", str(e.reason))


def llamar_con_respaldo(cadena: list[dict], sistema: str, texto: str, imagenes,
                        temperatura=0.3) -> tuple[str, dict]:
    """Prueba cada proveedor de la cadena en orden; usa el primero que responda.
    Si TODOS fallan, revienta con un SystemExit que junta el motivo de cada uno
    (y cuándo se espera que se reinicie su cuota, si aplica)."""
    errores = []
    saturados = False
    for i, cfg in enumerate(cadena):
        imgs = imagenes if cfg["vision"] else []
        candidatos = [cfg]
        while candidatos:
            actual = candidatos.pop(0)
            try:
                return llamar_modelo(actual, sistema, texto, imgs, temperatura), actual
            except _FalloProveedor as e:
                cuando = CUANDO_SE_REINICIA.get(actual["nombre"])
                if str(e.codigo) in ("429", "402", "403"):
                    pista = f" — cuota agotada, se reinicia {cuando}" if cuando else " — cuota agotada"
                elif e.codigo in SATURADO:
                    pista, saturados = " — servidor saturado (temporal)", True
                else:
                    pista = ""
                linea = f"{actual['nombre']}/{actual['modelo']}: {e.codigo}{pista} ({e.detalle[:200]})"
                print(f"[bucle] {linea}")
                errores.append(linea)
                # Solo al primer fallo por saturación del modelo de fábrica: busca hermanos.
                if actual is cfg and e.codigo in SATURADO and cfg["nombre"] == "gemini":
                    for m in modelos_alternos(cfg):
                        candidatos.append({**cfg, "modelo": m})
                    if candidatos:
                        print(f"[bucle] pruebo otros modelos de {cfg['nombre']}: "
                              f"{', '.join(c['modelo'] for c in candidatos)}")
        if i < len(cadena) - 1:
            print(f"[bucle] sigo con el siguiente proveedor de la cadena: {cadena[i + 1]['nombre']}…")
    if not errores:
        mensaje = "La cadena de proveedores está vacía (¿faltan claves de API?)."
    else:
        mensaje = "Ningún proveedor de la cadena respondió:\n" + "\n".join(errores)
        if saturados:
            mensaje += ("\n\nQué hacer: la saturación es temporal y NO gasta tu cuota. Vuelve a lanzar la "
                        "corrida en 15–30 min (encadena sola desde esta rama).")
        if len(cadena) == 1:
            faltan = [n for n in CADENA_AUTO if n != cadena[0]["nombre"]]
            if faltan:
                mensaje += ("\nTip: la cadena solo tenía a " + cadena[0]["nombre"] + ". Agrega también "
                            + " / ".join(PROVEEDORES[n]["clave_env"] for n in faltan)
                            + " en Settings → Secrets → Actions para que brinque sola cuando uno falle.")
    raise SystemExit("[bucle] " + mensaje)


def modelos_alternos(cfg: dict) -> list[str]:
    """Pregunta a la API qué modelos tiene y regresa hasta ALTERNOS_MAX de la misma familia
    ("flash"), primero los estables y al final los 'lite'. Si algo falla, lista vacía."""
    try:
        cab = {"Authorization": f"Bearer {cfg['clave']}"} if cfg.get("clave") else {}
        req = urllib.request.Request(cfg["base"].rstrip("/") + "/models", headers=cab)
        with urllib.request.urlopen(req, timeout=30) as r:
            datos = json.loads(r.read())
    except Exception as e:  # noqa: BLE001  (es un extra: si no se puede, no pasa nada)
        print(f"[bucle] no pude listar modelos de {cfg['nombre']}: {e}")
        return []
    return elegir_alternos([m.get("id", "") for m in datos.get("data", [])], cfg["modelo"])


def elegir_alternos(ids: list[str], actual: str, maximo: int = ALTERNOS_MAX) -> list[str]:
    """Parte pura de modelos_alternos (probada en tests/): filtra y ordena los nombres."""
    evitar = ("image", "tts", "audio", "live", "embed", "vision", "thinking", "exp")
    vistos, buenos = set(), []
    for i in ids:
        nombre = i.split("/", 1)[1] if i.startswith("models/") else i
        bajo = nombre.lower()
        if nombre == actual or nombre in vistos or "flash" not in bajo or any(t in bajo for t in evitar):
            continue
        vistos.add(nombre)
        buenos.append(nombre)
    # estables antes que preview, y 'lite' al final; dentro de cada grupo, el número más alto primero
    def clave(n):
        num = re.findall(r"\d+(?:\.\d+)?", n)
        return ("lite" in n, "preview" in n, -float(num[0]) if num else 0.0, n)
    return sorted(buenos, key=clave)[:maximo]


# ---------------------------------------------------------------- progreso en vivo (CHSP-X)
class Progreso:
    """Publica el avance de la corrida para que CHSP-X muestre la barra de %.

    Solo actúa dentro de GitHub Actions (necesita ALTH_PROGRESO_TOKEN, GITHUB_REPOSITORY y
    GITHUB_RUN_ID): escribe `bucle-<run_id>.json` en la rama `progreso` con la API de Contents,
    que CHSP-X ya puede leer con su token. Si algo falla, avisa una vez y sigue: el progreso
    nunca debe tumbar una corrida."""
    RAMA = "progreso"

    def __init__(self, asset_nombre: str, vueltas: int):
        self.repo = os.environ.get("GITHUB_REPOSITORY")
        self.run = os.environ.get("GITHUB_RUN_ID")
        self.token = os.environ.get("ALTH_PROGRESO_TOKEN")
        self.activo = bool(self.repo and self.run and self.token)
        self.asset, self.vueltas = asset_nombre, max(1, vueltas)
        self.ruta = f"bucle-{self.run}.json"
        self.sha = None
        self._avisado = False

    def _api(self, metodo, ruta, cuerpo=None):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}{ruta}", method=metodo,
            data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}")

    def _asegurar_rama(self):
        try:
            self._api("GET", f"/git/ref/heads/{self.RAMA}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            base = self._api("GET", "/git/ref/heads/main")["object"]["sha"]
            self._api("POST", "/git/refs", {"ref": f"refs/heads/{self.RAMA}", "sha": base})

    def unidades(self, hechas: float, etapa: str, vuelta: int | None = None):
        """hechas: cuántas 'unidades' van (vuelta 0 = 1 unidad; cada vuelta con la IA = 1)."""
        self.publicar(round(100 * hechas / (self.vueltas + 1)), etapa, vuelta)

    def publicar(self, pct: int, etapa: str, vuelta: int | None = None):
        if not self.activo:
            return
        datos = {"pct": max(0, min(100, int(pct))), "etapa": etapa, "vuelta": vuelta,
                 "vueltas": self.vueltas, "asset": self.asset, "actualizado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        cuerpo = {"message": f"progreso {self.asset}: {datos['pct']} %", "branch": self.RAMA,
                  "content": base64.b64encode(json.dumps(datos, ensure_ascii=False).encode()).decode()}
        for intento in range(2):
            try:
                if self.sha:
                    cuerpo["sha"] = self.sha
                r = self._api("PUT", f"/contents/{self.ruta}", cuerpo)
                self.sha = r["content"]["sha"]
                return
            except urllib.error.HTTPError as e:
                if intento == 0 and e.code in (404, 422):   # la rama aún no existe
                    try:
                        self._asegurar_rama()
                        continue
                    except Exception:  # noqa: BLE001
                        pass
                self._fallo(f"HTTP {e.code}")
                return
            except Exception as e:  # noqa: BLE001
                self._fallo(str(e))
                return

    def _fallo(self, motivo):
        if not self._avisado:
            print(f"[bucle] (aviso) no pude publicar el progreso para CHSP-X: {motivo}. Sigo igual.")
            self._avisado = True


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
        if destino.endswith(".json"):
            try:
                json.loads(codigo)
            except json.JSONDecodeError as e:
                return False, f"{destino}: JSON inválido ({e}).", {}
        else:
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


def guardar_revision(asset: Asset, resultado: dict, vuelta: int, motivo: str) -> dict:
    """Congela la evidencia del código que queda en la rama, nunca la de otra vuelta."""
    if not resultado.get("ok") or not resultado.get("carpeta"):
        raise ValueError("No hay render válido del código seleccionado")
    carpeta = Path(resultado["carpeta"])
    hoja, reporte = carpeta / "hoja.png", carpeta / "reporte.json"
    if not hoja.is_file() or not reporte.is_file():
        raise ValueError("Falta la hoja o el reporte del código seleccionado")
    destino = asset.trabajo / "revision"
    destino.mkdir(exist_ok=True)
    shutil.copy2(hoja, destino / "hoja.png")
    shutil.copy2(reporte, destino / "reporte.json")
    huella = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    archivos = {ruta: huella(RAIZ / ruta) for ruta in asset.editables}
    if asset.spec_path.is_file():
        archivos[asset.rel(asset.spec_path)] = huella(asset.spec_path)
    datos = {
        "asset": asset.rel(asset.dir), "vuelta_origen": vuelta, "motivo": motivo,
        "archivos_sha256": archivos, "hoja_sha256": huella(destino / "hoja.png"),
        "reporte_sha256": huella(destino / "reporte.json"),
        "verificacion_ok": bool((resultado.get("reporte") or {}).get("verificacion", {}).get("ok")),
    }
    (destino / "revision.json").write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return datos


# ---------------------------------------------------------------- comandos
_BUILD_ARRANQUE = '''"""{nombre} ALTH · arranque (todavía sin diseño real: solo una caja de relleno).

    alth-python assets/{nombre}/build.py            # iteración
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"

alth.nueva_escena()
relleno = alth.caja("Relleno", (10, 10, 10), color="#B7BABE")

objs = [relleno]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "{nombre}" / MODO, modo=MODO, titulo="{nombre} · arranque",
                   asset=alth.RAIZ / "assets" / "{nombre}" / "spec.json")
print(rep["medidas_mm"], rep["segundos_total"])
'''


def cmd_arrancar(args):
    """Crea el primer boceto de un asset nuevo (spec.json + build.py de relleno) y de una vez
    sigue con el bucle normal: la IA de la cadena escribe la primera versión real, tú no tienes
    que escribir ni una línea de Python para empezar."""
    nombre = Path(args.asset).name
    carpeta = RAIZ / "assets" / nombre
    if (carpeta / "build.py").exists():
        sys.exit(f"[bucle] assets/{nombre}/build.py ya existe; usa 'correr', no 'arrancar'.")
    if not args.ref:
        sys.exit("[bucle] arrancar necesita --ref refs/….png (la foto o imagen de referencia).")
    if not args.descripcion:
        sys.exit('[bucle] arrancar necesita --descripcion "qué es y su tamaño real".')
    carpeta.mkdir(parents=True, exist_ok=True)
    spec_seed = {
        "nombre": nombre, "categoria": "", "tipo_presupuesto": args.tipo or "objeto",
        "descripcion_humana": args.descripcion,
        "medidas_reales_mm": {}, "medidas_alth_mm": {}, "colores": {}, "modulos": [], "cotas": [],
        "historial": [], "referencia": args.ref,
        "bucle": {
            "ref": args.ref,
            "editables": [f"assets/{nombre}/spec.json"],
            "nota": (
                f"ARRANQUE de un asset nuevo. Qué es y su tamaño real: {args.descripcion}\n"
                "Todavía no hay diseño: build.py de momento solo trae una caja de relleno gris. "
                "En esta vuelta propón la PRIMERA versión completa de la geometría (con "
                "alth.torno/prisma/hoja/caja/anillo, lo que corresponda) Y llena este mismo "
                "spec.json: categoria, medidas_reales_mm, medidas_alth_mm (fórmula "
                "mm_real * 0.0559 * k, con el k de spec/alth_spec.json -> conversion_k), colores "
                "SOLO de la paleta, modulos, y una primera entrada en cotas para las piezas "
                "principales. No te preocupes por perfeccionar detalles todavía: cuerpo y "
                "proporciones primero. Sigue el 'Ciclo por asset' de CLAUDE.md."
            ),
        },
    }
    (carpeta / "spec.json").write_text(json.dumps(spec_seed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (carpeta / "build.py").write_text(_BUILD_ARRANQUE.format(nombre=nombre), encoding="utf-8")
    print(f"[bucle] arranque listo en assets/{nombre}/ (spec.json + build.py de relleno). Sigo con el bucle…")
    args.asset = f"assets/{nombre}"
    cmd_correr(args)


def cmd_correr(args):
    asset = Asset(args.asset, args)
    maximo = PRESUPUESTO_MAX.get(asset.spec.get("tipo_presupuesto", "objeto"), 4)
    if args.vueltas > maximo:
        print(f"[bucle] reduzco el máximo de {args.vueltas} a {maximo} intentos para este tipo de asset.")
        args.vueltas = maximo
    cadena = config_cadena(args)
    sistema = texto_sistema()
    nombres = " → ".join(f"{c['nombre']}/{c['modelo']}" for c in cadena)
    print(f"[bucle] {asset.nombre} · cadena: {nombres} · hasta {args.vueltas} vueltas")
    n0 = (asset.historial[-1]["vuelta"] + 1) if asset.historial else 0
    prog = Progreso(asset.nombre, args.vueltas)
    prog.unidades(0, "Renderizando el punto de partida", 0)
    resultado = correr_build(asset, args.timeout)
    sil = medir_silueta(asset, resultado, asset.trabajo / "superposicion.png")
    guardar_vuelta(asset, n0, resultado)
    if not asset.historial or not args.continuar:
        registrar(asset, n0, resultado, sil, "punto de partida", "-")
    def _snapshot():
        return {e: (RAIZ / e).read_text(encoding="utf-8") for e in asset.editables}

    def _iou(s):
        return (s or {}).get("iou") if (s or {}).get("iou") is not None else -1

    def _rango(res, s):
        """Qué versión es 'mejor': primero la que PASA la verificación (medidas, triángulos,
        paleta, piezas flotantes, apoyo en Z=0); entre iguales, la de mejor silueta (IoU)."""
        ver_ok = bool(((res.get("reporte") or {}).get("verificacion") or {}).get("ok"))
        return (ver_ok, _iou(s))

    ultimo_bueno = _snapshot() if resultado["ok"] else None
    mejor_bueno, mejor_rango, mejor_n = ((ultimo_bueno, _rango(resultado, sil), n0) if resultado["ok"]
                                         else (None, (False, -1), None))
    fallos_seguidos = 0
    for i in range(1, args.vueltas + 1):
        n = n0 + i
        texto = armar_prompt(asset, resultado, sil, i, args.vueltas)
        print(f"[bucle] vuelta {n}: pidiendo corrección al modelo…")
        prog.unidades(i, f"Vuelta {i}/{args.vueltas}: la IA propone cambios", i)
        try:
            respuesta, cfg = llamar_con_respaldo(cadena, sistema, texto, imagenes_para(asset, resultado, sil))
        except SystemExit as e:
            # Deja el motivo a la vista (resumen de GitHub Actions, rama de resultado) y termina.
            (asset.trabajo / "error.txt").write_text(f"{e}\n", encoding="utf-8")
            raise
        cambios, estado = extraer_campo(respuesta, "CAMBIOS"), extraer_campo(respuesta, "ESTADO").upper()
        ok, msg, _ = aplicar(asset, respuesta)
        if not ok:
            print(f"[bucle] respuesta rechazada: {msg}")
            resultado = {"ok": False, "salida": f"Tu respuesta anterior se rechazó sin correr: {msg}",
                         "reporte": resultado.get("reporte"), "carpeta": resultado.get("carpeta")}
            registrar(asset, n, resultado, sil, f"RECHAZADA: {msg}", cfg["modelo"])
            continue
        if asset.spec_path.exists():
            try:  # si el modelo también reescribió spec.json (modo 'arrancar'), toma lo nuevo
                asset.spec = json.loads(asset.spec_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        prog.unidades(i + 0.5, f"Vuelta {i}/{args.vueltas}: renderizando en Blender", i)
        resultado = correr_build(asset, args.timeout)
        sil = medir_silueta(asset, resultado, asset.trabajo / "superposicion.png")
        guardar_vuelta(asset, n, resultado, respuesta)
        registrar(asset, n, resultado, sil, cambios, f"{cfg['nombre']}/{cfg['modelo']}")
        ver = (resultado.get("reporte") or {}).get("verificacion") or {}
        print(f"[bucle] v{n} ({cfg['nombre']}/{cfg['modelo']}): build {'OK' if resultado['ok'] else 'FALLÓ'} · "
              f"verificación {'OK' if ver.get('ok') else '—'} · IoU {(sil or {}).get('iou')} · {cambios}")
        if resultado["ok"]:
            ultimo_bueno = _snapshot()
            fallos_seguidos = 0
            if _rango(resultado, sil) > mejor_rango:
                mejor_bueno, mejor_rango, mejor_n = ultimo_bueno, _rango(resultado, sil), n
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
    if mejor_bueno is not None:
        actual = _snapshot() if resultado.get("ok") else None
        if actual != mejor_bueno:
            for e, t in mejor_bueno.items():
                (RAIZ / e).write_text(t, encoding="utf-8")
            print(f"[bucle] restauré la mejor vuelta (v{mejor_n}) antes de generar la evidencia.")
            resultado = correr_build(asset, args.timeout)
            if not resultado["ok"]:
                raise SystemExit("[bucle] falló el render de la vuelta restaurada; no hay evidencia aprobable.")
        ver_ok, iou = mejor_rango
        estado_ver = "verificación OK" if ver_ok else "ninguna vuelta pasó la verificación"
        motivo = "mejor versión verificada" if ver_ok else "mejor silueta sin verificación completa"
        guardar_revision(asset, resultado, mejor_n, motivo)
        print(f"[bucle] hoja de revisión corresponde al código seleccionado (v{mejor_n}).")
        print(f"[bucle] me quedo con la vuelta {mejor_n} ({estado_ver}, IoU {iou}).")
        # El workflow usa esto para publicar la hoja de ESTA vuelta, no la de la última.
        (asset.trabajo / "elegida.txt").write_text(f"v{mejor_n:02d}\n", encoding="utf-8")
        with open(asset.trabajo / "resumen.md", "a", encoding="utf-8") as f:
            f.write(f"\n**Versión que queda en la rama:** vuelta {mejor_n} · {estado_ver} · IoU {iou}\n"
                    "_Regla: primero las que pasan la verificación; entre ellas, la de mejor silueta._\n")
    prog.publicar(100, f"Terminado · queda la vuelta {mejor_n}" if mejor_n is not None else "Terminado")
    print(f"[bucle] listo. Resumen: {asset.rel(asset.trabajo / 'resumen.md')}")


def cmd_paquete(args, asset: Asset | None = None, resultado: dict | None = None):
    asset = asset or Asset(args.asset, args)
    if getattr(args, "unico", False):
        asset.nota = ("RONDA ÚNICA: aplica todas las correcciones en esta respuesta "
                      "(ver la sección RONDA ÚNICA de las reglas).\n" + (asset.nota or "")).strip()
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
    for nombre in ("correr", "arrancar", "paquete", "aplicar", "medir"):
        s = sub.add_parser(nombre)
        s.add_argument("asset", help="carpeta del asset (assets/lata o solo 'lata'; en 'arrancar' "
                                     "es el nombre nuevo que se va a crear)")
        if nombre == "aplicar":
            s.add_argument("respuesta", help="archivo con la respuesta completa del modelo")
        s.add_argument("--ref", help="arrancar: la imagen de referencia es obligatoria aquí")
        s.add_argument("--recorte")
        s.add_argument("--vista")
        s.add_argument("--editable", action="append")
        s.add_argument("--nota")
        s.add_argument("--timeout", type=int, default=900)
        s.add_argument("--sin-correr", action="store_true", help="paquete: usa el último render sin volver a correr")
        if nombre == "paquete":
            s.add_argument("--unico", action="store_true",
                           help="ronda única: pide TODAS las correcciones en una sola respuesta (para copiar y pegar)")
        if nombre == "arrancar":
            s.add_argument("--descripcion", required=True, help='qué es y su tamaño real, p. ej. "espada larga medieval, 90 cm"')
            s.add_argument("--tipo", choices=tuple(PRESUPUESTO_MAX),
                           help="Tipo de asset para el presupuesto de intentos")
        if nombre in ("correr", "arrancar"):
            s.add_argument("--vueltas", type=int, default=4)
            s.add_argument("--proveedor", help="auto (por defecto) | ollama | deepseek | gemini | "
                                               "openrouter | groq | personalizado")
            s.add_argument("--modelo")
            s.add_argument("--sin-vision", action="store_true")
            s.add_argument("--continuar", action="store_true", help="sigue el historial previo")
    a = p.parse_args(argv)
    {"correr": cmd_correr, "arrancar": cmd_arrancar, "paquete": cmd_paquete,
     "aplicar": cmd_aplicar, "medir": cmd_medir}[a.cmd](a)


if __name__ == "__main__":
    main()
