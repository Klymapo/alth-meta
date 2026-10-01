"""ALTH-META · registro de capacidades: ¿el proceso ya sabe hacer lo que pide la ficha?

Compara la ficha de tools/reconocer.py con kb/capacidades.json y devuelve las BRECHAS: capacidades
que hay que investigar antes de construir.

Regla central: "ya sé" lo decide la EVIDENCIA, nunca la autoevaluación de un modelo.
  - Una capacidad solo cuenta como `dominada` si trae evidencia (rutas a archivos que existan en el
    repo: un asset aprobado, una prueba auditada). Si no, se degrada a `parcial` con un aviso.
  - Lo que no está en el registro es `desconocida`.
  - Las `fallida` conservan sus intentos fallidos para NO repetirlos.
  - Una capacidad nueva (fuera del vocabulario) es siempre una brecha.

Uso:
  python3 tools/capacidades.py comparar ficha.json            # imprime JSON; código de salida 0 = listo, 3 = hay brechas
  python3 tools/capacidades.py aprender torno --estado dominada --evidencia assets/espada/final.png --motivo "Espada aprobada"
  python3 tools/capacidades.py aprender dedos --estado fallida --motivo "Método X rechazado" --tecnica "método X"

`aprender` es el paso "se retroalimenta solo": se llama cuando el usuario aprueba (dominada, con el
asset aprobado como evidencia) o cuando una prueba auditada falla (fallida, con el motivo).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REGISTRO_RUTA = RAIZ / "kb" / "capacidades.json"
VOCAB_RUTA = RAIZ / "spec" / "capacidades_vocab.json"
ESTADOS = ("dominada", "parcial", "fallida", "desconocida")


def cargar_registro(ruta: Path = REGISTRO_RUTA) -> dict:
    ruta = Path(ruta)
    if not ruta.exists():
        return {"version": "1.0", "capacidades": {}}
    return json.loads(ruta.read_text(encoding="utf-8"))


def guardar_registro(registro: dict, ruta: Path = REGISTRO_RUTA) -> None:
    registro["actualizado"] = date.today().isoformat()
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(ruta)


def evidencia_faltante(entrada: dict, raiz: Path = RAIZ) -> list[str]:
    return [e for e in entrada.get("evidencia") or [] if not (Path(raiz) / e).exists()]


def estado_efectivo(entrada: dict | None, raiz: Path = RAIZ) -> tuple[str, list[str]]:
    """(estado, avisos). Aplica la regla de la evidencia."""
    if not entrada:
        return "desconocida", []
    estado = entrada.get("estado", "desconocida")
    if estado not in ESTADOS:
        return "desconocida", [f"estado inválido en el registro: {estado!r}"]
    avisos: list[str] = []
    if estado == "dominada":
        if not entrada.get("evidencia"):
            return "parcial", ["marcada 'dominada' sin evidencia: se trata como 'parcial'"]
        faltan = evidencia_faltante(entrada, raiz)
        if faltan:
            return "parcial", [f"evidencia que no existe en el repo ({', '.join(faltan)}): se trata como 'parcial'"]
    return estado, avisos


def comparar(ficha: dict, registro: dict, vocab: dict, raiz: Path = RAIZ) -> dict:
    caps = registro.get("capacidades", {})
    resultado = {"nombre": ficha.get("nombre"), "tipo": ficha.get("tipo"),
                 "dominadas": [], "parciales": [], "fallidas": [], "desconocidas": [], "nuevas": [],
                 "brechas": [], "avisos": []}
    for c in ficha.get("capacidades", []):
        cid = c["id"]
        if cid not in vocab["capacidades"]:
            resultado["avisos"].append(f"'{cid}' no está en el vocabulario: tratada como nueva")
            resultado["nuevas"].append(cid)
            resultado["brechas"].append({"id": cid, "estado": "nueva", "motivo": c.get("motivo", ""),
                                         "evidencia": [], "no_repetir": []})
            continue
        entrada = caps.get(cid)
        estado, avisos = estado_efectivo(entrada, raiz)
        resultado["avisos"] += [f"{cid}: {a}" for a in avisos]
        clave = {"dominada": "dominadas", "parcial": "parciales", "fallida": "fallidas",
                 "desconocida": "desconocidas"}[estado]
        resultado[clave].append(cid)
        if estado != "dominada":
            resultado["brechas"].append({
                "id": cid, "estado": estado, "motivo": (entrada or {}).get("motivo", "sin registro: nunca se ha hecho"),
                "evidencia": (entrada or {}).get("evidencia", []),
                "no_repetir": [t.get("tecnica") for t in (entrada or {}).get("intentos_fallidos", [])],
                "necesidad": c.get("motivo", "")})
    for c in ficha.get("capacidades_nuevas", []):
        cid = c["id"]
        resultado["nuevas"].append(cid)
        resultado["brechas"].append({"id": cid, "estado": "nueva", "motivo": c.get("motivo", ""),
                                     "evidencia": [], "no_repetir": []})
    resultado["listo"] = not resultado["brechas"]
    return resultado


def aprender(registro: dict, capacidad: str, estado: str, motivo: str, evidencia: list[str] | None = None,
             tecnica: str | None = None, vocab: dict | None = None, raiz: Path = RAIZ) -> dict:
    """Actualiza el registro. Reglas: 'dominada' exige evidencia que exista; 'fallida' exige motivo."""
    if estado not in ("dominada", "parcial", "fallida"):
        raise ValueError("solo se aprende dominada, parcial o fallida")
    evidencia = list(evidencia or [])
    if estado == "dominada":
        if not evidencia:
            raise ValueError("'dominada' exige evidencia (asset aprobado o prueba auditada)")
        faltan = [e for e in evidencia if not (Path(raiz) / e).exists()]
        if faltan:
            raise ValueError(f"la evidencia no existe en el repo: {', '.join(faltan)}")
    if estado == "fallida" and not motivo.strip():
        raise ValueError("'fallida' exige el motivo, para no repetir el intento")
    if vocab is not None and capacidad not in vocab["capacidades"]:
        raise ValueError(f"'{capacidad}' no está en spec/capacidades_vocab.json: agrégala allí primero (decisión humana)")
    caps = registro.setdefault("capacidades", {})
    entrada = caps.setdefault(capacidad, {})
    if estado == "fallida":
        entrada.setdefault("intentos_fallidos", []).append(
            {"tecnica": tecnica or "(sin nombre)", "motivo": motivo, "evidencia": evidencia})
    elif entrada.get("estado") == "fallida" and estado == "dominada":
        entrada["motivo_anterior_fallida"] = entrada.get("motivo")
    entrada["estado"] = estado
    entrada["motivo"] = motivo
    if evidencia:
        entrada["evidencia"] = sorted(set(entrada.get("evidencia", [])) | set(evidencia))
    entrada["actualizado"] = date.today().isoformat()
    return registro


# ---------------------------------------------------------------- comandos
def cmd_comparar(args) -> int:
    ficha = json.loads(Path(args.ficha).read_text(encoding="utf-8"))
    vocab = json.loads(VOCAB_RUTA.read_text(encoding="utf-8"))
    res = comparar(ficha, cargar_registro(Path(args.registro)), vocab)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["listo"]:
        print(f"[capacidades] {res['nombre']}: todo dominado, se puede construir directo.", file=sys.stderr)
        return 0
    ids = ", ".join(f"{b['id']} ({b['estado']})" for b in res["brechas"])
    print(f"[capacidades] {res['nombre']}: faltan {len(res['brechas'])} por cerrar → {ids}", file=sys.stderr)
    return 3


def cmd_aprender(args) -> int:
    vocab = json.loads(VOCAB_RUTA.read_text(encoding="utf-8"))
    ruta = Path(args.registro)
    try:
        reg = aprender(cargar_registro(ruta), args.capacidad, args.estado, args.motivo or "",
                       args.evidencia, args.tecnica, vocab)
    except ValueError as e:
        print(f"[capacidades] no se registró: {e}", file=sys.stderr)
        return 2
    guardar_registro(reg, ruta)
    print(f"[capacidades] {args.capacidad} → {args.estado}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Registro de capacidades de ALTH-META.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("comparar")
    c.add_argument("ficha")
    c.add_argument("--registro", default=str(REGISTRO_RUTA))
    c.set_defaults(fn=cmd_comparar)
    a = sub.add_parser("aprender")
    a.add_argument("capacidad")
    a.add_argument("--estado", required=True, choices=("dominada", "parcial", "fallida"))
    a.add_argument("--motivo", default="")
    a.add_argument("--evidencia", action="append", default=[])
    a.add_argument("--tecnica", default=None)
    a.add_argument("--registro", default=str(REGISTRO_RUTA))
    a.set_defaults(fn=cmd_aprender)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
