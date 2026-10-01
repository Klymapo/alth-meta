"""ALTH-META · máscaras limpias de figura, iguales para referencias y para renders.

Una sola forma de sacar "dónde está la figura" para las dos imágenes que se comparan, porque una
auditoría que mide la referencia de un modo y el render de otro compara los métodos, no las formas.

  1. `reconocer.separar_figura`: fondo conectado al borde (ΔE Lab) + sombra que se desvanece.
  2. `quitar_sombra_pegada`: la sombra del piso que queda PEGADA a la figura (la vista 3/4 de los
     renders del repo es ~30 % sombra si no se quita; medido el 1 oct 2026).

Sólo numpy/scipy/Pillow: corre en un runner de GitHub sin Blender y sin modelos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reconocer  # noqa: E402

SOMBRA_DESDE = 0.40      # la sombra del piso sólo se busca en el 60 % inferior de la figura
BORDE_SOMBRA_DE = 11.0   # contraste de borde (ΔE) bajo el cual una mancha gris es sombra, no pieza
CROMA_SOMBRA = 12.0      # croma máx. (vs. fondo) de una sombra: la de la manzana de referencia llega a 10 (rebote rojo)


def quitar_sombra_pegada(rgb: np.ndarray, figura: np.ndarray, fondo_rgb) -> tuple[np.ndarray, float]:
    """Quita la sombra del piso que queda PEGADA a la figura (separar_figura sólo quita la que se
    desvanece hacia el fondo). Una sombra de render es gris neutro (mismo tinte que el fondo), un poco
    más oscura que él, en la parte baja, y no tiene figura debajo en su misma columna.

    Se conserva lo oscuro de verdad (zapatos negros: L muy bajo), cualquier gris que tenga figura
    debajo, y toda mancha gris de BORDE NÍTIDO: una sombra se desvanece hacia el fondo (contraste de
    borde ΔE ≈ 6-8 en las referencias del repo), una pieza real no (aro metálico de la lata: 16.8).
    Calibrado el 1 oct 2026 con joven-rubio, alastor, manzana y lata (infografías) y taza/lata (renders).
    Devuelve (figura_limpia, fracción quitada).
    """
    lab = reconocer._srgb_a_lab(rgb)
    lab_f = reconocer._srgb_a_lab(np.asarray(fondo_rgb, dtype=np.float64))
    croma = np.hypot(lab[..., 1] - lab_f[1], lab[..., 2] - lab_f[2])
    de = np.linalg.norm(lab - lab_f, axis=-1)
    L = lab[..., 0]
    filas = np.where(figura.any(1))[0]
    if len(filas) == 0:
        return figura, 0.0
    corte = filas[0] + SOMBRA_DESDE * (filas[-1] - filas[0])
    abajo = np.zeros_like(figura)
    abajo[int(corte):] = True
    candidata = figura & abajo & (croma < CROMA_SOMBRA) & (L < lab_f[0] - 2) & (L > lab_f[0] - 50)
    solida = figura & ~candidata
    # ¿hay figura sólida más abajo en la misma columna? (acumulado desde abajo)
    hay_debajo = np.flipud(np.cumsum(np.flipud(solida), axis=0)) - solida > 0
    posible = candidata & ~hay_debajo
    fuera = ndimage.binary_dilation(~figura, iterations=2)
    et, n = ndimage.label(posible)
    sombra = np.zeros_like(figura)
    for i in range(1, n + 1):
        comp = et == i
        borde = comp & fuera
        if borde.any() and float(de[borde].mean()) < BORDE_SOMBRA_DE:
            sombra |= comp
    limpia = ndimage.binary_opening(figura & ~sombra, iterations=1)
    et, n = ndimage.label(limpia)
    if n > 1:
        tam = ndimage.sum(limpia, et, range(1, n + 1))
        limpia = et == (int(np.argmax(tam)) + 1)
    return limpia, float(sombra.sum() / max(figura.sum(), 1))


def mascara_limpia(rgb: np.ndarray) -> tuple[np.ndarray, dict]:
    """(máscara de la figura principal sin fondo ni sombras, datos de la separación)."""
    figura, sep = reconocer.separar_figura(rgb)
    if figura.sum() == 0:
        return figura, dict(sep, sombra_pegada_quitada=0.0)
    limpia, pegada = quitar_sombra_pegada(rgb, figura, reconocer._fondo(rgb))
    sep = dict(sep, sombra_pegada_quitada=round(pegada, 4))
    return limpia, sep


def cargar_con_mascara(ruta, recorte=None, lado: int = reconocer.LADO) -> tuple[np.ndarray, np.ndarray, dict]:
    """(rgb float32 0-255, máscara, datos) de una imagen en disco, con recorte opcional en fracciones."""
    rgb = reconocer.cargar(ruta, recorte, lado=lado)
    m, sep = mascara_limpia(rgb)
    return rgb, m, sep
