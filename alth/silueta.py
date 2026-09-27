"""ALTH-META · comparación de silueta entre un render y una imagen de referencia.

No necesita Blender (solo numpy + Pillow; scipy si está, para quedarse con la figura principal).
Sirve para dar "ojos numéricos" al bucle: un modelo que no ve imágenes recibe frases como
"banda 1 (arriba): el modelo es 35 % más angosto que la referencia".

    python3 alth/silueta.py render.png ref.png [--recorte 0,0,0.5,0.5]

Cómo compara:
1. Separa la figura del fondo: el fondo es el color mediano del borde de la imagen; todo lo que
   se aleja más de `umbral` en algún canal es figura. Las sombras suaves quedan fuera.
2. Se queda con la mancha más grande (el maniquí de escala o la sombra no cuentan).
3. Recorta cada figura a su caja, la lleva a la misma ALTURA (la proporción ancho/alto se conserva)
   y las alinea por el centro horizontal.
4. Mide: IoU (0-1, cuánto se empalman), proporción ancho/alto, y el ancho en N bandas horizontales
   de arriba a abajo.

Límites honestos: solo tiene sentido con la MISMA vista y la MISMA pose (frente contra frente,
T-pose contra T-pose). Con `recorte` se toma un cuadrante de una hoja de vistas.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ALTO_NORMAL = 240
NOMBRES_BANDA = None  # se generan según el número de bandas


def cargar(ruta, recorte=None) -> np.ndarray:
    """Imagen RGB como arreglo float. `recorte` = (x0, y0, x1, y1) en fracciones 0-1."""
    im = Image.open(ruta).convert("RGB")
    if recorte:
        w, h = im.size
        x0, y0, x1, y1 = recorte
        im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    return np.asarray(im, dtype=np.float32)


def mascara(rgb: np.ndarray, umbral: float = 28.0, borde: int = 4) -> np.ndarray:
    """True donde hay figura. El fondo se estima con el color mediano del borde."""
    marco = np.concatenate([rgb[:borde].reshape(-1, 3), rgb[-borde:].reshape(-1, 3),
                            rgb[:, :borde].reshape(-1, 3), rgb[:, -borde:].reshape(-1, 3)])
    fondo = np.median(marco, axis=0)
    return np.abs(rgb - fondo).max(axis=2) > umbral


def mayor_mancha(m: np.ndarray) -> np.ndarray:
    """Se queda con la región conectada más grande (si no hay scipy, devuelve la máscara igual)."""
    try:
        from scipy import ndimage
    except ImportError:  # pragma: no cover
        return m
    etiquetas, n = ndimage.label(m)
    if n <= 1:
        return m
    tam = ndimage.sum(m, etiquetas, range(1, n + 1))
    return etiquetas == (int(np.argmax(tam)) + 1)


def normalizar(m: np.ndarray, alto: int = ALTO_NORMAL) -> np.ndarray:
    """Recorta a la caja de la figura y la escala a `alto` px conservando la proporción."""
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        raise ValueError("no se encontró figura (¿fondo del mismo color?)")
    caja = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = caja.shape
    nuevo_w = max(1, round(w * alto / h))
    im = Image.fromarray((caja * 255).astype(np.uint8)).resize((nuevo_w, alto), Image.NEAREST)
    return np.asarray(im) > 127


def _centrar(a: np.ndarray, ancho: int) -> np.ndarray:
    lienzo = np.zeros((a.shape[0], ancho), dtype=bool)
    x0 = (ancho - a.shape[1]) // 2
    lienzo[:, x0:x0 + a.shape[1]] = a
    return lienzo


def perfil_anchos(a: np.ndarray, bandas: int) -> list[float]:
    """Ancho medio (px, a la altura normalizada) de la figura en cada banda horizontal."""
    filas = a.sum(axis=1).astype(float)
    trozos = np.array_split(filas, bandas)
    return [float(t.mean()) for t in trozos]


def nombre_banda(i: int, n: int) -> str:
    ini, fin = round(100 * i / n), round(100 * (i + 1) / n)
    zona = "arriba" if i < n / 3 else ("en medio" if i < 2 * n / 3 else "abajo")
    return f"banda {i + 1} ({zona}, {ini}-{fin} % de la altura desde arriba)"


def comparar(m_render: np.ndarray, m_ref: np.ndarray, bandas: int = 10, tolerancia: float = 0.08) -> dict:
    """Compara dos máscaras ya limpias. Devuelve números y frases listas para un prompt."""
    a, b = normalizar(m_render), normalizar(m_ref)
    ancho = max(a.shape[1], b.shape[1])
    a2, b2 = _centrar(a, ancho), _centrar(b, ancho)
    iou = float((a2 & b2).sum() / max(1, (a2 | b2).sum()))
    prop_r, prop_ref = a.shape[1] / a.shape[0], b.shape[1] / b.shape[0]
    pa, pb = perfil_anchos(a2, bandas), perfil_anchos(b2, bandas)
    frases, detalle = [], []
    dif_prop = prop_r / prop_ref - 1
    if abs(dif_prop) > tolerancia:
        frases.append(f"Proporción total: el modelo es {abs(dif_prop) * 100:.0f} % "
                      f"{'más ancho' if dif_prop > 0 else 'más angosto'} (a igual altura) que la referencia.")
    for i, (x, y) in enumerate(zip(pa, pb)):
        if y < 1 and x < 1:
            rel = 0.0
        elif y < 1:
            rel = 1.0
        else:
            rel = x / y - 1
        detalle.append({"banda": i + 1, "ancho_modelo": round(x, 1), "ancho_ref": round(y, 1), "dif": round(rel, 3)})
        if abs(rel) > tolerancia:
            if y < 1:
                frases.append(f"{nombre_banda(i, bandas)}: el modelo tiene figura donde la referencia está vacía.")
            else:
                frases.append(f"{nombre_banda(i, bandas)}: el modelo es {abs(rel) * 100:.0f} % "
                              f"{'más ancho' if rel > 0 else 'más angosto'}.")
    if not frases:
        frases.append("La silueta coincide con la referencia dentro de la tolerancia.")
    return {"iou": round(iou, 3), "proporcion_modelo": round(prop_r, 3), "proporcion_ref": round(prop_ref, 3),
            "bandas": detalle, "frases": frases}


def superponer(m_render: np.ndarray, m_ref: np.ndarray, destino) -> Path:
    """PNG con las dos siluetas normalizadas: gris = ambas, rojo = sobra en el modelo,
    azul = le falta al modelo (está en la referencia)."""
    a, b = normalizar(m_render), normalizar(m_ref)
    ancho = max(a.shape[1], b.shape[1])
    a, b = _centrar(a, ancho), _centrar(b, ancho)
    im = np.full(a.shape + (3,), 235, dtype=np.uint8)
    im[a & b] = (120, 120, 120)
    im[a & ~b] = (210, 60, 50)
    im[~a & b] = (60, 100, 210)
    destino = Path(destino)
    Image.fromarray(im).resize((ancho * 2, a.shape[0] * 2), Image.NEAREST).save(destino)
    return destino


def comparar_archivos(render, ref, recorte_ref=None, recorte_render=None, bandas=10, umbral=28.0,
                      superposicion=None) -> dict:
    m1 = mayor_mancha(mascara(cargar(render, recorte_render), umbral))
    m2 = mayor_mancha(mascara(cargar(ref, recorte_ref), umbral))
    res = comparar(m1, m2, bandas)
    if superposicion:
        res["superposicion"] = str(superponer(m1, m2, superposicion))
    return res


def texto(res: dict) -> str:
    """Resumen corto para meter en un prompt."""
    lineas = [f"IoU de silueta (0 = nada, 1 = idéntica): {res['iou']}",
              f"Ancho/alto: modelo {res['proporcion_modelo']} · referencia {res['proporcion_ref']}"]
    lineas += [f"- {f}" for f in res["frases"]]
    return "\n".join(lineas)


def _recorte(txt):
    return tuple(float(x) for x in txt.split(",")) if txt else None


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("render")
    p.add_argument("ref")
    p.add_argument("--recorte", help="recorte de la referencia x0,y0,x1,y1 (fracciones)")
    p.add_argument("--bandas", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.add_argument("--superposicion", help="guarda un PNG con las dos siluetas encimadas")
    a = p.parse_args()
    r = comparar_archivos(a.render, a.ref, _recorte(a.recorte), bandas=a.bandas, superposicion=a.superposicion)
    print(json.dumps(r, indent=2, ensure_ascii=False) if a.json else texto(r))
    sys.exit(0)
