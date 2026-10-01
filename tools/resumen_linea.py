"""Resumen en Markdown de una corrida de tools/crear_asset.py (resumen del job y comentario del issue).

    python3 tools/resumen_linea.py .linea/crear/manzana/resumen.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def markdown(r: dict, url_hoja: str | None = None) -> str:
    f = r.get("final") or r.get("base") or {}
    lineas = [f"## {r['nombre']} · {r.get('estado', '?')}", ""]
    if url_hoja:
        lineas += [f"![revisión: referencia, nuevo, anterior y 4 vistas]({url_hoja})", ""]
    if f:
        dims = f.get("dimensiones_mm") or {}
        dif = f.get("dif_dimensiones") or {}
        lineas += ["| medida | valor |", "|---|---|",
                   f"| IoU con la referencia | {f.get('iou')} ({', '.join(f'{k} {v}' for k, v in (f.get('iou_por_vista') or {}).items())}) |",
                   f"| dimensiones (mm) | " + ", ".join(f"{k} {v}" for k, v in dims.items()) + " |",
                   f"| diferencia vs pedido | " + ", ".join(f"{k} {v * 100:+.1f} %" for k, v in dif.items()) + " |",
                   f"| triángulos | {f.get('tris')} |",
                   f"| verificación (cotas, paleta, flotantes, apoyo) | {'OK' if f.get('verificacion_ok') else 'con fallas'} |"]
    au = r.get("auditoria")
    if au:
        lineas += ["", f"**Auditoría visual: {au.get('decision')}**"
                   + (f" · vista {au['vista']}" if au.get("vista") else "")
                   + (f" · fallas: {', '.join(au['fallas'])}" if au.get("fallas") else "")
                   + ("" if au.get("calibrado") else " · umbrales provisionales")]
        if au.get("error"):
            lineas.append(f"Error de entrada: {au['error']}")
        pm, md = au.get("por_medida") or {}, au.get("medidas") or {}
        if pm:
            lineas += ["", "| medida | valor | |", "|---|---|---|"] + [
                f"| {k} | {md.get(k, '')} | {v} |" for k, v in pm.items()]
        if au.get("aprobado"):
            lineas.append(f"\nContra el aprobado anterior: no peor {au.get('no_peor_que_aprobado')}, "
                          f"lo supera {au.get('supera_aprobado')}.")
    aj = r.get("ajuste")
    if aj:
        lineas += ["", f"Ajuste numérico: **{aj['estado']}** en {aj['rondas']} ronda(s), IoU {aj['iou_base']} → {aj['iou_final']}."]
    if r.get("faltantes"):
        lineas += ["", "**Faltantes (no se inventan):**"] + [f"- `{x['capacidad']}`: {x['motivo']}" for x in r["faltantes"]]
    pasos = r.get("pasos") or {}
    lineas += ["", f"Tiempo total {r.get('segundos')} s (" + ", ".join(f"{k} {v} s" for k, v in pasos.items()) + ")."]
    return "\n".join(lineas) + "\n"


def _siguiente(r: dict) -> str:
    estado = r.get("estado")
    if estado == "APROBADO_POR_AUDITORIA":
        return ("**La auditoría visual lo aprueba.** Se abre un PR de publicación (GLB, final.png, medidas, "
                "evidencia); entra a `main` cuando lo fusionas.")
    if estado == "AUDITORIA_FALLIDA":
        return ("**La auditoría visual lo rechaza**: no se publica. La comparación (azul = sólo referencia, "
                "naranja = sólo el modelo) está en la rama de revisión, carpeta `auditoria/`.")
    if estado == "FALTANTES":
        return "**No se puede aprobar todavía**: faltan capacidades (arriba). No se publica nada."
    return "**Falló la verificación técnica**: no se publica nada."


def comentario(r: dict, imagen: str, rama: str, corrida: str, comparacion: str | None = None) -> str:
    """Comentario del issue: resumen + hoja de revisión + cómo aprobar."""
    extra = (f"\n![auditoría: referencia | modelo | superposición]({comparacion})\n" if comparacion else "")
    return ("<!-- alth-linea:revision -->\n" + markdown(r, imagen) + extra +
            "\n" + _siguiente(r) + "\n\n"
            f"Revisión en la rama `{rama}` · corrida {corrida}\n")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("resumen")
    ap.add_argument("--comentario", action="store_true")
    ap.add_argument("--imagen", default=None)
    ap.add_argument("--rama", default="")
    ap.add_argument("--corrida", default="")
    ap.add_argument("--comparacion", default=None, help="URL de auditoria/comparacion.png")
    a = ap.parse_args()
    datos = json.loads(Path(a.resumen).read_text(encoding="utf-8"))
    print(comentario(datos, a.imagen, a.rama, a.corrida, a.comparacion) if a.comentario else markdown(datos, a.imagen))
