"""ALTH-META · reconocimiento de imagen: foto de referencia → FICHA JSON del asset.

Es el primer paso de la "línea única": antes de modelar nada, el proceso mira la imagen y dice
qué es y qué capacidades técnicas exige. Después tools/capacidades.py compara esa ficha con el
registro (kb/capacidades.json) para saber si "ya sabe hacerlo" o si hay que investigar.

El modelo de visión SOLO describe y elige capacidades de un vocabulario controlado
(spec/capacidades_vocab.json). Nunca decide si el proceso "sabe" hacerlo: eso lo decide la evidencia
del registro. Lo que el modelo mencione y no esté en el vocabulario se guarda aparte como
`capacidades_nuevas` (a investigar), no se acepta sin más.

Tres formas de usarlo (misma lógica que tools/bucle.py):

  # 1) Automático, con un proveedor GRATIS que tenga visión (Gemini; Groq NO sirve aquí: no ve imágenes)
  GEMINI_API_KEY=… python3 tools/reconocer.py reconocer refs/pendientes/espada.jpg --salida ficha.json

  # 2) Manual, sin API ni gasto: arma el prompt para pegarlo en cualquier chat gratis con imágenes…
  python3 tools/reconocer.py paquete refs/pendientes/espada.jpg
  #    …y aplica la respuesta pegada:
  python3 tools/reconocer.py aplicar respuesta.md --imagen refs/pendientes/espada.jpg --salida ficha.json

  # 3) Validar una ficha ya escrita
  python3 tools/reconocer.py validar ficha.json

Sin red ni clave NO inventa nada: se detiene y explica qué falta (modo manual disponible).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
VOCAB_RUTA = RAIZ / "spec" / "capacidades_vocab.json"

MAX_CAPACIDADES = 25
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------- vocabulario
def cargar_vocab(ruta: Path = VOCAB_RUTA) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- prompt
def prompt_reconocimiento(vocab: dict, nota: str = "") -> tuple[str, str]:
    """Devuelve (sistema, texto). El modelo debe contestar SOLO con un objeto JSON."""
    caps = "\n".join(f"  - {k}: {v['descripcion']}" for k, v in vocab["capacidades"].items())
    tipos = ", ".join(vocab["tipos"])
    sistema = (
        "Eres el reconocedor de ALTH-META, un estilo 3D chibi-soft low-poly para un videojuego. "
        "Miras una imagen de referencia y describes QUÉ es y QUÉ técnicas de modelado exige. "
        "No modelas, no das código, no opinas sobre si es fácil o difícil. "
        "Contestas SOLO con un objeto JSON válido, sin texto antes ni después."
    )
    texto = f"""Analiza la imagen y devuelve un JSON con exactamente estas claves:

{{
  "tipo": uno de [{tipos}],
  "nombre": "nombre corto en español, minúsculas, sin acentos ni espacios (usa guion bajo)",
  "descripcion": "una o dos frases: qué se ve",
  "partes": ["piezas visibles que habría que modelar, una por elemento"],
  "capacidades": [{{"id": "id del vocabulario", "motivo": "qué de la imagen lo exige"}}],
  "capacidades_nuevas": [{{"id": "nombre_en_snake_case", "motivo": "qué técnica falta en el vocabulario"}}],
  "tamano_real_mm": {{"alto": numero o null, "ancho": numero o null, "fondo": numero o null}},
  "fuente_tamano": "visible" | "estimado" | "desconocido",
  "colores_dominantes": ["#RRGGBB", "..."],
  "confianza": numero entre 0 y 1
}}

Reglas:
- En "capacidades" usa SOLO ids de esta lista (si algo no cabe, va en "capacidades_nuevas"):
{caps}
- Marca una capacidad solo si la imagen la exige de verdad (p. ej. "dedos" solo si se ven dedos individuales).
- "tamano_real_mm" es el tamaño del objeto REAL en milímetros. Si no hay escala visible, estímalo y pon
  "fuente_tamano": "estimado"; si no puedes, deja null y "desconocido". No inventes precisión.
