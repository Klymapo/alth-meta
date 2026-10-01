"""ALTH-META · reconocimiento de imagen SOLO CON CÓDIGO: foto de referencia → FICHA JSON del asset.

Sin IA, sin modelos entrenados, sin API, sin claves y sin cuota. Solo numpy + scipy + Pillow (lo mismo
que ya instalan los workflows del repo). Es el primer paso de la "línea única": antes de modelar, el
proceso mide la imagen y dice qué técnicas exige. Después tools/capacidades.py compara la ficha con el
registro (kb/capacidades.json) para saber si "ya sabe hacerlo" o si hay que investigar.

Qué hace el código por sí solo
  - Separa la figura del fondo y mide su silueta: proporción, solidez, redondez, simetría, huecos,
    piezas delgadas que sobresalen.
  - Mide los colores dominantes y los ajusta a la paleta ALTH de spec/alth_spec.json.
  - Busca piel, cabeza con ojos, pelo, ropa, calzado, lentes y huecos entre dedos (técnicas clásicas:
    componentes conectados, casco convexo y "defectos de convexidad").
  - Compara la imagen con su MEMORIA (kb/huellas.json: huellas de los assets aprobados) y dice a qué se
    parece. Cada asset aprobado que se memoriza mejora el reconocimiento: se retroalimenta solo.
  - Convierte el tamaño de la vida real a milímetros ALTH con la escala de Theo Alpha.

Qué NO puede hacer (límites honestos)
  - Saber qué ES algo nuevo la primera vez: para el código una manzana roja y una pelota roja son casi la
    misma figura. Por eso el NOMBRE lo da el usuario al mandar la imagen. Las palabras del nombre también
    activan capacidades que no se miden en pixeles (vidrio, líquido, vehículo…; ver "palabras" en
    spec/capacidades_vocab.json). Lo que no se pueda medir ni deducir del nombre sale en `no_medible`.
  - Distinguir cilindro de caja en una vista de frente, o ver dedos que están ocultos (p. ej. manos en
    los bolsillos). Lo que no se ve, no se detecta.
  - Funciona mejor con UNA figura sobre fondo liso. Con infografías o escenas usa --recorte.

Tamaño: el usuario da el tamaño de la VIDA REAL (p. ej. "8cm"). Nunca necesita saber el tamaño en el
mundo GLB: lo calcula el código con  mm_alth = mm_real × s0 × k  (s0 sale de Theo Alpha).
Con un solo número, se toma como la medida mayor y la otra se deduce de la proporción de la silueta.
Sin número, se usa la memoria si el nombre coincide con un asset conocido; si no, queda "desconocido".

  python3 tools/reconocer.py reconocer refs/pendientes/espada.jpg --nombre espada --tamano 90cm --salida ficha.json
  python3 tools/reconocer.py reconocer hoja.png --nombre manzana --recorte 0.5,0,1,1
  python3 tools/reconocer.py memorizar assets/manzana          # guarda la huella de un asset aprobado
  python3 tools/reconocer.py validar ficha.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull, QhullError

RAIZ = Path(__file__).resolve().parents[1]
VOCAB_RUTA = RAIZ / "spec" / "capacidades_vocab.json"
SPEC_RUTA = RAIZ / "spec" / "alth_spec.json"
HUELLAS_RUTA = RAIZ / "kb" / "huellas.json"

LADO = 512                    # la imagen se reduce a este lado mayor antes de medir
UMBRAL_DE_FONDO = 6.0         # ΔE (Lab) máximo para considerar un pixel "color de fondo"
RAZON_PIEL_AB = 0.38          # a*/b* mínimo para piel (separa piel de pelo rubio)
# Hueco entre dedos (relativo a √área de la mano). Calibrado el 1 oct 2026: la mano abierta de
# refs/infografias/mano-con-regla.jpg da 4 huecos; las manos en los bolsillos de joven-rubio.jpg dan 0.
DEDO_PROFUNDIDAD, DEDO_ELONGACION, DEDO_ANCHO = 0.18, 2.8, 0.20
SUAVIDAD_SOMBRA = 0.6       # borde/interior de ΔE: debajo de esto, la mancha gris se desvanece = sombra
FUENTES_TAMANO = ("usuario", "memoria", "desconocido")
HEX = re.compile(r"#[0-9A-Fa-f]{6}")

# Escala provisional mientras no exista spec v2 (bloque T0): cuerpo de Theo Alpha sin pelo medido en
# su GLB el 1 oct 2026, y altura real de Theo que dio el usuario (≈1.80 m). Si la spec trae
# "escala_alpha": {"s0": …}, se usa esa y estas constantes se ignoran.
ALTO_ALPHA_MM_PROVISIONAL = 95.7
ALTO_REAL_THEO_MM_PROVISIONAL = 1800.0


# ================================================================ color
def _srgb_a_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb (…, 3) en 0-255 → Lab D65."""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def _hex_a_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def _rgb_a_hex(rgb) -> str:
    return "#" + "".join(f"{int(round(max(0, min(255, v)))):02X}" for v in rgb)


def cargar_paleta(spec: dict) -> list[tuple[str, str, np.ndarray]]:
    """[(familia, hex, lab)] de spec → paleta (+ los hex de paleta_notas). Excluye el fondo de revisión."""
    salida = []
    for nombre, valor in (spec.get("paleta") or {}).items():
        if nombre == "fondo_revision":
            continue
        if isinstance(valor, list):
            salida += [(nombre, h, None) for h in valor if isinstance(h, str) and HEX.fullmatch(h)]
        elif isinstance(valor, dict):
            salida += [(k, h, None) for k, h in valor.items() if isinstance(h, str) and HEX.fullmatch(h)]
    for nombre, nota in (spec.get("paleta_notas") or {}).items():
        for h in HEX.findall(str(nota))[:1]:
            salida.append((nombre, h, None))
    return [(f, h.upper(), _srgb_a_lab(_hex_a_rgb(h))) for f, h, _ in salida]


