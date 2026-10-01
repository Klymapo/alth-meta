"""Construye un asset desde su receta (bloque T2 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/construir_receta.py receta.json --salida renders/linea/manzana
    alth-python tools/construir_receta.py receta.json --salida … --modo final --exportar assets/manzana

Arma las piezas con la librería alth (torno, prisma, hoja), renderiza la hoja de 4 vistas, corre la
verificación existente (cotas ±2 %, tris, paleta, flotantes, apoyo Z=0) y mide la silueta contra la
referencia de la receta (IoU de frente y 3/4; se usa la mejor porque la referencia puede no ser una
vista ortogonal). Escribe <salida>/resultado.json. `--exportar` (solo tras aprobación, T4) guarda
.blend + .glb (raíz ×0.01, Y-up) + spec.json en la carpeta del asset.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

TOL_DIM = 0.02
VISTAS_IOU = ("frente", "tres_cuartos")


def mascara_referencia(receta: dict) -> np.ndarray:
    """Silueta de la referencia sin la sombra, igual que la midió la receta."""
    import receta as R
    ficha_min = {"_meta": {"imagen": receta["origen"]["imagen"], "recorte": receta["origen"]["recorte"]}}
    rgb, figura, lleno, abierto = R.mascaras(ficha_min)
    _, sombra = R.protuberancias(rgb, figura, lleno, abierto)
    return lleno & ~sombra


def mascara_render(png: Path) -> np.ndarray:
    from alth import silueta
    return silueta.mayor_mancha(silueta.mascara(silueta.cargar(png)))


def iou_contra(png: Path, ref: np.ndarray) -> float:
    from alth import silueta
    return round(float(silueta.comparar(mascara_render(png), ref)["iou"]), 4)


def armar_objetos(receta: dict) -> list:
    import alth
    objs = []
    for p in receta["piezas"]:
        q = p["params"]
        nombre = f"{receta['nombre'].capitalize()}_{p['id']}"
        if p["modulo"] == "torno":
            er = q.get("escala_r", 1.0)
            perfil = [(r * er, z) for r, z in q["perfil"]]
            objs.append(alth.torno(nombre, perfil, segmentos=int(round(q.get("segmentos", 10))), color=p["color"],
                                   ruido_r=q.get("ruido_r", 0.06), ruido_z=q.get("ruido_z", 0.1),
                                   centro_abajo=q.get("centro_abajo"), centro_arriba=q.get("centro_arriba"),
                                   semilla=int(q.get("semilla", 7))))
        elif p["modulo"] == "prisma":
            objs.append(alth.prisma(nombre, q["radio_base"], q["radio_punta"], q["largo"], lados=int(q.get("lados", 5)),
                                    color=p["color"], pos=tuple(q["pos"]), rot=tuple(q["rot"])))
        elif p["modulo"] == "hoja":
            objs.append(alth.hoja(nombre, largo=q["largo"], ancho=q["ancho"], grosor=q["grosor"], nervio=q["nervio"],
                                  curva=q["curva"], color=p["color"], pos=tuple(q["pos"]), rot=tuple(q["rot"])))
        else:
            raise ValueError(f"módulo desconocido: {p['modulo']}")
    return objs


def spec_asset(receta: dict, objs) -> dict:
    """spec.json mínimo para la verificación: cotas del cuerpo (lo que midió la receta), tope y colores."""
    cuerpo = objs[0].name
    m = receta["medidas_mm"]
    # la cota es la medida de la referencia; escala_r es un ajuste para alcanzarla, no la mueve
    return {"nombre": receta["nombre"], "categoria": receta["categoria"], "k": receta["k"],
            "tris_max": receta["tris_max"],
            "cotas": [{"pieza": cuerpo, "eje": "W", "mm": m["cuerpo_ancho"]},
                      {"pieza": cuerpo, "eje": "H", "mm": m["cuerpo_alto"]}],
            "tolerancia_cotas": TOL_DIM, "colores": {p["id"]: {"hex": p["color"]} for p in receta["piezas"]},
            "receta": receta}


def construir(receta: dict, salida: Path, modo: str = "iteracion", exportar: Path | None = None,
              ref: np.ndarray | None = None) -> dict:
    import alth
    t0 = time.time()
    salida = Path(salida)
    alth.nueva_escena()
    objs = armar_objetos(receta)
    alth.estudio()
    asset = spec_asset(receta, objs)
    rep = alth.revisar(objs, salida, modo=modo, titulo=f"{receta['nombre']} · receta · {modo}", asset=asset)
    mn, mx = alth._limites(objs)
    dims = {"ancho": round(mx.x - mn.x, 3), "fondo": round(mx.y - mn.y, 3), "alto": round(mx.z - mn.z, 3)}
    pedidas = receta["medidas_mm"]
    dif = {k: round(dims[k] / pedidas[k] - 1, 4) for k in ("ancho", "alto") if pedidas.get(k)}
    dadas = [k for k in pedidas.get("dadas") or list(dif) if k in dif]
    cu = rep["medidas_mm"][objs[0].name]
    ref = mascara_referencia(receta) if ref is None else ref
    ious = {v: iou_contra(Path(rep["vistas"][v]), ref) for v in VISTAS_IOU if v in rep["vistas"]}
    tris = sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values())
    verif = rep.get("verificacion", {})
    res = {"nombre": receta["nombre"], "modo": modo, "hoja": rep["hoja"], "vistas": rep["vistas"],
           "dimensiones_mm": dims, "dimensiones_pedidas_mm": {k: pedidas.get(k) for k in ("ancho", "alto")},
           "dif_dimensiones": dif, "dimensiones_auditadas": dadas,
           "dimensiones_ok": all(abs(dif[k]) <= TOL_DIM for k in dadas),
           "cuerpo_mm": {"W": cu["W"], "H": cu["H"]},
           "dif_cuerpo": {"W": round(cu["W"] / receta["medidas_mm"]["cuerpo_ancho"] - 1, 4),
                          "H": round(cu["H"] / receta["medidas_mm"]["cuerpo_alto"] - 1, 4)},
           "tris": tris, "tris_max": receta["tris_max"], "verificacion_ok": bool(verif.get("ok")),
           "verificacion": verif, "iou_por_vista": ious, "iou": max(ious.values()) if ious else 0.0,
           "segundos": round(time.time() - t0, 1)}
    res["ok"] = res["dimensiones_ok"] and res["verificacion_ok"] and tris <= receta["tris_max"]
    if exportar:
        exportar = Path(exportar)
        exportar.mkdir(parents=True, exist_ok=True)
        (exportar / "spec.json").write_text(json.dumps({k: v for k, v in asset.items()}, ensure_ascii=False,
                                                       indent=2) + "\n", encoding="utf-8")
        alth.exportar_glb(objs, exportar / f"{receta['nombre']}.glb")
        res["exportado"] = str(exportar)
    (salida / "resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str) + "\n",
                                           encoding="utf-8")
    return res


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("receta")
    p.add_argument("--salida", required=True)
    p.add_argument("--modo", default="iteracion", choices=("iteracion", "final"))
    p.add_argument("--exportar", default=None, help="carpeta del asset (solo tras aprobación)")
    a = p.parse_args(argv)
    import receta as R
    receta = json.loads(Path(a.receta).read_text(encoding="utf-8"))
    errores = R.validar(receta)
    if errores:
        print("receta inválida:\n" + "\n".join(errores), file=sys.stderr)
        return 2
    res = construir(receta, Path(a.salida), a.modo, Path(a.exportar) if a.exportar else None)
    print(json.dumps({k: v for k, v in res.items() if k not in ("verificacion", "vistas")}, ensure_ascii=False,
                     indent=2, default=str))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
