"""Entrada única de la línea (bloque T2 de docs/BRIEF_LINEA_UNICA.md): imagen + nombre + tamaño real.

    alth-python tools/crear_asset.py --imagen refs/x.png --nombre manzana --tamano 8cm [--recorte 0.52,0.1,1,1]
                                     [--salida .linea/crear/manzana] [--max-brechas 3] [--max-segundos 900]

Encadena, sin IA ni intervención:
  reconocer → capacidades comparar → investigar (si hay brechas) → receta → construir (→ ajustar, T3)
y deja en --salida: ficha.json, capacidades.json, investigacion.json, receta.json, la hoja de 4 vistas
y resumen.json (qué quedó, qué falta y cuánto tardó). Lo que no se pudo cerrar se reporta como
faltante; nunca se inventa.
Código de salida: 0 = hoja lista para revisión, 4 = faltantes que impiden construir, 1 = falló la verificación.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))


def _guardar(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def crear(imagen: str, nombre: str, tamano: str | None, recorte=None, salida: Path | None = None,
          max_brechas: int = 3, max_segundos: float = 900.0, ajustar: bool = True, red=None) -> dict:
    import capacidades as cap
    import investigar as inv
    import receta as R
    import reconocer as rec

    t0 = time.time()
    salida = Path(salida or RAIZ / ".linea" / "crear" / rec.nombre_id(nombre))
    salida.mkdir(parents=True, exist_ok=True)
    resumen = {"nombre": nombre, "imagen": imagen, "tamano": tamano, "recorte": recorte, "pasos": {},
               "faltantes": [], "salida": str(salida)}

    def paso(n, t):
        resumen["pasos"][n] = round(time.time() - t, 2)

    # 1. reconocer
    t = time.time()
    ficha = rec.reconocer(imagen, nombre, tamano, recorte=recorte)
    _guardar(salida / "ficha.json", ficha)
    paso("reconocer", t)
    # 2. ¿ya sé hacerlo?
    t = time.time()
    vocab = rec.cargar_vocab()
    comp = cap.comparar(ficha, cap.cargar_registro(), vocab)
    _guardar(salida / "capacidades.json", comp)
    paso("capacidades", t)
    # 3. cerrar brechas (máximo de brechas y de tiempo por corrida)
    t = time.time()
    investigaciones = []
    plazo = t0 + max_segundos
    for b in comp["brechas"][:max_brechas]:
        restante = plazo - time.time()
        if restante <= 30:
            resumen["faltantes"].append({"capacidad": b["id"], "motivo": "sin tiempo para investigar en esta corrida"})
            continue
        problema = f"{b['id'].replace('_', ' ')} para {nombre}: {b.get('necesidad') or b.get('motivo', '')}"
        r = inv.buscar(b["id"], problema, red or inv.Red(token=os.environ.get("GITHUB_TOKEN")),
                       max_segundos=min(240.0, restante - 20))
        r.pop("brief", None)
        investigaciones.append(r)
        if r["estado"] != "USAR_VERIFICADA":
            resumen["faltantes"].append({"capacidad": b["id"], "motivo": f"{r['estado']}: la técnica no está verificada"
                                         + (f" (brief {r['ruta_brief']})" if r.get("ruta_brief") else "")})
    for b in comp["brechas"][max_brechas:]:
        resumen["faltantes"].append({"capacidad": b["id"], "motivo": f"fuera del máximo de {max_brechas} brechas por corrida"})
    _guardar(salida / "investigacion.json", investigaciones)
    paso("investigar", t)
    # 4. receta (código, desde la ficha)
    t = time.time()
    try:
        receta = R.armar(ficha, tamano_texto=tamano)
    except R.RecetaNoSoportada as e:
        resumen["faltantes"].append({"capacidad": "receta", "motivo": str(e)})
        resumen.update(estado="FALTANTES", segundos=round(time.time() - t0, 1))
        _guardar(salida / "resumen.json", resumen)
        return resumen
    _guardar(salida / "receta.json", receta)
    paso("receta", t)
    # 5. construir (y ajustar, T3)
    t = time.time()
    import construir_receta as C
    ref = C.mascara_referencia(receta)
    res = C.construir(receta, salida / "base", ref=ref)
    paso("construir", t)
    resumen["base"] = {k: res[k] for k in ("hoja", "iou", "iou_por_vista", "dimensiones_ok", "dif_dimensiones",
                                           "verificacion_ok", "tris", "ok")}
    final = res
    if ajustar:
        try:
            import ajustar as A
        except ImportError:
            A = None
        if A is not None:
            t = time.time()
            aj = A.ajustar(receta, salida / "ajuste", ref=ref, base=res, plazo=plazo)
            paso("ajustar", t)
            resumen["ajuste"] = {k: aj[k] for k in ("estado", "rondas", "iou_base", "iou_final", "ganador")}
            if aj.get("receta"):
                receta = aj["receta"]
                _guardar(salida / "receta.json", receta)
                final = aj["resultado"]
    resumen["final"] = {k: final[k] for k in ("hoja", "iou", "iou_por_vista", "dimensiones_ok", "dif_dimensiones",
                                              "dimensiones_mm", "verificacion_ok", "tris", "ok")}
    resumen["estado"] = "LISTO_PARA_REVISION" if final["ok"] else "VERIFICACION_FALLIDA"
    resumen["segundos"] = round(time.time() - t0, 1)
    _guardar(salida / "resumen.json", resumen)
    return resumen


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--imagen", required=True)
    p.add_argument("--nombre", required=True)
    p.add_argument("--tamano", default=None, help="tamaño REAL: '8cm', '10x8cm', 'alto=10cm'")
    p.add_argument("--recorte", default=None, help="x0,y0,x1,y1 en fracciones (infografías)")
    p.add_argument("--salida", default=None)
    p.add_argument("--max-brechas", type=int, default=3)
    p.add_argument("--max-segundos", type=float, default=900.0)
    p.add_argument("--sin-ajuste", action="store_true")
    a = p.parse_args(argv)
    import reconocer as rec
    r = crear(a.imagen, a.nombre, a.tamano, rec._recorte(a.recorte), Path(a.salida) if a.salida else None,
              a.max_brechas, a.max_segundos, ajustar=not a.sin_ajuste)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return {"LISTO_PARA_REVISION": 0, "FALTANTES": 4}.get(r["estado"], 1)


if __name__ == "__main__":
    sys.exit(main())