def _kmeans(x: np.ndarray, k: int, iteraciones: int = 20, semilla: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(semilla)
    centros = [x[rng.integers(len(x))]]
    for _ in range(1, k):                      # k-means++ determinista
        d = np.min(((x[:, None, :] - np.array(centros)[None]) ** 2).sum(-1), axis=1)
        if d.sum() == 0:
            break
        centros.append(x[rng.choice(len(x), p=d / d.sum())])
    c = np.array(centros)
    for _ in range(iteraciones):
        asign = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        nuevo = np.array([x[asign == i].mean(0) if np.any(asign == i) else c[i] for i in range(len(c))])
        if np.allclose(nuevo, c):
            break
        c = nuevo
    return c, asign


def colores_dominantes(rgb: np.ndarray, mascara: np.ndarray, paleta, k: int = 6) -> list[dict]:
    px = rgb[mascara]
    if len(px) == 0:
        return []
    if len(px) > 20000:
        px = px[np.random.default_rng(3).choice(len(px), 20000, replace=False)]
    lab = _srgb_a_lab(px)
    centros, asign = _kmeans(lab, min(k, len(lab)))
    salida = []
    for i in range(len(centros)):
        sel = asign == i
        if not np.any(sel):
            continue
        rgb_medio = px[sel].mean(0)
        lab_c = _srgb_a_lab(rgb_medio)
        mejor = min(paleta, key=lambda p: float(np.linalg.norm(p[2] - lab_c))) if paleta else None
        salida.append({"hex": _rgb_a_hex(rgb_medio), "porcentaje": round(100 * sel.mean(), 1),
                       "paleta": mejor[1] if mejor else None, "familia": mejor[0] if mejor else None,
                       "delta_e": round(float(np.linalg.norm(mejor[2] - lab_c)), 1) if mejor else None})
    return sorted(salida, key=lambda c: -c["porcentaje"])


def familias(colores: list[dict]) -> dict[str, float]:
    acc: dict[str, float] = {}
    for c in colores:
        if c.get("familia"):
            acc[c["familia"]] = acc.get(c["familia"], 0.0) + c["porcentaje"] / 100
    return {k: round(v, 3) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])}


