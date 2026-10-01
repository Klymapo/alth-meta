"""Investigación SIN IA (bloque T1 de docs/BRIEF_LINEA_UNICA.md): encontrar candidatos y probarlos.

    python3 tools/investigar.py buscar dedos "separar dedos de una mano tipo mitón"
    alth-python tools/investigar.py probar kb/investigacion/<id>.json
    python3 tools/investigar.py estado dedos

Sin modelo de lenguaje, investigar no es "entender" textos; es:
  1. Mirar la memoria (kb/). Una técnica `verified` para la capacidad con la MISMA versión de Blender
     → se usa y termina. Las `failed` y los `intentos_fallidos` de kb/capacidades.json se reportan y
     esas técnicas NO se repiten.
  2. Descargar páginas públicas (API y manual de Blender) y buscar código publicado con la API de
     GitHub (token de Actions en GITHUB_TOKEN). Cada operador documentado es un "documento"; se
     puntúa con BM25 contra las palabras de la capacidad y del problema (traducidas con un glosario
     fijo, sin respuestas dentro). De los ejemplos de código se extraen llamadas concretas
     (`bmesh.ops.*`, `bpy.ops.mesh.*`, `modifiers.new(type=…)`) con sus parámetros y la URL.
  3. Escribir el brief en el formato de copox/research/*.json, pasarlo por
     copox.production.research_gate.validate_research y guardarlo como `unverified`.
  4. `probar` (en Blender): cada candidato se aplica a un banco de prueba y pasa por los auditores.
     Solo un banco propio de la capacidad (tools/bancos/<capacidad>.py) puede subirlo a `verified`;
     el banco genérico de integridad solo puede tumbarlo a `failed`.
  5. Sin red, sin hallazgos o sin brief válido: RESEARCH_REQUIRED (código de salida 9). Nunca finge.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from copox.production.research_gate import validate_research  # noqa: E402

KB_CAPACIDADES = RAIZ / "kb" / "capacidades.json"
KB_INDICE = RAIZ / "kb" / "investigacion.json"
KB_BRIEFS = RAIZ / "kb" / "investigacion"
VOCAB = RAIZ / "spec" / "capacidades_vocab.json"
BANCOS = RAIZ / "tools" / "bancos"
VERSION_BLENDER_DEFECTO = "5.2.2"
USER_AGENT = "alth-meta-investigar/1.0 (+https://github.com/Klymapo/alth-meta; sin IA)"
SALIDA_RESEARCH_REQUIRED = 9

# Glosario fijo español → inglés. Son PALABRAS, no respuestas: no dice qué operador usar.
GLOSARIO = {
    "dedo": ["finger"], "dedos": ["finger"], "mano": ["hand"], "manos": ["hand"], "pulgar": ["thumb"],
    "palma": ["palm"], "muneca": ["wrist"], "brazo": ["arm"], "cabeza": ["head"], "cara": ["face"],
    "malla": ["mesh"], "vertice": ["vertex", "vert"], "vertices": ["vertex", "vert"], "arista": ["edge"],
    "aristas": ["edge"], "caras": ["face"], "poligono": ["polygon"], "triangulo": ["triangle"],
    "triangulos": ["triangle"], "separar": ["separate", "split"], "separados": ["separate", "split"],
    "separado": ["separate", "split"], "dividir": ["split", "divide"], "cortar": ["cut"], "corte": ["cut"],
    "hueco": ["gap"], "huecos": ["gap"], "ranura": ["slot", "groove"], "unir": ["join", "merge"],
    "soldar": ["weld", "merge"], "fusionar": ["merge"], "duplicados": ["duplicate", "double"],
    "reducir": ["reduce", "decimate"], "decimar": ["decimate"], "simplificar": ["simplify"],
    "retopologia": ["retopology", "remesh"], "retopologizar": ["retopology", "remesh"],
    "suavizar": ["smooth"], "subdividir": ["subdivide"], "extruir": ["extrude"], "extrusion": ["extrude"],
    "biselar": ["bevel"], "bisel": ["bevel"], "chaflan": ["bevel", "chamfer"], "rellenar": ["fill"],
    "agujero": ["hole"], "agujeros": ["hole"], "puente": ["bridge"], "espejo": ["mirror"],
    "simetria": ["symmetry", "mirror"], "simetrico": ["symmetric", "mirror"], "girar": ["rotate"],
    "escalar": ["scale"], "mover": ["translate"], "plano": ["plane"], "borde": ["boundary", "border"],
    "contorno": ["contour", "outline"], "silueta": ["silhouette"], "proteger": ["protect", "preserve"],
    "conservar": ["preserve", "keep"], "region": ["region"], "regiones": ["region"], "volumen": ["volume"],
    "grosor": ["thickness"], "booleano": ["boolean"], "booleana": ["boolean"], "esculpir": ["sculpt"],
    "pelo": ["hair"], "cabello": ["hair"], "ropa": ["cloth", "clothing"], "tela": ["cloth"],
    "torno": ["lathe", "spin", "revolve"], "revolucion": ["revolve", "spin"], "anillo": ["ring", "torus"],
    "aro": ["ring"], "caja": ["box", "cube"], "cubo": ["cube"], "esfera": ["sphere"], "cilindro": ["cylinder"],
    "hoja": ["leaf", "sheet"], "lamina": ["sheet"], "texto": ["text"], "vidrio": ["glass"], "metal": ["metal"],
    "liquido": ["liquid"], "esqueleto": ["armature", "skeleton"], "huesos": ["bone"], "pesos": ["weight"],
    "individuales": ["individual"], "visibles": ["visible"], "modelables": ["model"], "mitón": ["mitten"],
    "miton": ["mitten"], "guante": ["glove"], "topologia": ["topology"], "integridad": ["integrity"],
    "flotante": ["loose"], "flotantes": ["loose"], "sueltas": ["loose"], "piezas": ["part"],
}
VACIAS = set("""de la el los las un una unos unas y o a en con sin por para que del al se su sus es son
como mas muy ya no si lo le les entre sobre tipo cada todo toda todos todas este esta estos estas ese esa
the a an of and or to in on for with by from is are be as at it its this that""".split())
# Palabras que nombran una TÉCNICA (para reconocer un intento fallido en un candidato).
TECNICAS = {"boolean", "bisect", "decimate", "remesh", "extrude", "inset", "bridge", "sculpt", "subdivide",
            "weld", "solidify", "bevel", "shrinkwrap", "smooth", "knife", "triangulate", "dissolve", "spin",
            "mirror", "split", "displace", "voxel"}

FUENTES_DOC = [
    # (prefijo, url con {ver}, título, tipo)
    ("bmesh.ops", "https://docs.blender.org/api/{ver}/bmesh.ops.html", "Blender Python API — bmesh.ops", "official_docs"),
    ("bpy.ops.mesh", "https://docs.blender.org/api/{ver}/bpy.ops.mesh.html", "Blender Python API — bpy.ops.mesh", "official_docs"),
    ("modificador", "https://docs.blender.org/api/{ver}/bpy_types_enum_items/object_modifier_type_items.html",
     "Blender Python API — tipos de modificador", "official_docs"),
]
FUENTE_OPDEFINES = ("bmesh.ops", "https://raw.githubusercontent.com/blender/blender/v{version}/source/blender/bmesh/intern/bmesh_opdefines.cc",
                    "Blender (código oficial) — definiciones de operadores BMesh", "official_docs")


# ================================================================ texto
def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(texto: str) -> list[str]:
    """Palabras en minúscula, partiendo identificadores (bisect_plane → bisect, plane)."""
    t = normalizar(re.sub(r"([a-z])([A-Z])", r"\1 \2", texto))
    return [w for w in re.findall(r"[a-z][a-z0-9]+", t.replace("_", " ")) if w not in VACIAS]


def raiz_en(w: str) -> str:
    """Raíz ingenua en inglés: fingers → finger, separated → separat(e)."""
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 + len(suf) and w.endswith(suf):
            return w[: -len(suf)]
    return w


def terminos(*textos: str) -> list[str]:
    """Términos de búsqueda en inglés a partir de textos en español (glosario) o inglés (tal cual)."""
    out: list[str] = []
    for texto in textos:
        for w in tokens(texto):
            for e in GLOSARIO.get(w, [w] if w.isascii() and not _parece_espanol(w) else []):
                if e not in out:
                    out.append(e)
    return out


def _parece_espanol(w: str) -> bool:
    return w.endswith(("cion", "ado", "ada", "idos", "idas", "mente", "iendo", "ando")) or \
        w in {"forma", "modelo", "objeto"}


# ================================================================ BM25
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = [[raiz_en(w) for w in d] for d in docs]
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.avg = sum(len(d) for d in self.docs) / max(self.n, 1)
        self.df: dict[str, int] = {}
        for d in self.docs:
            for w in set(d):
                self.df[w] = self.df.get(w, 0) + 1

    def puntaje(self, i: int, consulta: list[str]) -> float:
        d = self.docs[i]
        if not d:
            return 0.0
        s = 0.0
        for q in {raiz_en(w) for w in consulta}:
            f = d.count(q)
            if not f:
                continue
            idf = math.log(1 + (self.n - self.df[q] + 0.5) / (self.df[q] + 0.5))
            s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
        return s


# ================================================================ red
class Red:
    """HTTP con límites. Registra cada consulta (URL, código, bytes) para el brief."""

    def __init__(self, timeout: float = 20.0, max_bytes: int = 3_000_000, token: str | None = None):
        self.timeout, self.max_bytes, self.token = timeout, max_bytes, token
        self.registro: list[dict] = []

    def get(self, url: str, aceptar: str | None = None) -> tuple[int, str]:
        h = {"User-Agent": USER_AGENT}
        if aceptar:
            h["Accept"] = aceptar
        if self.token and "api.github.com" in url:
            h["Authorization"] = f"Bearer {self.token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=self.timeout) as r:
                cuerpo = r.read(self.max_bytes).decode("utf-8", "replace")
                codigo = r.status
        except urllib.error.HTTPError as e:
            codigo, cuerpo = e.code, ""
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            codigo, cuerpo = 0, ""
            self.registro.append({"url": url, "codigo": 0, "error": type(e).__name__})
            return codigo, cuerpo
        self.registro.append({"url": url, "codigo": codigo, "bytes": len(cuerpo)})
        return codigo, cuerpo


# ================================================================ parsers
def _texto_html(s: str) -> str:
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parsear_sphinx(pagina: str, prefijo: str) -> list[dict]:
    """Secciones de una página de la API (Sphinx): una por `id="<prefijo>.<nombre>"`."""
    marcas = list(re.finditer(r'id="(' + re.escape(prefijo) + r'\.(\w+))"', pagina))
    out = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(pagina)
        bloque = pagina[m.start():fin]
        firma = bloque.split("</dt>", 1)[0]
        params = [p for p in re.findall(r'class="sig-param"[^>]*>(?:<[^>]+>)*\s*(\w+)', firma)]
        if not params:
            params = re.findall(r'<span class="pre">(\w+)</span></span><span class="o"><span class="pre">=', firma)
        params = [x for x in params if x not in ("bm", "self")]
        out.append({"nombre": m.group(1), "texto": _texto_html(bloque)[:3000], "params": params, "tipos": {}})
    return out


def parsear_enum(pagina: str, prefijo: str = "modificador") -> list[dict]:
    """Lista de valores de un enum de la API (p. ej. tipos de modificador): <dt>NOMBRE</dt><dd>texto</dd>."""
    out = []
    for m in re.finditer(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", pagina, flags=re.S):
        clave = _texto_html(m.group(1))
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", clave):
            out.append({"nombre": f"{prefijo}:{clave}", "texto": f"{clave} {_texto_html(m.group(2))}"[:1500],
                        "params": [], "tipos": {}})
    if out:
        return out
    # otro marcado (listas): cada <code>NOMBRE</code> en mayúsculas abre un valor hasta el siguiente
    marcas = list(re.finditer(r"<code[^>]*>(?:<span[^>]*>)?\s*([A-Z][A-Z0-9_]{2,})\s*(?:</span>)?</code>", pagina))
    vistos = set()
    for i, m in enumerate(marcas):
        clave = m.group(1)
        if clave in vistos:
            continue
        vistos.add(clave)
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else min(len(pagina), m.end() + 2000)
        out.append({"nombre": f"{prefijo}:{clave}", "texto": f"{clave} {_texto_html(pagina[m.end():fin])}"[:1500],
                    "params": [], "tipos": {}})
    return out


TIPO_SLOT = {"BMO_OP_SLOT_ELEMENT_BUF": "elementos", "BMO_OP_SLOT_FLT": "float", "BMO_OP_SLOT_INT": "int",
             "BMO_OP_SLOT_BOOL": "bool", "BMO_OP_SLOT_VEC": "vector", "BMO_OP_SLOT_MAT": "matriz",
             "BMO_OP_SLOT_PTR": "puntero", "BMO_OP_SLOT_MAPPING": "mapa"}


def parsear_opdefines(cc: str) -> list[dict]:
    """bmesh_opdefines.cc (fuente de la doc de bmesh.ops): comentario + slots de entrada por operador."""
    out = []
    patron = re.compile(r"/\*((?:(?!\*/).)*?)\*/\s*(?:#[^\n]*\n\s*)*static BMOpDefine bmo_\w+_def = \{\s*/\*opname\*/ \"(\w+)\",(.*?)"
                        r"/\*slot_types_out\*/", re.S)
    for m in patron.finditer(cc):
        doc = re.sub(r"\s*\n\s*\*\s?", " ", m.group(1)).strip(" *")
        slots = re.findall(r"(?:/\*\s*((?:(?!\*/).)*?)\s*\*/\s*)?\{\"(\w+)\",\s*(BMO_OP_SLOT_\w+)", m.group(3), re.S)
        params = [s[1] for s in slots]
        texto = doc + " " + " ".join(f"{s[1]} {s[0]}" for s in slots)
        out.append({"nombre": f"bmesh.ops.{m.group(2)}", "texto": re.sub(r"\s+", " ", texto)[:3000],
                    "params": params, "tipos": {s[1]: TIPO_SLOT.get(s[2], s[2]) for s in slots}})
    return out


def _nombre_punteado(n: ast.AST) -> str | None:
    partes = []
    while isinstance(n, ast.Attribute):
        partes.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name):
        partes.append(n.id)
        return ".".join(reversed(partes))
    return None


def _literal(n: ast.AST):
    try:
        return ast.literal_eval(n)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def extraer_llamadas(codigo: str) -> list[dict]:
    """Llamadas concretas en un ejemplo de código: operador + parámetros (literal si se puede, si no '<expr>')."""
    try:
        arbol = ast.parse(codigo)
    except (SyntaxError, ValueError):
        return _extraer_llamadas_regex(codigo)
    out = []
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call):
            continue
        nombre = _nombre_punteado(n.func) or ""
        params = {}
        for kw in n.keywords:
            if kw.arg:
                v = _literal(kw.value)
                params[kw.arg] = v if v is not None else "<expr>"
        if nombre.startswith(("bmesh.ops.", "bpy.ops.mesh.")):
            out.append({"tecnica": nombre, "parametros": params, "linea": n.lineno})
        elif nombre.endswith("modifiers.new"):
            tipo = params.get("type")
            if tipo is None and len(n.args) >= 2:
                tipo = _literal(n.args[1])
            if isinstance(tipo, str):
                out.append({"tecnica": f"modificador:{tipo}", "parametros": {}, "linea": n.lineno})
    out.sort(key=lambda c: c["linea"])
    return out


def _extraer_llamadas_regex(codigo: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\b(bmesh\.ops\.\w+|bpy\.ops\.mesh\.\w+)\s*\(", codigo):
        out.append({"tecnica": m.group(1), "parametros": {}, "linea": codigo[:m.start()].count("\n") + 1})
    for m in re.finditer(r"modifiers\.new\([^)]*type\s*=\s*['\"](\w+)['\"]", codigo):
        out.append({"tecnica": f"modificador:{m.group(1)}", "parametros": {}, "linea": codigo[:m.start()].count("\n") + 1})
    return sorted(out, key=lambda c: c["linea"])


def url_raw(html_url: str) -> str | None:
    m = re.match(r"https://github\.com/([^/]+/[^/]+)/blob/(.+)$", html_url or "")
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}" if m else None


# ================================================================ memoria (kb)
def _leer(ruta: Path, defecto):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def cargar_indice(ruta: Path = KB_INDICE) -> dict:
    return _leer(ruta, {"version": "1.0", "nota": "Investigaciones sin IA de tools/investigar.py. "
                        "unverified = encontrada, no probada; verified = pasó una prueba real en Blender; "
                        "failed = rechazada por un auditor (no se repite).", "entradas": []})


def guardar_json(ruta: Path, datos: dict) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(ruta)


def tecnicas_fallidas(capacidad: str, indice: dict, registro: dict) -> list[dict]:
    """Lo que NO se repite: intentos_fallidos del registro y candidatos `failed` de investigaciones previas."""
    out = []
    for t in (registro.get("capacidades", {}).get(capacidad, {}) or {}).get("intentos_fallidos", []):
        out.append({"tecnica": t.get("tecnica", ""), "motivo": t.get("motivo", ""), "origen": "kb/capacidades.json",
                    "palabras": sorted(set(terminos(t.get("tecnica", ""))) & TECNICAS)})
    for e in indice.get("entradas", []):
        if e.get("capacidad") != capacidad:
            continue
        for c in e.get("candidatos", []):
            if c.get("estado") == "failed":
                out.append({"tecnica": c["tecnica"], "motivo": c.get("motivo", ""), "origen": e.get("brief"),
                            "palabras": []})
    return out


def repite_fallida(tecnica: str, fallidas: list[dict]) -> dict | None:
    """¿El candidato es una técnica que ya falló? Igual por nombre, o comparte su palabra de técnica."""
    mias = {raiz_en(w) for w in tokens(tecnica)}
    for f in fallidas:
        if f["tecnica"] == tecnica:
            return f
        if mias & {raiz_en(w) for w in f["palabras"]}:
            return f
    return None


def verificada_vigente(capacidad: str, version: str, indice: dict) -> dict | None:
    for e in reversed(indice.get("entradas", [])):
        if e.get("capacidad") == capacidad and e.get("blender") == version:
            for c in e.get("candidatos", []):
                if c.get("estado") == "verified":
                    return {"entrada": e, "candidato": c}
    return None


# ================================================================ buscar
def version_blender() -> str:
    try:
        import bpy  # noqa: F401
        return ".".join(str(x) for x in bpy.app.version)
    except ImportError:
        return os.environ.get("ALTH_BLENDER_VERSION", VERSION_BLENDER_DEFECTO)


def recolectar_docs(red: Red, version: str, plazo: float) -> tuple[list[dict], list[dict]]:
    """Secciones de operadores de las páginas oficiales. Devuelve (secciones, fuentes usadas)."""
    ver = ".".join(version.split(".")[:2])
    secciones, fuentes = [], []
    bmesh_ok = False
    for prefijo, url, titulo, tipo in FUENTES_DOC:
        if time.time() > plazo:
            break
        for u in (url.format(ver=ver), url.format(ver="current")):
            codigo, pagina = red.get(u)
            if codigo == 200 and pagina:
                sec = parsear_enum(pagina) if prefijo == "modificador" else parsear_sphinx(pagina, prefijo)
                if sec:
                    for s in sec:
                        s["url"] = u + ("#" + s["nombre"] if not s["nombre"].startswith("modificador:") else "")
                    secciones += sec
                    fuentes.append({"title": titulo, "url": u, "source_type": tipo, "secciones": len(sec)})
                    bmesh_ok |= prefijo == "bmesh.ops"
                    break
    if not bmesh_ok and time.time() < plazo:   # respaldo: la fuente de la doc en el repo oficial
        prefijo, url, titulo, tipo = FUENTE_OPDEFINES
        u = url.format(version=version)
        codigo, cc = red.get(u)
        sec = parsear_opdefines(cc) if codigo == 200 else []
        for s in sec:
            s["url"] = u
        if sec:
            secciones += sec
            fuentes.append({"title": titulo, "url": u, "source_type": tipo, "secciones": len(sec)})
    return secciones, fuentes


def _agregar_ejemplo(red: Red, ejemplos: list, vistos: set, html_url: str, repo: str, ruta: str) -> None:
    raw = url_raw(html_url)
    if not raw or raw in vistos:
        return
    vistos.add(raw)
    c, texto = red.get(raw)
    if c != 200 or not texto:
        return
    llamadas = extraer_llamadas(texto)
    if llamadas:
        ejemplos.append({"url": html_url, "repo": repo, "ruta": ruta, "llamadas": llamadas, "texto": texto[:20000]})


def buscar_codigo(red: Red, consultas: list[str], max_archivos: int, plazo: float,
                  consulta_repos: str | None = None, max_repos: int = 4) -> list[dict]:
    """Ejemplos publicados con la API de GitHub.

    1. Búsqueda de código (`search/code`): con un token personal busca en todo GitHub; con el token de
       Actions suele no devolver repos ajenos.
    2. Respaldo que sí funciona con el token de Actions: búsqueda de repositorios públicos
       (`search/repositories`), árbol de cada repo y los .py cuyo nombre coincide con la consulta.
    """
    if not red.token:
        return []
    vistos, ejemplos = set(), []
    for q in consultas:
        if time.time() > plazo or len(ejemplos) >= max_archivos:
            break
        url = "https://api.github.com/search/code?per_page=10&q=" + urllib.parse.quote(q)
        codigo, cuerpo = red.get(url, aceptar="application/vnd.github.text-match+json")
        if codigo != 200:
            break                    # 403/422/429: este token no puede buscar código; no insistir
        for item in json.loads(cuerpo or "{}").get("items", []):
            if len(ejemplos) >= max_archivos or time.time() > plazo:
                break
            _agregar_ejemplo(red, ejemplos, vistos, item.get("html_url", ""),
                             item.get("repository", {}).get("full_name", ""), item.get("path", ""))
    if len(ejemplos) >= max_archivos or not consulta_repos or time.time() > plazo:
        return ejemplos
    # de lo específico a lo general: con los términos, con el primero, y solo "bmesh"
    palabras_q = consulta_repos.split()
    repos = []
    for q in dict.fromkeys([" ".join(palabras_q), " ".join(palabras_q[:2]), palabras_q[0]]):
        if time.time() > plazo:
            break
        url = ("https://api.github.com/search/repositories?sort=stars&order=desc&per_page=10&q="
               + urllib.parse.quote(q + " language:Python"))
        codigo, cuerpo = red.get(url)
        repos = json.loads(cuerpo or "{}").get("items", []) if codigo == 200 else []
        if repos:
            break
    palabras = {raiz_en(w) for w in tokens(consulta_repos)} | {"bmesh", "mesh", "op"}
    for r in repos[:max_repos]:
        if len(ejemplos) >= max_archivos or time.time() > plazo:
            break
        nombre, rama = r.get("full_name", ""), r.get("default_branch", "main")
        c, cuerpo = red.get(f"https://api.github.com/repos/{nombre}/git/trees/{urllib.parse.quote(rama)}?recursive=1")
        if c != 200:
            continue
        pys = [t["path"] for t in json.loads(cuerpo or "{}").get("tree", [])
               if t.get("type") == "blob" and t.get("path", "").endswith(".py") and t.get("size", 0) < 200_000]
        pys.sort(key=lambda ruta: -len({raiz_en(w) for w in tokens(ruta)} & palabras))
        for ruta in pys[:6]:
            if len(ejemplos) >= max_archivos or time.time() > plazo:
                break
            _agregar_ejemplo(red, ejemplos, vistos, f"https://github.com/{nombre}/blob/{rama}/{ruta}", nombre, ruta)
    return ejemplos


def _principio(texto: str) -> str:
    t = re.sub(r"^\s*(bmesh\.ops\.|bpy\.ops\.mesh\.)?\w+\s*\([^)]*\)\s*", "", texto)
    return (re.split(r"(?<=\.)\s", t, maxsplit=1)[0] if t else "")[:240]


def ejecutable(tecnica: str) -> tuple[bool, str]:
    if tecnica.startswith("bmesh.ops."):
        return True, "bmesh.ops trabaja sobre datos (sin interfaz)"
    if tecnica.startswith("modificador:"):
        return True, "modificador evaluado por datos (sin interfaz)"
    return False, "bpy.ops depende del contexto de interfaz/viewport (regla ALTH): buscar su equivalente en bmesh.ops"


def puntuar(secciones: list[dict], ejemplos: list[dict], consulta: list[str], fallidas: list[dict],
            max_candidatos: int = 8) -> tuple[list[dict], list[dict]]:
    """Candidatos (aplicables y descartados) ordenados por BM25 de su documentación + sus ejemplos."""
    docs = [tokens(s["texto"]) + tokens(s["nombre"]) for s in secciones]
    bm = BM25(docs)
    por_nombre: dict[str, dict] = {}

    def entrada(s):
        return por_nombre.setdefault(s["nombre"], {
            "tecnica": s["nombre"], "puntaje_doc": 0.0, "puntaje_ejemplos": 0.0, "params_doc": s["params"],
            "tipos": s.get("tipos", {}), "principio": _principio(s["texto"]), "fuentes": [], "parametros": {},
            "ejemplos": []})

    documentadas = {}
    for i, s in enumerate(secciones):
        documentadas.setdefault(s["nombre"], s)
        p = bm.puntaje(i, consulta)
        if p > 0:
            c = entrada(s)
            c["puntaje_doc"] = max(c["puntaje_doc"], p)
            c["fuentes"].append(s.get("url", ""))
    if ejemplos:
        bm_e = BM25([tokens(e["texto"]) for e in ejemplos])
        for i, e in enumerate(ejemplos):
            pe = bm_e.puntaje(i, consulta)
            if pe <= 0:
                continue
            for ll in e["llamadas"]:
                s = documentadas.get(ll["tecnica"])
                if s is None:
                    continue                    # solo operadores que también documenta la fuente oficial
                c = entrada(s)
                if s.get("url", "") not in c["fuentes"]:
                    c["fuentes"].append(s.get("url", ""))
                c["puntaje_ejemplos"] += pe / len(e["llamadas"])
                if e["url"] not in c["ejemplos"]:
                    c["ejemplos"].append(e["url"])
                for k, v in ll["parametros"].items():
                    if v != "<expr>" and k not in c["parametros"]:
                        c["parametros"][k] = v
    aplicables, descartadas = [], []
    for c in sorted(por_nombre.values(), key=lambda c: -(c["puntaje_doc"] + 0.5 * c["puntaje_ejemplos"])):
        c["puntaje"] = round(c["puntaje_doc"] + 0.5 * c["puntaje_ejemplos"], 4)
        c["puntaje_doc"], c["puntaje_ejemplos"] = round(c["puntaje_doc"], 4), round(c["puntaje_ejemplos"], 4)
        f = repite_fallida(c["tecnica"], fallidas)
        ok, motivo = ejecutable(c["tecnica"])
        if f:
            descartadas.append({**c, "motivo": f"repite una técnica fallida: {f['tecnica']} ({f['motivo']})"})
        elif not ok:
            descartadas.append({**c, "motivo": motivo})
        elif len(aplicables) < max_candidatos:
            c["estado"] = "unverified"
            aplicables.append(c)
    return aplicables, descartadas


def slug(t: str) -> str:
    return "-".join(tokens(t))[:40].strip("-") or "problema"


def armar_brief(capacidad: str, problema: str, version: str, consulta: list[str], fuentes: list[dict],
                ejemplos: list[dict], aplicables: list[dict], descartadas: list[dict], fallidas: list[dict],
                registro_red: list[dict], ahora: datetime) -> dict:
    rid = f"{capacidad}-{slug(problema)}-{ahora.strftime('%Y%m%d%H%M%S')}"
    sel = aplicables[0]["tecnica"] if aplicables else None
    usadas = {u for c in aplicables for u in c["fuentes"] + c["ejemplos"]}
    srcs = []
    for f in fuentes:
        rel = [c["tecnica"] for c in aplicables if any(u.startswith(f["url"]) for u in c["fuentes"])]
        if rel:
            srcs.append({"title": f["title"], "url": f["url"], "source_type": f["source_type"],
                         "relevance": "documenta " + ", ".join(rel[:6])})
    for e in ejemplos:
        rel = [c["tecnica"] for c in aplicables if e["url"] in c["ejemplos"]]
        if rel and e["url"] in usadas:
            srcs.append({"title": f"{e['repo']} — {e['ruta']}", "url": e["url"], "source_type": "community",
                         "relevance": "ejemplo publicado que llama " + ", ".join(rel[:4])})
    tecnicas = [{"name": c["tecnica"], "applicable": True, "principle": c["principio"],
                 "parametros": c["parametros"], "params_doc": c["params_doc"], "tipos": c["tipos"],
                 "puntaje": c["puntaje"], "fuentes": c["fuentes"][:3], "ejemplos": c["ejemplos"][:5],
                 "estado": "unverified"} for c in aplicables]
    en_red = any(r.get("codigo") == 200 for r in registro_red)
    return {
        "research_id": rid, "module": capacidad, "problem": problema,
        "date": ahora.date().isoformat(), "researched_at": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "READY", "estado": "unverified", "blender": version,
        "web_research_performed": en_red, "internet_checked": en_red,
        "research_prepared_by": "tools/investigar.py (sin IA: descarga + BM25 + extracción de llamadas)",
        "consulta": consulta, "consultas_http": registro_red,
        "sources": srcs, "techniques": tecnicas,
        "techniques_found": [c["tecnica"] for c in aplicables],
        "techniques_rejected": [{"name": c["tecnica"], "reason": c["motivo"]} for c in descartadas],
        "no_repetir": [{"tecnica": f["tecnica"], "motivo": f["motivo"], "origen": f["origen"]} for f in fallidas],
        "selected_technique": sel,
        "reason": (f"mayor puntaje BM25 ({aplicables[0]['puntaje']}) entre {len(aplicables)} candidatos ejecutables "
                   "sin interfaz que no repiten técnicas fallidas") if sel else "sin candidatos",
        "risks": ["unverified: es un hallazgo de búsqueda, no está probado; solo una prueba real en Blender lo sube "
                  "a verified", "el puntaje mide coincidencia de palabras, no que la técnica resuelva el problema"],
        "implementation_notes": "alth-python tools/investigar.py probar <este brief> aplica cada candidato a un "
                                "banco de prueba y lo pasa por los auditores (integridad de malla + banco de la capacidad).",
        "candidatos": [{"tecnica": c["tecnica"], "estado": "unverified"} for c in aplicables],
    }


def buscar(capacidad: str, problema: str, red: Red, *, version: str | None = None, max_candidatos: int = 8,
           max_ejemplos: int = 12, max_segundos: float = 240.0, guardar: bool = True,
           kb_indice: Path = KB_INDICE, kb_briefs: Path = KB_BRIEFS, kb_capacidades: Path = KB_CAPACIDADES,
           ahora: datetime | None = None) -> dict:
    """Paso 1-3 y 5. Devuelve {"estado": USAR_VERIFICADA | CANDIDATOS | RESEARCH_REQUIRED, ...}."""
    t0 = time.time()
    plazo = t0 + max_segundos
    version = version or version_blender()
    ahora = ahora or datetime.now(timezone.utc)
    indice = cargar_indice(kb_indice)
    registro = _leer(kb_capacidades, {"capacidades": {}})
    vocab = _leer(VOCAB, {"capacidades": {}})

    previa = verificada_vigente(capacidad, version, indice)
    if previa:
        return {"estado": "USAR_VERIFICADA", "capacidad": capacidad, "tecnica": previa["candidato"]["tecnica"],
                "brief": previa["entrada"].get("brief"), "blender": version, "segundos": round(time.time() - t0, 2)}

    fallidas = tecnicas_fallidas(capacidad, indice, registro)
    entrada_vocab = vocab.get("capacidades", {}).get(capacidad, {})
    consulta = terminos(problema, capacidad.replace("_", " "), entrada_vocab.get("descripcion", ""),
                        " ".join(entrada_vocab.get("palabras", [])))
    secciones, fuentes = recolectar_docs(red, version, plazo)
    principales = [t for t in consulta if t not in {"mesh", "face", "edge", "vertex", "vert"}][:4]
    consultas_codigo = [" ".join(principales[:3]) + " bmesh language:Python"] if principales else []
    if secciones and principales:
        prev, _ = puntuar(secciones, [], consulta, fallidas, max_candidatos=3)
        consultas_codigo += [f"{c['tecnica']} {principales[0]} language:Python" for c in prev]
    consulta_repos = " ".join(["bmesh"] + principales[:2]) if principales else None
    ejemplos = buscar_codigo(red, consultas_codigo, max_ejemplos, plazo, consulta_repos)
    aplicables, descartadas = puntuar(secciones, ejemplos, consulta, fallidas, max_candidatos)
    brief = armar_brief(capacidad, problema, version, consulta, fuentes, ejemplos, aplicables, descartadas,
                        fallidas, red.registro, ahora)
    gate = validate_research(brief, capacidad, technique=brief["selected_technique"]) if aplicables else \
        {"status": "RESEARCH_REQUIRED", "reasons": ["sin_candidatos"]}
    if not any(r.get("codigo") == 200 for r in red.registro):
        gate = {"status": "RESEARCH_REQUIRED", "reasons": ["sin_red"] + gate.get("reasons", [])}
    brief["gate"] = {"status": gate["status"], "reasons": gate.get("reasons", [])}
    res = {"estado": "CANDIDATOS" if gate["status"] == "READY" else "RESEARCH_REQUIRED", "capacidad": capacidad,
           "problema": problema, "blender": version, "candidatos": brief["techniques_found"],
           "descartadas": brief["techniques_rejected"], "no_repetir": brief["no_repetir"],
           "fuentes": [s["url"] for s in brief["sources"]], "gate": brief["gate"],
           "segundos": round(time.time() - t0, 2), "brief": brief}
    if res["estado"] == "RESEARCH_REQUIRED":
        brief["status"] = "RESEARCH_REQUIRED"
    if guardar and res["estado"] == "CANDIDATOS":
        ruta = Path(kb_briefs) / f"{brief['research_id']}.json"
        guardar_json(ruta, brief)
        indice["entradas"].append({"capacidad": capacidad, "problema": problema, "blender": version,
                                   "brief": _rel(ruta), "fecha": brief["date"], "candidatos": brief["candidatos"]})
        guardar_json(kb_indice, indice)
        res["ruta_brief"] = _rel(ruta)
    return res


def _rel(p: Path) -> str:
    p = Path(p).resolve()
    return str(p.relative_to(RAIZ)) if RAIZ in p.parents else str(p)


# ================================================================ probar (Blender)
def marcar(indice: dict, brief: dict, ruta_brief: str, tecnica: str, estado: str, motivo: str,
           evidencia: list[str] | None = None) -> None:
    """Actualiza el estado de un candidato en el brief y en el índice. verified/failed/unverified."""
    assert estado in ("verified", "failed", "unverified")
    for lista in (brief.get("candidatos", []),
                  *[e["candidatos"] for e in indice.get("entradas", []) if e.get("brief") == ruta_brief]):
        for c in lista:
            if c["tecnica"] == tecnica:
                c.update({"estado": estado, "motivo": motivo, "evidencia": evidencia or [],
                          "probado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    for t in brief.get("techniques", []):
        if t["name"] == tecnica:
            t["estado"] = estado
    estados = {c["estado"] for c in brief.get("candidatos", [])}
    brief["estado"] = "verified" if "verified" in estados else ("failed" if estados == {"failed"} else "unverified")


def cargar_banco(capacidad: str):
    """Banco propio de la capacidad (tools/bancos/<capacidad>.py) o el genérico de integridad."""
    import importlib.util
    for nombre in (capacidad, "integridad"):
        ruta = BANCOS / f"{nombre}.py"
        if ruta.exists():
            spec = importlib.util.spec_from_file_location(f"banco_{nombre}", ruta)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return nombre, mod
    raise FileNotFoundError("falta tools/bancos/integridad.py")


def probar(ruta_brief: Path, max_candidatos: int = 8, salida: Path | None = None,
           kb_indice: Path = KB_INDICE) -> dict:
    brief = json.loads(Path(ruta_brief).read_text(encoding="utf-8"))
    rel = _rel(Path(ruta_brief))
    indice = cargar_indice(kb_indice)
    nombre_banco, banco = cargar_banco(brief["module"])
    propio = nombre_banco == brief["module"]
    salida = Path(salida or RAIZ / ".linea" / "investigar" / brief["research_id"])
    resultados = []
    tecnicas = {t["name"]: t for t in brief.get("techniques", [])}
    for c in brief.get("candidatos", [])[:max_candidatos]:
        if c["estado"] != "unverified":
            continue
        t = tecnicas.get(c["tecnica"], {"name": c["tecnica"]})
        r = banco.probar(t, salida / slug(c["tecnica"]))
        if r["ok"] is None:
            estado = "unverified"          # no se pudo ejercitar: no es evidencia en contra
        elif not r["ok"]:
            estado = "failed"
        elif propio:
            estado = "verified"
        else:
            estado = "unverified"
            r["motivo"] = "integridad OK, pero no hay banco de la capacidad: sigue sin verificar. " + r.get("motivo", "")
        marcar(indice, brief, rel, c["tecnica"], estado, r.get("motivo", ""), r.get("evidencia", []))
        resultados.append({"tecnica": c["tecnica"], "estado": estado, **{k: v for k, v in r.items() if k != "ok"}})
    guardar_json(Path(ruta_brief), brief)
    guardar_json(kb_indice, indice)
    return {"brief": rel, "banco": nombre_banco, "resultados": resultados, "estado_brief": brief["estado"]}


# ================================================================ CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buscar", help="pasos 1-3: memoria, red, brief unverified")
    b.add_argument("capacidad")
    b.add_argument("problema")
    b.add_argument("--max-candidatos", type=int, default=8)
    b.add_argument("--max-ejemplos", type=int, default=12)
    b.add_argument("--max-segundos", type=float, default=240.0)
    b.add_argument("--no-guardar", action="store_true")
    pr = sub.add_parser("probar", help="paso 4: prueba real en Blender (alth-python)")
    pr.add_argument("brief")
    pr.add_argument("--max-candidatos", type=int, default=8)
    pr.add_argument("--salida", default=None)
    e = sub.add_parser("estado", help="qué sabe la memoria de una capacidad")
    e.add_argument("capacidad")
    a = p.parse_args(argv)
    if a.cmd == "buscar":
        red = Red(token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
        r = buscar(a.capacidad, a.problema, red, max_candidatos=a.max_candidatos, max_ejemplos=a.max_ejemplos,
                   max_segundos=a.max_segundos, guardar=not a.no_guardar)
        brief = r.pop("brief", None) or {}
        r["consultas_http"] = [f"{x.get('codigo')} {x['url']}" for x in brief.get("consultas_http", [])]
        r["ejemplos_de_codigo"] = sorted({u for t in brief.get("techniques", []) for u in t.get("ejemplos", [])})
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if r["estado"] == "RESEARCH_REQUIRED":
            print(f"RESEARCH_REQUIRED: {', '.join(r['gate']['reasons'])}", file=sys.stderr)
            return SALIDA_RESEARCH_REQUIRED
        return 0
    if a.cmd == "probar":
        print(json.dumps(probar(Path(a.brief), a.max_candidatos, Path(a.salida) if a.salida else None),
                         ensure_ascii=False, indent=2, default=str))
        return 0
    indice = cargar_indice()
    reg = _leer(KB_CAPACIDADES, {"capacidades": {}})
    print(json.dumps({"capacidad": a.capacidad, "registro": reg.get("capacidades", {}).get(a.capacidad),
                      "investigaciones": [e for e in indice["entradas"] if e["capacidad"] == a.capacidad],
                      "no_repetir": tecnicas_fallidas(a.capacidad, indice, reg)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
