"""Receta ALTH armada por CÓDIGO a partir de la ficha (bloque T2 de docs/BRIEF_LINEA_UNICA.md).

    python3 tools/receta.py armar ficha.json --salida receta.json
    python3 tools/receta.py validar receta.json

Nada se escribe a mano ni lo decide una IA: cada número sale de la imagen de referencia que la ficha
señala (ruta + recorte) y de lo que la ficha midió:
  - cuerpo `torno`: perfil = medio ancho del cuerpo (la figura sin piezas delgadas) en bandas de
    altura; cuencas arriba/abajo si el centro de la silueta queda hundido respecto a los hombros;
  - piezas que sobresalen: `prisma` si son alargadas (tallo, palo), `hoja` si son planas y la ficha
    pide la capacidad hoja; posición, largo, ancho y ángulo salen de su mancha en la imagen;
  - colores: el color dominante de cada mancha ajustado a la paleta;
  - mm: escala px→mm con tamano_alth_mm de la ficha (s0 de Alpha × k).
Lo que no sabe armar (personajes, cuerpos que no son torno) lo dice en vez de inventarlo.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import reconocer as rec  # noqa: E402

ESQUEMA = RAIZ / "spec" / "receta.schema.json"
SPEC = RAIZ / "spec" / "alth_spec.json"
BANDAS_T = [0.0, 0.05, 0.18, 0.35, 0.55, 0.75, 0.9, 1.0]   # alturas relativas del perfil (más denso en las tapas)
CUENCA_MIN = 0.03          # hundido mínimo (fracción del alto del cuerpo) para hacer cuenca
ELONGACION_PRISMA = 3.0    # mancha más alargada que esto → prisma
PUNTA_ROMA_PRISMA = 0.75   # ancho cerca de la punta / ancho máximo: palo o tallo (romo) ≈ 0.8-1, hoja (gota) ≈ 0.2-0.6
INCLINACION_HOJA = 20.0    # grados que la hoja se inclina hacia el frente para leerse también en 3/4
TOPE_POR_CATEGORIA = {"de_mano": "objeto_mano", "portatil": "objeto_mano", "largo_en_mano": "objeto_mano",
                      "mueble": "mueble", "anclado_al_cuerpo": "mueble"}


class RecetaNoSoportada(ValueError):
    """La ficha pide algo que la receta todavía no sabe armar: se reporta como faltante."""


# ================================================================ validación (subconjunto de JSON Schema)
def validar(dato, esquema: dict | None = None, ruta: str = "$") -> list[str]:
    """Errores de `dato` contra el esquema (type, required, properties, additionalProperties, enum,
    pattern, minimum, minLength, minItems, items). Lista vacía = válido."""
    import re
    esquema = esquema if esquema is not None else json.loads(ESQUEMA.read_text(encoding="utf-8"))
    errores: list[str] = []
    tipos = esquema.get("type")
    if tipos:
        tipos = tipos if isinstance(tipos, list) else [tipos]
        ok = any(_es_tipo(dato, t) for t in tipos)
        if not ok:
            return [f"{ruta}: se esperaba {'/'.join(tipos)}, llegó {type(dato).__name__}"]
    if "enum" in esquema and dato not in esquema["enum"]:
        errores.append(f"{ruta}: {dato!r} no está en {esquema['enum']}")
    if isinstance(dato, str):
        if len(dato) < esquema.get("minLength", 0):
            errores.append(f"{ruta}: texto vacío")
        if "pattern" in esquema and not re.search(esquema["pattern"], dato):
            errores.append(f"{ruta}: {dato!r} no cumple {esquema['pattern']}")
    if isinstance(dato, (int, float)) and not isinstance(dato, bool) and "minimum" in esquema \
            and dato < esquema["minimum"]:
        errores.append(f"{ruta}: {dato} < mínimo {esquema['minimum']}")
    if isinstance(dato, dict):
        for r in esquema.get("required", []):
            if r not in dato:
                errores.append(f"{ruta}: falta '{r}'")
        props = esquema.get("properties", {})
        for k, v in dato.items():
            if k in props:
                errores += validar(v, props[k], f"{ruta}.{k}")
            elif esquema.get("additionalProperties") is False:
                errores.append(f"{ruta}: campo no permitido '{k}'")
    if isinstance(dato, list):
        if len(dato) < esquema.get("minItems", 0):
            errores.append(f"{ruta}: necesita al menos {esquema['minItems']} elemento(s)")
        if "items" in esquema:
            for i, v in enumerate(dato):
                errores += validar(v, esquema["items"], f"{ruta}[{i}]")
    return errores


def _es_tipo(v, t: str) -> bool:
    return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str),
            "integer": isinstance(v, int) and not isinstance(v, bool),
            "number": isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": isinstance(v, bool), "null": v is None}[t]


# ================================================================ medición de la imagen
def mascaras(ficha: dict, raiz: Path = RAIZ):
    """(rgb, figura, lleno, cuerpo) de la imagen de la ficha, con el mismo recorte con que se midió."""
    meta = ficha.get("_meta") or {}
    ruta = Path(meta.get("imagen", ""))
    ruta = ruta if ruta.is_absolute() else Path(raiz) / ruta
    rgb = rec.cargar(ruta, tuple(meta["recorte"]) if meta.get("recorte") else None)
    figura, _ = rec.separar_figura(rgb)
    _, lleno, cuerpo = rec.medir_silueta(figura)
    return rgb, figura, lleno, cuerpo


def _caja(m: np.ndarray):
    ys, xs = np.nonzero(m)
    return ys.min(), ys.max(), xs.min(), xs.max()


def perfil_torno(cuerpo: np.ndarray, esc: float, bandas=BANDAS_T) -> dict:
    """Perfil (radio, z) en mm del cuerpo, de abajo hacia arriba, y sus cuencas."""
    y0, y1, x0, x1 = _caja(cuerpo)
    alto_px = y1 - y0 + 1
    perfil = []
    for t in bandas:
        fila = int(round(y1 - t * (alto_px - 1)))
        filas = cuerpo[max(y0, fila - 1):min(y1, fila + 1) + 1]
        anchos = [np.ptp(np.nonzero(f)[0]) + 1 for f in filas if f.any()]
        r = (np.mean(anchos) / 2.0) * esc if anchos else 0.0
        perfil.append([round(float(r), 3), round(float(t * alto_px * esc), 3)])
    # cuencas: ¿el centro queda más bajo (arriba) o más alto (abajo) que el contorno?
    cx = int(round((x0 + x1) / 2))
    ventana = cuerpo[:, max(x0, cx - max(1, (x1 - x0) // 25)):cx + max(1, (x1 - x0) // 25) + 1]
    filas_c = np.nonzero(ventana.any(1))[0]
    hundido_arriba = (filas_c.min() - y0) / alto_px if len(filas_c) else 0.0
    hundido_abajo = (y1 - filas_c.max()) / alto_px if len(filas_c) else 0.0
    alto_mm = alto_px * esc
    return {"perfil": perfil, "alto_mm": round(float(alto_mm), 3), "ancho_mm": round(float((x1 - x0 + 1) * esc), 3),
            "centro_arriba": round(float(alto_mm * (1 - hundido_arriba)), 3) if hundido_arriba > CUENCA_MIN else None,
            "centro_abajo": round(float(alto_mm * hundido_abajo), 3) if hundido_abajo > CUENCA_MIN else None,
            "hundido_arriba": round(float(hundido_arriba), 3), "hundido_abajo": round(float(hundido_abajo), 3)}


def protuberancias(rgb: np.ndarray, figura: np.ndarray, lleno: np.ndarray, cuerpo: np.ndarray,
                   area_min: float = 0.006, de_pieza: float = 15.0) -> tuple[list[dict], np.ndarray]:
    """Piezas que sobresalen y la sombra que haya quedado pegada a la figura.

    Parte de las manchas que la apertura deja fuera del cuerpo (mismo criterio que
    reconocer.medir_silueta) y:
      - descarta como SOMBRA la mancha baja, gris (croma < 8) y más oscura que el fondo;
      - hace crecer cada pieza por su color (ΔE < de_pieza) dentro de la figura, para que el
        tallo o la hoja incluyan la parte que la apertura dejó pegada al cuerpo.
    Devuelve (piezas, máscara de sombra).
    """
    from scipy import ndimage
    lab = rec._srgb_a_lab(rgb)
    lab_f = rec._srgb_a_lab(rec._fondo(rgb))
    y0, y1, _, _ = _caja(lleno)
    resto = lleno & ~cuerpo
    et, n = ndimage.label(resto)
    area = float(lleno.sum())
    sombra = np.zeros_like(lleno)
    piezas = []
    for i in range(1, n + 1):
        sel = et == i
        if sel.sum() < area_min * area:
            continue
        med = np.median(lab[sel], axis=0)
        croma = float(np.hypot(med[1] - lab_f[1], med[2] - lab_f[2]))
        baja = np.argwhere(sel)[:, 0].mean() > y0 + 0.65 * (y1 - y0)
        if baja and croma < 8 and med[0] < lab_f[0]:
            sombra |= sel
            continue
        parecido = figura & (np.linalg.norm(lab - med, axis=-1) < de_pieza)
        et_p, _ = ndimage.label(parecido | sel)
        crecida = np.isin(et_p, np.unique(et_p[sel]))
        piezas.append(crecida)
    # dos manchas que crecieron hasta tocarse son la misma pieza
    unidas: list[np.ndarray] = []
    for m in piezas:
        for j, u in enumerate(unidas):
            if (u & m).any():
                unidas[j] = u | m
                break
        else:
            unidas.append(m)
    cuerpo_px = lleno & ~sombra
    for u in unidas:
        cuerpo_px &= ~u
    centro = np.argwhere(cuerpo_px).mean(0)
    out = []
    for m in unidas:
        coords = np.argwhere(m).astype(float)
        base = coords[int(np.argmin(((coords - centro) ** 2).sum(1)))]   # donde nace: lo más cerca del cuerpo
        # ejes principales (PCA): largo y ancho de la pieza; el eje apunta de la base hacia su centro
        c = coords - coords.mean(0)
        _, vecs = np.linalg.eigh(np.cov(c.T))
        eje, perp = vecs[:, 1], vecs[:, 0]
        if (coords.mean(0) - base) @ eje < 0:
            eje = -eje
        a_lo, a_an = coords @ eje, coords @ perp
        largo, ancho_max = float(np.ptp(a_lo)) + 1.0, float(np.ptp(a_an)) + 1.0
        punta = base + eje * float(a_lo.max() - base @ eje)
        a = float(m.sum())
        # ¿punta roma (palo, tallo) o afilada (hoja)? ancho cerca de la punta / ancho máximo
        t = (a_lo - a_lo.min()) / max(np.ptp(a_lo), 1e-9)
        anchos = [np.ptp(a_an[(t >= i / 10) & (t <= (i + 1) / 10)]) + 1 if ((t >= i / 10) & (t <= (i + 1) / 10)).any()
                  else 0.0 for i in range(10)]
        punta_roma = float(np.mean(anchos[8:]) / max(max(anchos), 1e-9))
        out.append({"mascara": m, "area_rel": round(a / area, 4), "elongacion": round(rec._elongacion(coords), 2),
                    "relleno": round(a / (largo * ancho_max), 3), "punta_roma": round(punta_roma, 3),
                    "base_px": [int(base[1]), int(base[0])], "punta_px": [int(round(punta[1])), int(round(punta[0]))],
                    "largo_px": largo, "ancho_px": a / largo, "ancho_max_px": ancho_max})
    return out, sombra


def color_paleta(rgb: np.ndarray, m: np.ndarray, paleta) -> str:
    cols = rec.colores_dominantes(rgb, m, paleta, k=3)
    return cols[0]["paleta"].upper() if cols else "#B7BABE"


# ================================================================ armar
def armar(ficha: dict, raiz: Path = RAIZ, spec: dict | None = None) -> dict:
    spec = spec or json.loads(SPEC.read_text(encoding="utf-8"))
    if ficha.get("tipo") != "objeto":
        raise RecetaNoSoportada(f"tipo '{ficha.get('tipo')}': la receta por código solo arma objetos todavía")
    caps = {c["id"] for c in ficha.get("capacidades", [])}
    if "torno" not in caps:
        raise RecetaNoSoportada("el cuerpo no es de revolución (torno): no hay módulo dominado para armarlo")
    tam = ficha.get("tamano_alth_mm") or {}
    if not tam.get("ancho") and not tam.get("alto"):
        raise RecetaNoSoportada("la ficha no trae tamaño ALTH: falta el tamaño real (--tamano)")
    rgb, figura, lleno, abierto = mascaras(ficha, raiz)
    paleta = rec.cargar_paleta(spec)
    protus, sombra = protuberancias(rgb, figura, lleno, abierto)
    silueta = lleno & ~sombra
    cuerpo = silueta.copy()
    for p in protus:
        cuerpo &= ~p["mascara"]
    from scipy import ndimage
    et, n = ndimage.label(cuerpo)          # el cuerpo es la mancha mayor que queda
    if n > 1:
        cuerpo = et == (1 + int(np.argmax(ndimage.sum(cuerpo, et, range(1, n + 1)))))
    y0, y1, x0, x1 = _caja(silueta)
    esc = tam["ancho"] / (x1 - x0 + 1) if tam.get("ancho") else tam["alto"] / (y1 - y0 + 1)
    avisos = [f"escala {esc:.5f} mm/px por el {'ancho' if tam.get('ancho') else 'alto'} total de la silueta"]
    if sombra.any():
        avisos.append(f"sombra pegada a la figura descartada ({sombra.sum() / lleno.sum() * 100:.1f} % del área); "
                      "la ficha la midió como parte de la silueta")

    pt = perfil_torno(cuerpo, esc)
    cy0, cy1, cx0, cx1 = _caja(cuerpo)
    cx = (cx0 + cx1) / 2.0
    params_cuerpo = {"perfil": pt["perfil"], "segmentos": 10, "ruido_r": 0.06, "ruido_z": 0.1, "semilla": 7,
                     "centro_arriba": pt["centro_arriba"], "centro_abajo": pt["centro_abajo"]}
    piezas = [{"id": "cuerpo", "modulo": "torno", "color": color_paleta(rgb, cuerpo, paleta), "params": params_cuerpo,
               "origen": f"silueta del cuerpo en {len(BANDAS_T)} bandas; hundido arriba {pt['hundido_arriba']}, "
                         f"abajo {pt['hundido_abajo']}"}]
    ajustables = [{"ruta": "piezas.0.params.ruido_r", "min": 0.0, "max": 0.12, "paso": 0.02},
                  {"ruta": "piezas.0.params.ruido_z", "min": 0.0, "max": 0.2, "paso": 0.04},
                  {"ruta": "piezas.0.params.segmentos", "min": 8, "max": 12, "paso": 1},
                  {"ruta": "piezas.0.params.escala_r", "min": 0.9, "max": 1.1, "paso": 0.02}]
    params_cuerpo["escala_r"] = 1.0

    def a_mm(px):  # (x, y) de imagen → (x, z) en mm con el piso en la base del cuerpo
        return [round(float((px[0] - cx) * esc), 3), round(float((cy1 - px[1]) * esc), 3)]

    n_hoja = n_prisma = 0
    for p in sorted(protus, key=lambda p: -p["area_rel"]):
        base, punta = a_mm(p["base_px"]), a_mm(p["punta_px"])
        dx, dz = punta[0] - base[0], punta[1] - base[1]
        largo = p["largo_px"] * esc
        ancho = p["ancho_px"] * esc
        color = color_paleta(rgb, p["mascara"], paleta)
        if p["elongacion"] >= ELONGACION_PRISMA or p["punta_roma"] >= PUNTA_ROMA_PRISMA or "hoja" not in caps:
            n_prisma += 1
            theta = math.degrees(math.atan2(dx, dz))           # +Z del prisma hacia la punta
            rb = max(ancho / 2, 0.08)
            # la base entra un poco en el cuerpo para que la pieza no flote
            hund = min(0.3 * largo, 2 * rb)
            pos = [base[0] - math.sin(math.radians(theta)) * hund, 0.0, base[1] - math.cos(math.radians(theta)) * hund]
            piezas.append({"id": f"prisma_{n_prisma}", "modulo": "prisma", "color": color,
                           "params": {"radio_base": round(rb, 3), "radio_punta": round(rb * 0.7, 3),
                                      "largo": round(largo + hund, 3), "lados": 5,
                                      "pos": [round(v, 3) for v in pos], "rot": [0.0, round(theta, 2), 0.0]},
                           "origen": f"mancha de punta roma (elongación {p['elongacion']}, punta {p['punta_roma']}, "
                                     f"{p['area_rel'] * 100:.1f} % del área)"})
        else:
            n_hoja += 1
            phi = -math.degrees(math.atan2(dz, dx))              # +X de la hoja hacia la punta
            piezas.append({"id": f"hoja_{n_hoja}", "modulo": "hoja", "color": color,
                           "params": {"largo": round(largo, 3), "ancho": round(max(p["ancho_max_px"] * esc, 0.2), 3),
                                      "grosor": round(max(0.05 * largo, 0.1), 3), "nervio": round(0.08 * largo, 3),
                                      "curva": round(0.12 * largo, 3), "pos": [base[0], 0.0, base[1]],
                                      "rot": [90.0 - INCLINACION_HOJA, round(phi, 2), 0.0]},
                           "origen": f"mancha plana en gota (elongación {p['elongacion']}, punta {p['punta_roma']}, "
                                     f"{p['area_rel'] * 100:.1f} % del área)"})
            k = len(piezas) - 1
            ajustables.append({"ruta": f"piezas.{k}.params.rot.0", "min": 50.0, "max": 90.0, "paso": 10.0})
    cat = (ficha.get("escala") or {}).get("categoria") or "de_mano"
    tope = spec["geometria"]["tris_max"].get(TOPE_POR_CATEGORIA.get(cat, "objeto_mano"), 500)
    receta = {
        "version": "1.0", "nombre": rec.nombre_id(ficha["nombre"]), "tipo": "objeto", "categoria": cat,
        "k": float((ficha.get("escala") or {}).get("k", 1.0)),
        "medidas_mm": {"alto": round(float((y1 - y0 + 1) * esc), 2), "ancho": round(float((x1 - x0 + 1) * esc), 2),
                       "fondo": tam.get("fondo"), "cuerpo_alto": pt["alto_mm"], "cuerpo_ancho": pt["ancho_mm"]},
        "tris_max": int(tope), "piezas": piezas, "ajustables": ajustables,
        "origen": {"imagen": (ficha.get("_meta") or {}).get("imagen", ""),
                   "recorte": list((ficha.get("_meta") or {}).get("recorte") or []) or None,
                   "imagen_sha256": (ficha.get("_meta") or {}).get("imagen_sha256"),
                   "metodo": "tools/receta.py (código, sin IA)", "capacidades": sorted(caps)},
        "avisos": avisos,
    }
    errores = validar(receta)
    if errores:
        raise ValueError("la receta armada no cumple el esquema: " + "; ".join(errores))
    return receta


def obtener(receta: dict, ruta: str):
    v = receta
    for p in ruta.split("."):
        v = v[int(p)] if isinstance(v, list) else v[p]
    return v


def fijar(receta: dict, ruta: str, valor) -> dict:
    """Copia de la receta con `ruta` (p. ej. 'piezas.0.params.ruido_r') = valor."""
    nueva = json.loads(json.dumps(receta))
    partes = ruta.split(".")
    v = nueva
    for p in partes[:-1]:
        v = v[int(p)] if isinstance(v, list) else v[p]
    ult = partes[-1]
    if isinstance(v, list):
        v[int(ult)] = valor
    else:
        v[ult] = valor
    return nueva


# ================================================================ CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("armar")
    a.add_argument("ficha")
    a.add_argument("--salida", default=None)
    v = sub.add_parser("validar")
    v.add_argument("receta")
    args = p.parse_args(argv)
    if args.cmd == "armar":
        ficha = json.loads(Path(args.ficha).read_text(encoding="utf-8"))
        try:
            receta = armar(ficha)
        except RecetaNoSoportada as e:
            print(f"[receta] FALTANTE: {e}", file=sys.stderr)
            return 4
        texto = json.dumps(receta, ensure_ascii=False, indent=2) + "\n"
        if args.salida:
            Path(args.salida).write_text(texto, encoding="utf-8")
        print(texto)
        return 0
    errores = validar(json.loads(Path(args.receta).read_text(encoding="utf-8")))
    print("\n".join(errores) or "OK: la receta cumple spec/receta.schema.json")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