# ================================================================ imagen y silueta
def cargar(ruta, recorte=None, lado: int = LADO) -> np.ndarray:
    im = Image.open(ruta).convert("RGB")
    if recorte:
        w, h = im.size
        x0, y0, x1, y1 = recorte
        im = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    escala = lado / max(im.size)
    if escala < 1:
        im = im.resize((max(1, round(im.width * escala)), max(1, round(im.height * escala))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32)


def _fondo(rgb: np.ndarray, borde: int = 4) -> np.ndarray:
    marco = np.concatenate([rgb[:borde].reshape(-1, 3), rgb[-borde:].reshape(-1, 3),
                            rgb[:, :borde].reshape(-1, 3), rgb[:, -borde:].reshape(-1, 3)])
    return np.median(marco, axis=0)


def separar_figura(rgb: np.ndarray) -> tuple[np.ndarray, dict]:
    """Máscara de la figura principal (sin sombra) y datos de la separación.

    1. Fondo = lo que se parece al color del borde (ΔE < UMBRAL_DE_FONDO) Y está conectado al borde de la
       imagen. Así un objeto crema o blanco no se pierde aunque se parezca al fondo: basta su contorno.
    2. Sombra = mancha gris (mismo tinte que el fondo, más oscura) cuyo borde se DESVANECE hacia el fondo.
       Un objeto gris (metal, el lado sombreado de una taza) tiene borde nítido y se conserva.
    """
    fondo = _fondo(rgb)
    lab = _srgb_a_lab(rgb)
    lab_f = _srgb_a_lab(fondo)
    de = ndimage.median_filter(np.linalg.norm(lab - lab_f, axis=-1), size=3)
    parecido = de < UMBRAL_DE_FONDO
    et_f, _ = ndimage.label(parecido)
    borde = np.unique(np.concatenate([et_f[0], et_f[-1], et_f[:, 0], et_f[:, -1]]))
    es_fondo = np.isin(et_f, borde[borde > 0])
    m = ~es_fondo
    # Huecos que atraviesan la figura (asa de taza): color de fondo encerrado, no conectado al borde.
    encerrado = parecido & ~es_fondo
    et_h, n_h = ndimage.label(encerrado)
    if n_h:
        tam_h = ndimage.sum(encerrado, et_h, range(1, n_h + 1))
        grandes = np.isin(et_h, 1 + np.where(tam_h > 0.002 * m.sum())[0])
        m &= ~grandes
    m = ndimage.binary_opening(m, iterations=1)
    # Sombras: gris neutro más oscuro que el fondo, con borde suave.
    croma = np.hypot(lab[..., 1] - lab_f[1], lab[..., 2] - lab_f[2])
    candidata = m & (croma < 7) & (lab[..., 0] < lab_f[0] - 3) & (lab[..., 0] > 0.3 * lab_f[0])
    et_s, n_s = ndimage.label(candidata)
    afuera = ndimage.binary_dilation(~m, iterations=2)
    filas = np.where(m.any(1))[0]
    sombra = np.zeros_like(m)
    if len(filas):
        corte = filas[0] + 0.5 * (filas[-1] - filas[0])
        for i in range(1, n_s + 1):
            sel = et_s == i
            if sel.sum() < 30 or np.argwhere(sel)[:, 0].mean() < corte:
                continue
            anillo = sel & afuera
            if anillo.sum() < 0.05 * sel.sum():          # casi no toca el fondo: es parte del objeto
                continue
            suavidad = float(de[anillo].mean() / max(de[sel].mean(), 1e-6))
            if suavidad < SUAVIDAD_SOMBRA:
                sombra |= sel
    sombra_quitada = float(sombra.sum() / max(m.sum(), 1))
    if sombra.any():
        m = ndimage.binary_opening(m & ~sombra, iterations=1)
    etiquetas, n = ndimage.label(m)
    if n == 0:
        return m, {"componentes": 0, "fondo": _rgb_a_hex(fondo), "sombra_quitada": 0.0, "fraccion_imagen": 0.0}
    tam = ndimage.sum(m, etiquetas, range(1, n + 1))
    principal = etiquetas == (int(np.argmax(tam)) + 1)
    total = m.sum()
    relevantes = int(np.sum(tam > 0.01 * total))
    return principal, {"componentes": relevantes, "fondo": _rgb_a_hex(fondo),
                       "sombra_quitada": round(sombra_quitada, 3),
                       "fraccion_imagen": round(float(principal.mean()), 4),
                       "fraccion_principal": round(float(principal.sum() / total), 3)}


def casco_convexo(m: np.ndarray) -> np.ndarray:
    pts = np.argwhere(m & ~ndimage.binary_erosion(m))
    if len(pts) < 3:
        return m.copy()
    try:
        h = ConvexHull(pts)
    except QhullError:
        return m.copy()
    poli = [(float(pts[i][1]), float(pts[i][0])) for i in h.vertices]
    im = Image.new("1", (m.shape[1], m.shape[0]), 0)
    ImageDraw.Draw(im).polygon(poli, fill=1, outline=1)
    return np.asarray(im, dtype=bool) | m


def _elongacion(coords: np.ndarray) -> float:
    if len(coords) < 3:
        return 1.0
    ev = np.sort(np.linalg.eigvalsh(np.cov(coords.T.astype(np.float64))))
    return float(math.sqrt(max(ev[-1], 1e-9) / max(ev[0], 1e-9)))


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 0.0


def _elipse_equivalente(m: np.ndarray) -> np.ndarray:
    c = np.argwhere(m).astype(np.float64)
    if len(c) < 5:
        return m.copy()
    mu = c.mean(0)
    cov = np.cov(c.T)
    inv = np.linalg.inv(cov + np.eye(2) * 1e-6)
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    d = np.stack([yy - mu[0], xx - mu[1]], -1)
    return np.einsum("...i,ij,...j->...", d, inv, d) <= 4.0   # elipse de 2 sigmas (área = π·4·√det)


def simetria_lr(m: np.ndarray) -> float:
    cols = np.where(m.any(0))[0]
    if len(cols) == 0:
        return 0.0
    cx = np.argwhere(m)[:, 1].mean()
    desplaz = int(round(m.shape[1] / 2 - cx))
    centrada = np.roll(m, desplaz, axis=1)
    return _iou(centrada, centrada[:, ::-1])


def medir_silueta(m: np.ndarray) -> tuple[dict, np.ndarray, np.ndarray]:
    lleno = ndimage.binary_fill_holes(m)
    filas, cols = np.where(lleno.any(1))[0], np.where(lleno.any(0))[0]
    alto, ancho = int(filas[-1] - filas[0] + 1), int(cols[-1] - cols[0] + 1)
    area = float(lleno.sum())
    casco = casco_convexo(lleno)
    huecos_m = lleno & ~m
    et_h, n_h = ndimage.label(huecos_m)
    huecos = [float(s) for s in ndimage.sum(huecos_m, et_h, range(1, n_h + 1))] if n_h else []
    huecos = [h for h in huecos if h > 0.005 * area]
    # Piezas delgadas que sobresalen: lo que se pierde al "abrir" la figura con un disco grande.
    r = max(2, int(0.12 * min(alto, ancho)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disco = (yy ** 2 + xx ** 2) <= r * r
    abierto = ndimage.binary_opening(lleno, structure=disco)
    if abierto.sum() < 0.3 * area:                # figura toda delgada (p. ej. una espada): no hay "cuerpo"
        abierto = lleno
    resto = lleno & ~abierto
    et_p, n_p = ndimage.label(resto)
    protuberancias = []
    for i in range(1, n_p + 1):
        sel = et_p == i
        a = float(sel.sum())
        if a < 0.006 * area:
            continue
        coords = np.argwhere(sel)
        con_hueco = bool(np.any(sel & huecos_m))
        protuberancias.append({"area_rel": round(a / area, 3), "elongacion": round(_elongacion(coords), 2),
                               "arriba": bool(coords[:, 0].mean() < filas[0] + 0.35 * alto),
                               "con_hueco": con_hueco})
    return {"alto_px": alto, "ancho_px": ancho, "aspecto_alto_ancho": round(alto / ancho, 3),
            "solidez": round(area / float(casco.sum()), 3),
            "redondez": round(_iou(abierto, _elipse_equivalente(abierto)), 3),
            "simetria": round(simetria_lr(lleno), 3),
            "simetria_cuerpo": round(simetria_lr(abierto), 3),
            "huecos": len(huecos), "huecos_area_rel": round(sum(huecos) / area, 3),
            "protuberancias": protuberancias}, lleno, abierto


# ================================================================ piel, cabeza, manos
def mascara_piel(rgb: np.ndarray, figura: np.ndarray, paleta) -> np.ndarray:
    pieles = [p[2] for p in paleta if p[0].startswith("piel")]
    if not pieles:
        return np.zeros_like(figura)
    lab = _srgb_a_lab(rgb)
    d = np.min(np.stack([np.linalg.norm(lab - p, axis=-1) for p in pieles]), axis=0)
    # La piel es más rojiza que el pelo rubio o el oro: a*/b* ≈ 0.40-0.55 en piel con luz ALTH,
    # 0.14-0.36 en pelo rubio (medido en refs/personajes/joven-rubio.jpg, 1 oct 2026).
    a, b = lab[..., 1], lab[..., 2]
    tono = (a > 4) & (b > 8) & (lab[..., 0] > 40) & (a >= RAZON_PIEL_AB * b) & (a < b * 1.6 + 8)
    return figura & (d < 22) & tono


def huecos_entre_dedos(comp: np.ndarray) -> int:
    """Cuenta huecos profundos y angostos entre la figura y su casco convexo (defectos de convexidad).
    Una mano abierta tiene 3-4; un puño o una mano metida en el bolsillo, ~0."""
    area = float(comp.sum())
    if area < 80:
        return 0
    casco = casco_convexo(comp)
    defectos = casco & ~comp
    prof = ndimage.distance_transform_edt(casco)
    et, n = ndimage.label(defectos)
    cuenta = 0
    escala = math.sqrt(area)
    for i in range(1, n + 1):
        sel = et == i
        a = float(sel.sum())
        if a < 0.004 * area:
            continue
        hondo = float(prof[sel].max())
        ancho = a / max(hondo, 1.0)
        if (hondo >= DEDO_PROFUNDIDAD * escala and _elongacion(np.argwhere(sel)) >= DEDO_ELONGACION
                and ancho <= DEDO_ANCHO * escala):
            cuenta += 1
    return cuenta


def analizar_personaje(rgb, figura, lleno, paleta) -> dict | None:
    """Busca cabeza con ojos dentro de la piel. Si no hay, no es personaje (para el código)."""
    piel = mascara_piel(rgb, lleno, paleta)
    filas = np.where(lleno.any(1))[0]
    y0, alto = int(filas[0]), int(filas[-1] - filas[0] + 1)
    # Se cierran huecos angostos para que unos lentes o una ceja no partan la cara en pedazos.
    r = max(2, int(round(0.012 * alto)))
    unida = ndimage.binary_closing(piel, structure=np.ones((2 * r + 1, 2 * r + 1)), iterations=1)
    et, n = ndimage.label(unida)
    if n == 0:
        return None
    tam = ndimage.sum(piel, et, range(1, n + 1))
    lab = _srgb_a_lab(rgb)
    cabeza = None
    for i in np.argsort(-tam):
        comp_unida = et == (i + 1)
        comp = comp_unida & piel
        if tam[i] < 0.01 * lleno.sum():
            break
        ys = np.where(comp.any(1))[0]
        if ys.mean() > y0 + 0.6 * alto:
            continue
        cara = ndimage.binary_fill_holes(comp_unida)
        rasgos = cara & ~comp_unida
        et_r, n_r = ndimage.label(rasgos)
        ojos = 0
        for j in range(1, n_r + 1):
            sel = et_r == j
            rel = sel.sum() / comp.sum()
            if 0.002 < rel < 0.12 and lab[sel][:, 0].mean() < 55:
                ojos += 1
        if ojos >= 2:
            cabeza = {"mascara": comp, "rasgos_oscuros": ojos, "top": int(ys[0]), "bottom": int(ys[-1]),
                      "alto": int(ys[-1] - ys[0] + 1)}
            break
    if cabeza is None:
        return None
    res = {"cabeza_rasgos": cabeza["rasgos_oscuros"]}
    cab = cabeza["mascara"]
    xs = np.where(cab.any(0))[0]
    # Lentes: componente muy oscuro sobre la cara que encierra huecos grandes.
    oscuro = lleno & (lab[..., 0] < 28)
    zona = np.zeros_like(oscuro)
    zona[cabeza["top"]:cabeza["bottom"] + 1, max(0, xs[0] - 5):xs[-1] + 6] = True
    et_o, n_o = ndimage.label(oscuro & zona)
    lentes = False
    for j in range(1, n_o + 1):
        sel = et_o == j
        dentro = ndimage.binary_fill_holes(sel) & ~sel
        if dentro.sum() > 0.03 * cab.sum():
            lentes = True
    res["lentes"] = lentes
    # Pelo: figura arriba de la cara que no es piel.
    arriba = lleno.copy()
    arriba[cabeza["top"] + int(0.25 * cabeza["alto"]):] = False
    pelo = arriba & ~piel
    res["pelo"] = bool(pelo.sum() > 0.08 * cab.sum())
    res["pelo_largo"] = False
    if res["pelo"]:
        color = np.median(lab[pelo], axis=0)
        parecido = lleno & (np.linalg.norm(lab - color, axis=-1) < 14)
        et_p, n_p = ndimage.label(parecido)
        ids = set(np.unique(et_p[pelo & parecido])) - {0}
        if ids:
            bajo = max(int(np.where((et_p == i).any(1))[0][-1]) for i in ids)
            res["pelo_largo"] = bajo > cabeza["bottom"] + 0.15 * cabeza["alto"]
    # Ropa y calzado: debajo de la cabeza.
    abajo_y0 = cabeza["bottom"]
    torso = lleno.copy()
    torso[:abajo_y0] = False
    torso[int(y0 + 0.9 * alto):] = False
    res["ropa"] = bool(torso.sum() and (torso & ~piel).sum() / torso.sum() > 0.6)

    def ancho_banda(f0, f1):
        b = lleno[int(f0):max(int(f0) + 1, int(f1))]
        cols = np.where(b.any(0))[0]
        return float(cols[-1] - cols[0] + 1) if len(cols) else 0.0

    resto = y0 + alto - abajo_y0
    hombros = ancho_banda(abajo_y0 + 0.02 * resto, abajo_y0 + 0.12 * resto)
    faldon = ancho_banda(abajo_y0 + 0.55 * resto, abajo_y0 + 0.70 * resto)
    res["ropa_holgada"] = bool(hombros and faldon > 1.08 * hombros)
    res["proporcion_faldon_hombros"] = round(faldon / hombros, 3) if hombros else None
    pie = lleno.copy()
    pie[: int(y0 + 0.93 * alto)] = False
    res["calzado"] = bool(pie.sum() and (pie & (lab[..., 0] < 35)).sum() / pie.sum() > 0.5)
    # Manos: piel que no es la cabeza ni está pegada a ella.
    resto_piel = piel & ~ndimage.binary_dilation(cab, iterations=3)
    et_m, n_m = ndimage.label(resto_piel)
    manos = [et_m == j for j in range(1, n_m + 1) if (et_m == j).sum() > 0.08 * cab.sum()]
    res["manos_visibles"] = len(manos)
    res["huecos_dedos"] = max([huecos_entre_dedos(mn) for mn in manos], default=0)
    res["alto_cabeza_rel"] = round(cabeza["alto"] / alto, 3)
    return res


# ================================================================ vocabulario, nombre y memoria
def cargar_vocab(ruta: Path = VOCAB_RUTA) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def nombre_id(texto: str) -> str:
    return _normalizar(texto).replace(" ", "_")[:41] or "sin_nombre"


def capacidades_por_nombre(nombre: str, vocab: dict) -> dict[str, str]:
    """Capacidades que activan las palabras del nombre (las que no se pueden medir en pixeles)."""
    n = f" {_normalizar(nombre)} "
    hallazgos = {}
    for cid, d in vocab["capacidades"].items():
        for p in d.get("palabras") or []:
            if f" {_normalizar(p)} " in n:
                hallazgos[cid] = f"el nombre dice '{p}'"
                break
    return hallazgos


def tipo_por_nombre(nombre: str, vocab: dict) -> str | None:
    n = f" {_normalizar(nombre)} "
    for tipo, palabras in (vocab.get("tipos_palabras") or {}).items():
        if any(f" {_normalizar(p)} " in n for p in palabras):
            return tipo
    return None


def cargar_huellas(ruta: Path = HUELLAS_RUTA) -> dict:
    ruta = Path(ruta)
    if not ruta.exists():
        return {"version": "1.0", "huellas": []}
    return json.loads(ruta.read_text(encoding="utf-8"))


def vector_forma(sil: dict) -> np.ndarray:
    # La cuenta de piezas que sobresalen es frágil (cambia con la vista): pesa poco.
    prot = [p for p in sil["protuberancias"] if p["area_rel"] >= 0.02]
    return np.array([math.log(max(sil["aspecto_alto_ancho"], 1e-3)), sil["solidez"], sil["redondez"],
                     sil["simetria_cuerpo"], min(sil["huecos_area_rel"] * 5, 1.0), 0.15 * min(len(prot), 3) / 3])


def colores_lab(colores: list[dict]) -> list[list[float]]:
    """[[L, a, b, fracción]] de los colores dominantes (lo que se guarda en la memoria)."""
    return [[*map(lambda v: round(float(v), 2), _srgb_a_lab(_hex_a_rgb(c["hex"]))), round(c["porcentaje"] / 100, 3)]
            for c in colores]


def distancia_color(a: list, b: list) -> float:
    """0 = mismos colores, 1 = nada que ver. Promedio ponderado del ΔE al color más cercano, en ambos sentidos."""
    if not a or not b:
        return 1.0
    A, B = np.array(a, dtype=float), np.array(b, dtype=float)
    d = np.linalg.norm(A[:, None, :3] - B[None, :, :3], axis=-1)
    ida = float((d.min(1) * A[:, 3]).sum() / max(A[:, 3].sum(), 1e-9))
    vuelta = float((d.min(0) * B[:, 3]).sum() / max(B[:, 3].sum(), 1e-9))
    return min(1.0, (ida + vuelta) / 2 / 40.0)


def parecidos(sil: dict, colores: list[dict], huellas: list[dict], n: int = 3) -> list[dict]:
    v = vector_forma(sil)
    mios = colores_lab(colores)
    salida = []
    for h in huellas:
        ds = float(np.linalg.norm(v - np.array(h["forma"])))
        dc = distancia_color(mios, h.get("colores", []))
        salida.append({"asset": h["asset"], "nombre": h["nombre"], "similitud": round(math.exp(-2.5 * (ds + dc)), 3),
                       "distancia_forma": round(ds, 3), "distancia_color": round(dc, 3)})
    return sorted(salida, key=lambda s: -s["similitud"])[:n]


def medidas_de_spec(medidas: dict) -> dict:
    """Normaliza las medidas reales de un spec.json de asset a {alto, ancho, fondo} en mm."""
    m = {k: float(v) for k, v in (medidas or {}).items() if isinstance(v, (int, float))}
    alto = next((m[k] for k in ("alto", "alto_cuerpo", "alto_con_tapa", "largo") if k in m), None)
    ancho = next((m[k] for k in ("ancho", "diametro", "diametro_boca", "diametro_arriba") if k in m), None)
    fondo = m.get("fondo", m.get("diametro", None))
    return {"alto": alto, "ancho": ancho, "fondo": fondo}


# ================================================================ tamaño y escala
def parsear_tamano(texto: str | None) -> dict:
    """'8cm' · '80' (mm) · '10x8cm' (alto x ancho) · '10x8x8 cm' · 'alto=10cm,ancho=8'. Regresa mm."""
    if not texto or not str(texto).strip():
        return {}
    t = str(texto).lower().replace(",", " ").replace("×", "x").strip()
    unidad = 10.0 if "cm" in t else 1000.0 if re.search(r"\d\s*m\b", t) else 1.0
    nombrados = dict(re.findall(r"(alto|ancho|fondo)\s*=\s*([\d.]+)", t))
    if nombrados:
        return {k: float(v) * unidad for k, v in nombrados.items()}
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums or any(v <= 0 for v in nums):
        raise ValueError(f"no entiendo el tamaño: {texto!r} (ej. '8cm', '10x8cm', 'alto=10cm')")
    if len(nums) == 1:
        return {"mayor": nums[0] * unidad}
    return dict(zip(("alto", "ancho", "fondo"), (v * unidad for v in nums)))


def completar_tamano(dado: dict, sil: dict) -> dict:
    """Con un solo número (medida mayor) deduce la otra con la proporción de la silueta."""
    asp = sil["aspecto_alto_ancho"]
    if "mayor" in dado:
        mayor = dado["mayor"]
        alto, ancho = (mayor, mayor / asp) if asp >= 1 else (mayor * asp, mayor)
        return {"alto": round(alto, 1), "ancho": round(ancho, 1), "fondo": None}
    alto, ancho = dado.get("alto"), dado.get("ancho")
    if alto and not ancho:
        ancho = alto / asp
    if ancho and not alto:
        alto = ancho * asp
    return {"alto": round(alto, 1) if alto else None, "ancho": round(ancho, 1) if ancho else None,
            "fondo": dado.get("fondo")}


def escala_s0(spec: dict) -> tuple[float, str]:
    ea = spec.get("escala_alpha") or {}
    if isinstance(ea.get("s0"), (int, float)):
        return float(ea["s0"]), "spec/alth_spec.json → escala_alpha.s0"
    return ALTO_ALPHA_MM_PROVISIONAL / ALTO_REAL_THEO_MM_PROVISIONAL, (
        f"PROVISIONAL: Theo Alpha {ALTO_ALPHA_MM_PROVISIONAL} mm / Theo real {ALTO_REAL_THEO_MM_PROVISIONAL:.0f} mm "
        "(se reemplaza al escribir spec v2)")


def factor_k(tipo: str, tam: dict, sil: dict, spec: dict) -> tuple[float, str]:
    ck = spec.get("conversion_k") or {}
    mayor = max([v for v in (tam.get("alto"), tam.get("ancho"), tam.get("fondo")) if v] or [0])
    if tipo == "personaje":
        return 1.0, "personaje: la altura real escala directo con s0"
    if tipo == "vehiculo":
        return float(ck.get("vehiculo", {}).get("k", 0.9)), "vehiculo"
    if tipo == "arquitectura":
        return float(ck.get("arquitectura", {}).get("k", 1.0)), "arquitectura"
    if tipo == "animal" and mayor and mayor <= 10 * ck.get("animal_pequeno", {}).get("max_real_cm", 60):
        return float(ck["animal_pequeno"]["k"]), "animal_pequeno"
    if tipo == "mueble":
        return 1.0, "mueble: se ancla al cuerpo (asiento=rodilla, escritorio=cadera…); k=1 provisional"
    if not mayor:
        return 1.0, "sin tamaño real: k sin definir"
    if mayor <= 10 * ck.get("de_mano", {}).get("max_real_cm", 20):
        return float(ck.get("de_mano", {}).get("k", 2.0)), "de_mano"
    if sil["aspecto_alto_ancho"] > 4 or sil["aspecto_alto_ancho"] < 0.25:
        return float(ck.get("largo_en_mano", {}).get("k", 1.0)), "largo_en_mano"
    if mayor <= 10 * ck.get("portatil", {}).get("max_real_cm", 60):
        return float(ck.get("portatil", {}).get("k", 1.3)), "portatil"
    return 1.0, "grande: k=1"


# ================================================================ reglas: medidas → capacidades
def _cap(caps: dict, cid: str, confianza: float, motivo: str):
    if cid not in caps or caps[cid]["confianza"] < confianza:
        caps[cid] = {"id": cid, "confianza": round(confianza, 2), "motivo": motivo}


def deducir_capacidades(tipo: str, sil: dict, per: dict | None, colores: list[dict]) -> dict:
    caps: dict[str, dict] = {}
    s, sc, red, sol = sil["simetria"], sil["simetria_cuerpo"], sil["redondez"], sil["solidez"]
    if s > 0.86:
        _cap(caps, "simetria_bilateral", min(1.0, (s - 0.86) / 0.1 + 0.6), f"simetría izq/der {s:.2f}")
    if tipo != "personaje":
        if sc > 0.88 and sol > 0.88:
            _cap(caps, "torno", min(1.0, 0.5 + (sc - 0.88) * 3 + (red - 0.8)), f"cuerpo simétrico {sc:.2f}, "
                 f"sólido {sol:.2f}, redondez {red:.2f} (de frente un cilindro y una caja se ven igual)")
        if sil["huecos"]:
            _cap(caps, "anillo", 0.75, f"{sil['huecos']} hueco(s) que atraviesan la figura (asa, argolla)")
        for p in sil["protuberancias"]:
            if p["con_hueco"]:
                _cap(caps, "anillo", 0.8, "pieza que sobresale con un hueco: asa")
            elif p["elongacion"] >= 3.0:
                _cap(caps, "prisma", 0.7, f"pieza delgada y alargada (elongación {p['elongacion']})")
            else:
                _cap(caps, "hoja", 0.55, f"pieza plana que sobresale (elongación {p['elongacion']})")
    # Metal NO se deduce del color: un gris, un blanco en sombra y un metal se ven igual en pixeles.
    # Solo lo activa el nombre ("lata", "espada"…), ver capacidades_por_nombre.
    if per:
        _cap(caps, "cuerpo_humanoide", 0.8, f"cabeza con piel y {per['cabeza_rasgos']} rasgos oscuros (ojos/cejas)")
        _cap(caps, "cabeza_cara", 0.8, f"{per['cabeza_rasgos']} rasgos oscuros dentro de la cara")
        _cap(caps, "rig_esqueleto", 0.9, "todo personaje se anima")
        if per["pelo"]:
            _cap(caps, "pelo_largo" if per["pelo_largo"] else "pelo_corto", 0.6,
                 "pelo arriba de la cara" + (", baja más allá de la barbilla" if per["pelo_largo"] else ""))
        if per["ropa"]:
            if per["ropa_holgada"]:
                _cap(caps, "ropa_holgada_tela", 0.5, f"la silueta se abre hacia abajo ({per['proporcion_faldon_hombros']}× los hombros)")
            _cap(caps, "ropa_ajustada", 0.5, "torso cubierto (no distingue bien prenda holgada de ajustada)")
        if per["calzado"]:
            _cap(caps, "calzado", 0.6, "base oscura en los pies")
        if per["lentes"]:
            _cap(caps, "accesorio_rigido", 0.6, "marco oscuro sobre la cara (posibles lentes)")
        if per["huecos_dedos"] >= 2:
            _cap(caps, "dedos", 0.7, f"{per['huecos_dedos']} huecos entre dedos en una mano visible")
    return caps


def cabeza_y_manos_sin_personaje(rgb, lleno, paleta) -> dict:
    """Para objetos que son puro cuerpo (p. ej. una mano suelta): busca dedos en la piel."""
    piel = mascara_piel(rgb, lleno, paleta)
    if piel.sum() < 0.3 * lleno.sum():
        return {"huecos_dedos": 0}
    et, n = ndimage.label(piel)
    tam = ndimage.sum(piel, et, range(1, n + 1))
    comp = et == (int(np.argmax(tam)) + 1)
    return {"huecos_dedos": huecos_entre_dedos(comp), "piel": round(float(piel.sum() / lleno.sum()), 3)}


# ================================================================ ficha
def reconocer(imagen, nombre: str, tamano: str | None = None, tipo: str | None = None, recorte=None,
              vocab: dict | None = None, spec: dict | None = None, huellas: dict | None = None) -> dict:
    vocab = vocab or cargar_vocab()
    spec = spec or json.loads(SPEC_RUTA.read_text(encoding="utf-8"))
    huellas = huellas if huellas is not None else cargar_huellas()
    paleta = cargar_paleta(spec)
    avisos: list[str] = []

    rgb = cargar(imagen, recorte)
    figura, sep = separar_figura(rgb)
    if sep["componentes"] == 0 or figura.sum() < 200:
        raise ValueError("no encontré ninguna figura sobre el fondo (¿imagen vacía o fondo no liso?)")
    sil, lleno, abierto = medir_silueta(figura)
    colores = colores_dominantes(rgb, lleno, paleta)
    fam = familias(colores)

    per = analizar_personaje(rgb, figura, lleno, paleta)
    tipo_nombre = tipo_por_nombre(nombre, vocab)
    if tipo:
        tipo_final, fuente_tipo = tipo, "usuario"
    elif per:
        tipo_final, fuente_tipo = "personaje", "medido (cabeza con ojos)"
    elif tipo_nombre:
        tipo_final, fuente_tipo = tipo_nombre, "nombre"
    else:
        tipo_final, fuente_tipo = "objeto", "por defecto (sin cabeza ni palabra clave)"
    if tipo_final not in vocab["tipos"]:
        raise ValueError(f"tipo inválido: {tipo_final!r}. Opciones: {', '.join(vocab['tipos'])}")
    if tipo_nombre and tipo_final != tipo_nombre and fuente_tipo != "usuario":
        avisos.append(f"el nombre sugiere '{tipo_nombre}' pero se midió '{tipo_final}'")

    caps = deducir_capacidades(tipo_final, sil, per if tipo_final == "personaje" else None, colores)
    extra = None
    if tipo_final != "personaje":
        extra = cabeza_y_manos_sin_personaje(rgb, lleno, paleta)
        if extra["huecos_dedos"] >= 2:
            _cap(caps, "dedos", 0.7, f"{extra['huecos_dedos']} huecos entre dedos")
            # Las "piezas que sobresalen" de una mano son sus dedos, no tallos ni hojas.
            for cid in ("prisma", "hoja"):
                if cid in caps and caps[cid]["motivo"].startswith("pieza"):
                    del caps[cid]
    for cid, motivo in capacidades_por_nombre(nombre, vocab).items():
        _cap(caps, cid, 0.9, motivo)
    # Decisiones de diseño del usuario: se exigen aunque la imagen no las muestre.
    for req in (vocab.get("requeridas_por_tipo") or {}).get(tipo_final, []):
        _cap(caps, req["id"], 1.0, req["motivo"])

    medibles = {cid for cid, d in vocab["capacidades"].items() if d.get("medible")}
    no_medible = sorted(cid for cid, d in vocab["capacidades"].items()
                        if not d.get("medible") and cid not in caps)

    mismas = [h for h in huellas.get("huellas", []) if h.get("tipo", "objeto") == tipo_final]
    parec = parecidos(sil, colores, mismas)
    nid = nombre_id(nombre)
    por_nombre = [h for h in huellas.get("huellas", []) if nid == h["nombre"] or nid in h.get("alias", [])]

    # tamaño
    try:
        dado = parsear_tamano(tamano)
    except ValueError as e:
        raise ValueError(str(e)) from None
    if dado:
        tam, fuente_tam = completar_tamano(dado, sil), "usuario"
    elif por_nombre and any(por_nombre[0].get("medidas_reales_mm", {}).values()):
        tam, fuente_tam = dict(por_nombre[0]["medidas_reales_mm"]), "memoria"
        avisos.append(f"tamaño tomado de la memoria ({por_nombre[0]['asset']}); si no es el mismo objeto, dalo con --tamano")
    else:
        tam, fuente_tam = {"alto": None, "ancho": None, "fondo": None}, "desconocido"
        avisos.append("sin tamaño real: pásalo con --tamano (p. ej. '8cm'); el resto de la ficha sí sirve")
    s0, fuente_s0 = escala_s0(spec)
    k, cat = factor_k(tipo_final, tam, sil, spec)
    tam_alth = {d: (round(v * s0 * k, 2) if v else None) for d, v in tam.items()}
    if "PROVISIONAL" in fuente_s0:
        avisos.append("escala provisional (Theo Alpha 95.7 mm ↔ 1.80 m) hasta que exista spec v2")

    # confianza global: calidad de la separación figura/fondo
    conf = 1.0
    if sep["fraccion_imagen"] < 0.02:
        conf -= 0.3
        avisos.append("la figura ocupa muy poco de la imagen; recórtala o usa una imagen más cercana")
    if sep["fraccion_imagen"] > 0.85:
        conf -= 0.4
        avisos.append("la 'figura' ocupa casi toda la imagen: el fondo no es liso o es una foto sin fondo")
    if sep["componentes"] > 3 or sep.get("fraccion_principal", 1) < 0.6:
        conf -= 0.3
        avisos.append(f"hay {sep['componentes']} manchas grandes (texto, paneles, otras figuras): "
                      "se midió solo la mayor; usa --recorte para aislar el objeto")
    conf = max(0.05, round(conf, 2))

    partes = ["cuerpo principal"]
    for p in sil["protuberancias"]:
        partes.append(("asa" if p["con_hueco"] else "pieza alargada" if p["elongacion"] >= 3 else "pieza plana")
                      + (" arriba" if p["arriba"] else ""))
    if per:
        partes = ["cabeza"] + (["pelo"] if per["pelo"] else []) + (["ropa"] if per["ropa"] else []) + \
                 (["calzado"] if per["calzado"] else []) + (["lentes"] if per["lentes"] else []) + \
                 [f"manos visibles: {per['manos_visibles']}"]
    principales = ", ".join(f"{c['familia']} {c['porcentaje']:.0f} %" for c in colores[:3] if c.get("familia"))
    descripcion = (f"{tipo_final} '{nombre}' medido por código: silueta {sil['aspecto_alto_ancho']:.2f} alto/ancho, "
                   f"simetría {sil['simetria']:.2f}, {len(sil['protuberancias'])} pieza(s) que sobresalen, "
                   f"{sil['huecos']} hueco(s); colores {principales or 'sin coincidencia en paleta'}.")
    if parec and parec[0]["similitud"] >= 0.6:
        descripcion += f" Se parece a '{parec[0]['nombre']}' de la memoria ({parec[0]['similitud']:.2f})."

    ficha = {"tipo": tipo_final, "fuente_tipo": fuente_tipo, "nombre": nid, "descripcion": descripcion,
             "partes": partes,
             "capacidades": sorted(caps.values(), key=lambda c: -c["confianza"]),
             "capacidades_nuevas": [], "no_medible": no_medible,
             "tamano_real_mm": tam, "fuente_tamano": fuente_tam,
             "tamano_alth_mm": tam_alth, "escala": {"s0": round(s0, 5), "fuente": fuente_s0, "k": k, "categoria": cat},
             "colores_dominantes": colores, "familias_color": fam,
             "parecidos": parec, "conocido_por_nombre": [h["asset"] for h in por_nombre],
             "medidas": {"separacion": sep, "silueta": sil, "personaje": per, "piel_objeto": extra},
             "confianza": conf}
    validar_ficha(ficha, vocab)
    sha = hashlib.sha256(Path(imagen).read_bytes()).hexdigest()
    ficha["_meta"] = {"imagen": str(imagen), "imagen_sha256": sha, "recorte": recorte, "metodo": "codigo",
                      "medibles_en_vocabulario": sorted(medibles),
                      "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"), "avisos": avisos}
    return ficha


def validar_ficha(ficha: dict, vocab: dict) -> dict:
    """Contrato que consume tools/capacidades.py. Lanza ValueError si no se cumple."""
    if not isinstance(ficha, dict):
        raise ValueError("la ficha debe ser un objeto JSON")
    if ficha.get("tipo") not in vocab["tipos"]:
        raise ValueError(f"tipo inválido: {ficha.get('tipo')!r}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]{0,40}", str(ficha.get("nombre", ""))):
        raise ValueError(f"nombre inválido: {ficha.get('nombre')!r}")
    for c in ficha.get("capacidades", []):
        if c.get("id") not in vocab["capacidades"]:
            raise ValueError(f"capacidad fuera del vocabulario: {c.get('id')!r}")
        if not 0 <= float(c.get("confianza", -1)) <= 1:
            raise ValueError(f"confianza inválida en {c.get('id')}")
    if ficha.get("fuente_tamano") not in FUENTES_TAMANO:
        raise ValueError(f"fuente_tamano inválida: {ficha.get('fuente_tamano')!r}")
    for k, v in (ficha.get("tamano_real_mm") or {}).items():
        if v is not None and (not isinstance(v, (int, float)) or v <= 0):
            raise ValueError(f"medida inválida {k}={v!r}")
    if not 0 <= float(ficha.get("confianza", -1)) <= 1:
        raise ValueError("confianza global inválida")
    return ficha


# ================================================================ memoria
def huella_de_asset(carpeta: Path, vocab: dict, spec: dict) -> dict:
    """Huella de un asset aprobado: silueta y colores de la vista de FRENTE de su final.png (hoja 2x2)."""
    carpeta = Path(carpeta)
    final = carpeta / "final.png"
    asset_spec = json.loads((carpeta / "spec.json").read_text(encoding="utf-8"))
    rgb = cargar(final, (0.0, 0.03, 0.5, 0.5))
    figura, _ = separar_figura(rgb)
    sil, lleno, _ = medir_silueta(figura)
    colores = colores_dominantes(rgb, lleno, cargar_paleta(spec))
    nombre = nombre_id(asset_spec.get("nombre") or carpeta.name)
    return {"asset": str(carpeta.relative_to(RAIZ)) if carpeta.is_absolute() and RAIZ in carpeta.parents else str(carpeta),
            "nombre": nombre, "alias": sorted({nombre_id(carpeta.name)} - {nombre}),
            "tipo": "objeto", "categoria": asset_spec.get("categoria"),
            "medidas_reales_mm": medidas_de_spec(asset_spec.get("medidas_reales_mm")),
            "forma": [round(float(x), 4) for x in vector_forma(sil)], "colores": colores_lab(colores),
            "familias": familias(colores),
            "evidencia": str(final.relative_to(RAIZ)) if final.is_absolute() and RAIZ in final.parents else str(final),
            "fecha": datetime.now(timezone.utc).date().isoformat()}


def memorizar(carpeta: Path, ruta: Path = HUELLAS_RUTA) -> dict:
    vocab, spec = cargar_vocab(), json.loads(SPEC_RUTA.read_text(encoding="utf-8"))
    carpeta = Path(carpeta).resolve()
    if not (carpeta / "final.png").exists():
        raise ValueError(f"{carpeta} no tiene final.png: solo se memorizan assets aprobados")
    h = huella_de_asset(carpeta, vocab, spec)
    datos = cargar_huellas(ruta)
    datos["huellas"] = [x for x in datos["huellas"] if x["asset"] != h["asset"]] + [h]
    datos["huellas"].sort(key=lambda x: x["asset"])
    datos["actualizado"] = h["fecha"]
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return h


# ================================================================ comandos
def _recorte(txt):
    if not txt:
        return None
    v = [float(x) for x in txt.split(",")]
    if len(v) != 4 or not all(0 <= x <= 1 for x in v) or v[0] >= v[2] or v[1] >= v[3]:
        raise SystemExit("[reconocer] --recorte es x0,y0,x1,y1 en fracciones 0-1 (p. ej. 0.5,0,1,1)")
    return v


def _resumen(f: dict) -> str:
    caps = ", ".join(f"{c['id']} ({c['confianza']:.2f})" for c in f["capacidades"]) or "—"
    tam = f["tamano_real_mm"]
    alth = f["tamano_alth_mm"]
    tam_txt = (f"real alto {tam['alto']} × ancho {tam['ancho']} mm → ALTH {alth['alto']} × {alth['ancho']} mm "
               f"({f['escala']['categoria']}, k={f['escala']['k']})") if tam.get("alto") else "tamaño desconocido"
    par = f["parecidos"][0] if f["parecidos"] else None
    return (f"{f['nombre']} · {f['tipo']} ({f['fuente_tipo']}) · confianza {f['confianza']:.2f}\n"
            f"  capacidades: {caps}\n  tamaño: {tam_txt} [{f['fuente_tamano']}]\n"
            + (f"  se parece a: {par['nombre']} ({par['similitud']:.2f})\n" if par and par["similitud"] >= 0.2 else ""))


def cmd_reconocer(args) -> int:
    if not Path(args.imagen).exists():
        print(f"[reconocer] no existe la imagen: {args.imagen}", file=sys.stderr)
        return 2
    try:
        ficha = reconocer(args.imagen, args.nombre, args.tamano, args.tipo, _recorte(args.recorte))
    except ValueError as e:
        print(f"[reconocer] {e}", file=sys.stderr)
        return 2
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(ficha, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(_resumen(ficha), end="")
    for a in ficha["_meta"]["avisos"]:
        print(f"  aviso: {a}")
    print(f"[reconocer] ficha guardada en {salida}")
    return 0


def cmd_memorizar(args) -> int:
    try:
        h = memorizar(Path(args.asset), Path(args.huellas))
    except (ValueError, FileNotFoundError) as e:
        print(f"[reconocer] no se memorizó: {e}", file=sys.stderr)
        return 2
    print(f"[reconocer] memorizado {h['asset']} ({h['nombre']})")
    return 0


def cmd_validar(args) -> int:
    try:
        validar_ficha(json.loads(Path(args.ficha).read_text(encoding="utf-8")), cargar_vocab())
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[reconocer] ficha inválida: {e}")
        return 2
    print("[reconocer] ficha válida")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Reconocimiento de imagen SOLO con código → ficha JSON (ALTH-META).")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconocer", help="mide la imagen y escribe la ficha")
    r.add_argument("imagen")
    r.add_argument("--nombre", required=True, help="qué es, en tus palabras (p. ej. 'manzana', 'vaso de vidrio')")
    r.add_argument("--tamano", default=None, help="tamaño REAL: '8cm', '10x8cm', 'alto=10cm' (sin unidad = mm)")
    r.add_argument("--tipo", default=None, help="solo si quieres forzarlo: objeto | personaje | mueble | …")
    r.add_argument("--recorte", default=None, help="x0,y0,x1,y1 en fracciones (aislar el objeto de una infografía)")
    r.add_argument("--salida", default="ficha.json")
    r.set_defaults(fn=cmd_reconocer)
    m = sub.add_parser("memorizar", help="guarda la huella de un asset APROBADO (carpeta con final.png)")
    m.add_argument("asset")
    m.add_argument("--huellas", default=str(HUELLAS_RUTA))
    m.set_defaults(fn=cmd_memorizar)
    v = sub.add_parser("validar", help="valida una ficha ya escrita")
    v.add_argument("ficha")
    v.set_defaults(fn=cmd_validar)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