- "colores_dominantes": hasta 6 colores hex medidos de la imagen, de más a menos presente.
- Si la imagen tiene varios objetos o personajes, describe el principal y menciona el resto en "partes".
"""
    if nota.strip():
        texto += f"\nIndicación del usuario: {nota.strip()}\n"
    return sistema, texto


# ---------------------------------------------------------------- extracción y validación
def extraer_json(respuesta: str) -> dict:
    """Saca el primer objeto JSON de la respuesta (aguanta ```json … ``` y texto alrededor)."""
    t = respuesta.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.IGNORECASE | re.MULTILINE).strip()
    inicio = t.find("{")
    if inicio < 0:
        raise ValueError("la respuesta no contiene un objeto JSON")
    profundidad, en_cadena, escape = 0, False, False
    for i in range(inicio, len(t)):
        c = t[i]
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 0:
                return json.loads(t[inicio:i + 1])
    raise ValueError("el JSON de la respuesta está incompleto")


def _numero_o_none(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"no es un número: {v!r}")
    if v <= 0:
        raise ValueError(f"las medidas deben ser positivas: {v!r}")
    return float(v)


def _id_valido(i) -> bool:
    return isinstance(i, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,40}", i) is not None


def validar_ficha(ficha: dict, vocab: dict) -> tuple[dict, list[str]]:
    """Valida y normaliza. Regresa (ficha_limpia, avisos). Lanza ValueError si no sirve.

    - Los ids fuera del vocabulario se MUEVEN a capacidades_nuevas (con aviso); nunca se aceptan como conocidos.
    - Medidas no positivas, tipos raros o una ficha sin capacidades son errores, no se "arreglan".
    """
    if not isinstance(ficha, dict):
        raise ValueError("la ficha debe ser un objeto JSON")
    avisos: list[str] = []
    vocab_caps = vocab["capacidades"]

    tipo = ficha.get("tipo")
    if tipo not in vocab["tipos"]:
        raise ValueError(f"tipo inválido: {tipo!r}. Opciones: {', '.join(vocab['tipos'])}")
    nombre = ficha.get("nombre")
    if not _id_valido(nombre):
        raise ValueError(f"nombre inválido: {nombre!r} (minúsculas, sin acentos ni espacios, usa guion bajo)")
    descripcion = str(ficha.get("descripcion") or "").strip()
    if not descripcion:
        raise ValueError("falta la descripción")

    partes = [str(p).strip() for p in (ficha.get("partes") or []) if str(p).strip()]
    if not partes:
        avisos.append("la ficha no lista partes; el armado de la receta tendrá menos contexto")

    caps, nuevas, vistas = [], [], set()
    for c in ficha.get("capacidades") or []:
        cid = c.get("id") if isinstance(c, dict) else c
        motivo = str(c.get("motivo", "")).strip() if isinstance(c, dict) else ""
        if cid in vistas:
            continue
        vistas.add(cid)
        if cid in vocab_caps:
            caps.append({"id": cid, "motivo": motivo})
        elif _id_valido(cid):
            nuevas.append({"id": cid, "motivo": motivo or "propuesta del modelo (fuera del vocabulario)"})
            avisos.append(f"'{cid}' no está en el vocabulario: pasa a capacidades_nuevas (hay que investigarla)")
        else:
            avisos.append(f"capacidad ignorada por formato inválido: {cid!r}")
    for c in ficha.get("capacidades_nuevas") or []:
        cid = c.get("id") if isinstance(c, dict) else c
        motivo = str(c.get("motivo", "")).strip() if isinstance(c, dict) else ""
        if cid in vistas or not _id_valido(cid):
            continue
        vistas.add(cid)
        if cid in vocab_caps:
            caps.append({"id": cid, "motivo": motivo})
            avisos.append(f"'{cid}' venía como nueva pero ya está en el vocabulario: se movió a capacidades")
        else:
            nuevas.append({"id": cid, "motivo": motivo})
    if not caps and not nuevas:
        raise ValueError("la ficha no declara ninguna capacidad: no hay nada que comparar contra el registro")
    if len(caps) + len(nuevas) > MAX_CAPACIDADES:
        raise ValueError(f"demasiadas capacidades ({len(caps) + len(nuevas)} > {MAX_CAPACIDADES}): la ficha no es confiable")

    medidas = ficha.get("tamano_real_mm") or {}
    if not isinstance(medidas, dict):
        raise ValueError("tamano_real_mm debe ser un objeto {alto, ancho, fondo}")
    tam = {k: _numero_o_none(medidas.get(k)) for k in ("alto", "ancho", "fondo")}
    fuente = ficha.get("fuente_tamano", "desconocido")
    if fuente not in ("visible", "estimado", "desconocido"):
        raise ValueError(f"fuente_tamano inválida: {fuente!r}")
    if all(v is None for v in tam.values()):
        if fuente != "desconocido":
            avisos.append("sin medidas pero fuente_tamano no es 'desconocido': se corrigió")
        fuente = "desconocido"
    elif fuente == "desconocido":
        fuente = "estimado"
        avisos.append("trae medidas pero fuente_tamano='desconocido': se marcó como 'estimado'")

    colores = []
    for c in ficha.get("colores_dominantes") or []:
        if isinstance(c, str) and HEX.match(c):
            colores.append(c.upper())
        else:
            avisos.append(f"color ignorado (no es #RRGGBB): {c!r}")
    colores = colores[:6]

    conf = ficha.get("confianza", 0.0)
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
        raise ValueError(f"confianza debe estar entre 0 y 1: {conf!r}")
    if conf < 0.5:
        avisos.append(f"confianza baja ({conf:.2f}): conviene revisar la ficha antes de seguir")

    limpia = {"tipo": tipo, "nombre": nombre, "descripcion": descripcion, "partes": partes,
              "capacidades": caps, "capacidades_nuevas": nuevas, "tamano_real_mm": tam,
              "fuente_tamano": fuente, "colores_dominantes": colores, "confianza": float(conf)}
    return limpia, avisos


# ---------------------------------------------------------------- llamada al modelo
def cadena_con_vision(cadena: list[dict]) -> list[dict]:
    """Reconocer exige ver la imagen: se descartan los proveedores sin visión (p. ej. Groq)."""
    return [c for c in cadena if c.get("vision")]


def reconocer(imagen: Path, cadena: list[dict], vocab: dict, nota: str = "",
              reintentos_formato: int = 1, llamar=None) -> dict:
    """Imagen → ficha validada (con metadatos). `llamar` se inyecta en las pruebas; por defecto
    usa tools/bucle.llamar_con_respaldo (misma cadena de proveedores y reintentos que el bucle)."""
    if llamar is None:
        import bucle
        llamar = bucle.llamar_con_respaldo
    cadena = cadena_con_vision(cadena)
    if not cadena:
        raise SystemExit(
            "[reconocer] ningún proveedor configurado puede ver imágenes. Define GEMINI_API_KEY "
            "(gratis) o usa el modo manual:  python3 tools/reconocer.py paquete <imagen>")
    sistema, texto = prompt_reconocimiento(vocab, nota)
    imagenes = [("referencia", Path(imagen), None)]
    ultimo_error = ""
    for intento in range(reintentos_formato + 1):
        pedido = texto if not ultimo_error else (
            texto + f"\n\nTu respuesta anterior no fue válida: {ultimo_error}\nCorrígela y devuelve SOLO el JSON.")
        respuesta, cfg = llamar(cadena, sistema, pedido, imagenes, 0.2)
        try:
            ficha, avisos = validar_ficha(extraer_json(respuesta), vocab)
        except (ValueError, json.JSONDecodeError) as e:
            ultimo_error = str(e)
            print(f"[reconocer] respuesta inválida ({ultimo_error}); "
                  f"{'reintento' if intento < reintentos_formato else 'sin más reintentos'}")
            continue
        return _con_metadatos(ficha, avisos, Path(imagen), cfg.get("nombre"), cfg.get("modelo"))
    raise SystemExit(f"[reconocer] el modelo no devolvió una ficha válida: {ultimo_error}")


def _con_metadatos(ficha: dict, avisos: list[str], imagen: Path, proveedor, modelo) -> dict:
    sha = hashlib.sha256(Path(imagen).read_bytes()).hexdigest() if Path(imagen).exists() else None
    ficha = dict(ficha)
    ficha["_meta"] = {"imagen": str(imagen), "imagen_sha256": sha, "proveedor": proveedor, "modelo": modelo,
                      "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "avisos": avisos}
    return ficha


# ---------------------------------------------------------------- comandos
def _guardar(ficha: dict, salida: Path) -> None:
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(ficha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resumen(ficha: dict) -> str:
    caps = ", ".join(c["id"] for c in ficha["capacidades"]) or "—"
    nuevas = ", ".join(c["id"] for c in ficha["capacidades_nuevas"]) or "—"
    return (f"{ficha['nombre']} ({ficha['tipo']}) · confianza {ficha['confianza']:.2f}\n"
            f"  capacidades: {caps}\n  nuevas (a investigar): {nuevas}")


def cmd_reconocer(args) -> int:
    import bucle
    imagen = Path(args.imagen)
    if not imagen.exists():
        sys.exit(f"[reconocer] no existe la imagen: {imagen}")
    ficha = reconocer(imagen, bucle.config_cadena(args), cargar_vocab(), args.nota or "")
    _guardar(ficha, Path(args.salida))
    print(_resumen(ficha))
    for a in ficha["_meta"]["avisos"]:
        print(f"  aviso: {a}")
    print(f"[reconocer] ficha guardada en {args.salida}")
    return 0


def cmd_paquete(args) -> int:
    imagen = Path(args.imagen)
    if not imagen.exists():
        sys.exit(f"[reconocer] no existe la imagen: {imagen}")
    sistema, texto = prompt_reconocimiento(cargar_vocab(), args.nota or "")
    destino = Path(args.destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(f"{sistema}\n\n---\n\n{texto}\n\n(Adjunta la imagen: {imagen})\n", encoding="utf-8")
    print(f"[reconocer] prompt listo en {destino}. Pégalo en un chat con imágenes, adjunta {imagen} "
          f"y guarda la respuesta; luego:\n  python3 tools/reconocer.py aplicar respuesta.md --imagen {imagen}")
    return 0


def cmd_aplicar(args) -> int:
    try:
        ficha, avisos = validar_ficha(extraer_json(Path(args.respuesta).read_text(encoding="utf-8")), cargar_vocab())
    except (ValueError, json.JSONDecodeError) as e:
        sys.exit(f"[reconocer] la respuesta no es una ficha válida: {e}")
    ficha = _con_metadatos(ficha, avisos, Path(args.imagen) if args.imagen else Path("(manual)"), "manual", None)
    _guardar(ficha, Path(args.salida))
    print(_resumen(ficha))
    print(f"[reconocer] ficha guardada en {args.salida}")
    return 0


def cmd_validar(args) -> int:
    try:
        ficha, avisos = validar_ficha(json.loads(Path(args.ficha).read_text(encoding="utf-8")), cargar_vocab())
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[reconocer] ficha inválida: {e}")
        return 2
    print(_resumen(ficha))
    for a in avisos:
        print(f"  aviso: {a}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Reconocimiento de imagen → ficha JSON (ALTH-META).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconocer", help="llama a un proveedor con visión y guarda la ficha")
    r.add_argument("imagen")
    r.add_argument("--salida", default="ficha.json")
    r.add_argument("--nota", default="")
    r.add_argument("--proveedor", default=None, help="auto (por defecto) | gemini | openrouter | ollama | personalizado")
    r.add_argument("--modelo", default=None)
    r.add_argument("--sin-vision", action="store_true", help=argparse.SUPPRESS)
    r.set_defaults(fn=cmd_reconocer)

    k = sub.add_parser("paquete", help="arma el prompt para pegarlo a mano en un chat gratis con imágenes")
    k.add_argument("imagen")
    k.add_argument("--destino", default="reconocer_prompt.md")
    k.add_argument("--nota", default="")
    k.set_defaults(fn=cmd_paquete)

    a = sub.add_parser("aplicar", help="valida la respuesta pegada a mano y guarda la ficha")
    a.add_argument("respuesta")
    a.add_argument("--imagen", default=None)
    a.add_argument("--salida", default="ficha.json")
    a.set_defaults(fn=cmd_aplicar)

    v = sub.add_parser("validar", help="valida una ficha ya escrita")
    v.add_argument("ficha")
    v.set_defaults(fn=cmd_validar)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
