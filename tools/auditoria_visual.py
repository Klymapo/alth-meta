"""ALTH-META · auditoría visual: compara el render de un asset contra su imagen de referencia y DECIDE.

Es el gate de aprobación (decisión del dueño, 1 oct 2026: "esa auditoría define si se aprueba o no").
Sin modelos ni IA: numpy/scipy/Pillow, corre igual en un runner de GitHub que aquí.

Cómo compara (diseño de docs/AUDITORIA_VISUAL.md):
  1. Máscaras limpias con el MISMO código para las dos imágenes (tools/mascaras.py: fondo + sombras).
  2. Encuadre fijo: cada figura se recorta a su caja, se escala a la misma altura y se centra por su
     centroide horizontal. Así se compara la forma, no el tamaño ni la posición en la imagen.
  3. Varias medidas independientes, cada una con su umbral (spec/auditoria_visual.json):
       silueta  IoU                       ¿ocupan el mismo lugar?
       contorno distancia del borde (p95) ¿el borde se desvía en algún tramo? (orejas, asa, hoja)
       contorno distancia media del borde (chamfer)
       inercia  primer momento de Hu (compacidad), estable en figuras casi simétricas
       bandas   ancho por franja de altura, diferencia media ¿la proporción cambia a lo alto?
       aspecto  ancho/alto de la caja (|ln| del cociente)
       redondez cuánto llena el cuerpo su caja y sus 4 esquinas (redondo vs. caja de lados rectos)
       color    ΔE por celda de una rejilla 4×3 + colores dominantes, en Lab con L* a la mitad
     Informativas (no vetan): Dice, Hu completos (log, inestables en siluetas casi simétricas),
     banda máxima, SSIM de luminancia.
  4. Un FAIL veta; ningún puntaje compensa un FAIL (regla COPOX). Medidas sin datos = N-A.
  5. Vista: se audita cada vista del render y se elige la más parecida (o la declarada con --vista).
  6. Con --aprobado (hoja del asset aprobado, mismo encuadre): para REEMPLAZAR un asset aprobado el
     candidato tiene que superarlo (más IoU y menos desvío de contorno p95 que él); `no_peor_que_aprobado`
     queda como dato (tolerancia de spec/auditoria_visual.json).

Salida: auditoria.json + comparacion.png (azul = sólo referencia, naranja = sólo render, gris = ambos).
Código de salida: 0 PASS · 1 FAIL · 2 entrada inválida.

  python3 tools/auditoria_visual.py --ref refs/infografias/objeto-01-manzana.png --recorte 0.52,0.1,1,1 \
      --hoja .linea/crear/manzana/final.png --aprobado assets/manzana/final.png --salida /tmp/aud
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mascaras  # noqa: E402
import reconocer  # noqa: E402

UMBRALES_RUTA = RAIZ / "spec" / "auditoria_visual.json"
# Cuadrantes de la hoja 2x2 de alth.revisar (final.png): (x0, y0, x1, y1) en fracciones.
CUADRANTES = reconocer.VISTAS_HOJA      # frente, lateral, espalda, tres_cuartos (los mismos del reconocedor)
VISTAS_DEFECTO = ("frente", "tres_cuartos")
LADO = 256          # alto del lienzo normalizado
ALTO_FIG = 0.84     # fracción del lienzo que ocupa la altura de la figura
N_BANDAS = 10
REGIONES = (4, 3)   # rejilla de color: filas × columnas sobre la intersección
K_DOMINANTES = 6
PESO_L = 0.5
CUERPO_DESDE = 0.22   # la redondez se mide sin el 22 % superior de la figura (tallo, hoja)
ESQUINA = 0.20        # lado de cada esquina, en fracción del lado menor de la caja del cuerpo
# Medidas que vetan (un FAIL basta). Las demás del reporte son informativas.
VETO = ("silueta_iou", "contorno_p95", "contorno_chamfer", "compacidad", "bandas_media", "aspecto",
        "redondez_llenado", "redondez_esquinas", "color_regiones", "color_dominante")


# ================================================================ encuadre
def normalizar(rgb: np.ndarray, m: np.ndarray, lado: int = LADO) -> tuple[np.ndarray, np.ndarray]:
    """(rgb, máscara) en un lienzo de `lado` de alto: figura escalada a ALTO_FIG·lado de alto, en el mismo
    renglón y con su centroide horizontal al centro. El ancho del lienzo crece lo necesario para que la
    figura NUNCA se recorte (una figura 3:1 no debe parecer 2:1); `igualar` empareja dos lienzos.
    Mismo transform para color y máscara."""
    filas, cols = np.where(m.any(1))[0], np.where(m.any(0))[0]
    if len(filas) == 0:
        raise ValueError("máscara vacía: no hay figura que auditar")
    y0, y1, x0, x1 = filas[0], filas[-1] + 1, cols[0], cols[-1] + 1
    alto = int(round(ALTO_FIG * lado))
    s = alto / (y1 - y0)
    ancho = max(1, int(round((x1 - x0) * s)))
    mc = Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8)).resize((ancho, alto), Image.BILINEAR)
    cc = Image.fromarray(np.clip(rgb[y0:y1, x0:x1], 0, 255).astype(np.uint8)).resize((ancho, alto), Image.BILINEAR)
    mn = np.asarray(mc) > 127
    if mn.sum() < 20:
        raise ValueError("la figura es demasiado delgada para auditarla (se pierde al normalizar)")
    cx = float(np.where(mn)[1].mean())
    margen = (lado - alto) // 2
    W = max(int(1.5 * lado), 2 * int(np.ceil(max(cx, ancho - cx))) + 2 * margen)
    W += W % 2
    ox, oy = int(round(W / 2 - cx)), margen
    lienzo_m = np.zeros((lado, W), bool)
    lienzo_c = np.zeros((lado, W, 3), np.float32)
    lienzo_m[oy:oy + alto, ox:ox + ancho] = mn
    lienzo_c[oy:oy + alto, ox:ox + ancho] = np.asarray(cc, np.float32)
    return lienzo_c, lienzo_m


def igualar(a: tuple, b: tuple) -> tuple[tuple, tuple]:
    """Rellena el lienzo más angosto por los dos lados (el centroide queda al centro en ambos)."""
    W = max(a[1].shape[1], b[1].shape[1])

    def pad(t):
        c, m = t
        extra = W - m.shape[1]
        izq = extra // 2
        return (np.pad(c, ((0, 0), (izq, extra - izq), (0, 0))), np.pad(m, ((0, 0), (izq, extra - izq))))
    return pad(a), pad(b)


# ================================================================ medidas
def _borde(m: np.ndarray) -> np.ndarray:
    return m & ~ndimage.binary_erosion(m)


def contorno(a: np.ndarray, b: np.ndarray, alto: float) -> dict:
    ba, bb = _borde(a), _borde(b)
    if not ba.any() or not bb.any():
        return {"chamfer": 1.0, "p95": 1.0}
    da, db = ndimage.distance_transform_edt(~bb)[ba], ndimage.distance_transform_edt(~ba)[bb]
    return {"chamfer": float((da.mean() + db.mean()) / 2 / alto),
            "p95": float(max(np.percentile(da, 95), np.percentile(db, 95)) / alto)}


def hu(m: np.ndarray) -> np.ndarray:
    """7 momentos de Hu en escala log (signo · log10|h|), invariantes a escala, posición y rotación."""
    y, x = np.nonzero(m)
    y, x = y.astype(np.float64), x.astype(np.float64)
    m00 = float(len(x))
    xc, yc = x - x.mean(), y - y.mean()

    def eta(p, q):
        return float((xc ** p * yc ** q).sum()) / m00 ** (1 + (p + q) / 2)
    n20, n02, n11 = eta(2, 0), eta(0, 2), eta(1, 1)
    n30, n03, n21, n12 = eta(3, 0), eta(0, 3), eta(2, 1), eta(1, 2)
    h = np.array([
        n20 + n02,
        (n20 - n02) ** 2 + 4 * n11 ** 2,
        (n30 - 3 * n12) ** 2 + (3 * n21 - n03) ** 2,
        (n30 + n12) ** 2 + (n21 + n03) ** 2,
        (n30 - 3 * n12) * (n30 + n12) * ((n30 + n12) ** 2 - 3 * (n21 + n03) ** 2)
        + (3 * n21 - n03) * (n21 + n03) * (3 * (n30 + n12) ** 2 - (n21 + n03) ** 2),
        (n20 - n02) * ((n30 + n12) ** 2 - (n21 + n03) ** 2) + 4 * n11 * (n30 + n12) * (n21 + n03),
        (3 * n21 - n03) * (n30 + n12) * ((n30 + n12) ** 2 - 3 * (n21 + n03) ** 2)
        - (n30 - 3 * n12) * (n21 + n03) * (3 * (n30 + n12) ** 2 - (n21 + n03) ** 2),
    ])
    return np.sign(h) * np.log10(np.abs(h) + 1e-30)


def distancia_hu(a: np.ndarray, b: np.ndarray) -> float:
    """Diferencia de los 3 primeros momentos (log): los de orden alto son ruido en siluetas facetadas."""
    return float(np.max(np.abs(hu(a)[:3] - hu(b)[:3])))


def compacidad(a: np.ndarray, b: np.ndarray) -> float:
    """|ln| del cociente del primer momento de Hu (inercia normalizada): estable aunque la figura sea
    casi simétrica, a diferencia de los momentos de orden alto en escala log."""
    return float(abs(hu(a)[0] - hu(b)[0]) * np.log(10))


def anchos_por_banda(m: np.ndarray, n: int = N_BANDAS) -> np.ndarray:
    filas = np.where(m.any(1))[0]
    alto = filas[-1] - filas[0] + 1
    anchos = m.sum(1)[filas[0]:filas[-1] + 1].astype(float)
    return np.array([anchos[int(i * alto / n):max(int((i + 1) * alto / n), int(i * alto / n) + 1)].mean()
                     for i in range(n)]) / alto


def aspecto(m: np.ndarray) -> float:
    filas, cols = np.where(m.any(1))[0], np.where(m.any(0))[0]
    return (cols[-1] - cols[0] + 1) / (filas[-1] - filas[0] + 1)


def _cuerpo(m: np.ndarray, desde: float = CUERPO_DESDE) -> np.ndarray:
    """La figura sin su parte alta (tallo, hoja, asa superior): ahí se mide la redondez del cuerpo."""
    filas = np.where(m.any(1))[0]
    c = m.copy()
    c[:int(filas[0] + desde * (filas[-1] - filas[0]))] = False
    return c


def redondez(m: np.ndarray) -> dict:
    """Qué tan 'caja' es el cuerpo: fracción llena de su caja (elipse ≈ 0.785, caja = 1) y ocupación de
    las 4 esquinas de esa caja (lado = ESQUINA del lado menor). Una manzana redonda deja las esquinas
    vacías; una de lados rectos y hombros planos las llena (caso rechazado por el dueño el 1 oct 2026)."""
    c = _cuerpo(m)
    ys, xs = np.nonzero(c)
    if len(ys) < 50:
        return {"llenado": None, "esquinas": None}
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    lado = max(1, int(ESQUINA * min(y1 - y0, x1 - x0)))
    esq = [c[y0:y0 + lado, x0:x0 + lado], c[y0:y0 + lado, x1 - lado:x1],
           c[y1 - lado:y1, x0:x0 + lado], c[y1 - lado:y1, x1 - lado:x1]]
    return {"llenado": float(c.sum() / ((y1 - y0) * (x1 - x0))), "esquinas": [float(e.mean()) for e in esq]}


def _lab_ponderado(rgb: np.ndarray) -> np.ndarray:
    """Lab con L* a la mitad: el tono (a*b*) manda; la luz del render nunca es la de la referencia,
    pero sin nada de L* un crema y un gris oscuro serían el mismo color."""
    lab = reconocer._srgb_a_lab(rgb).astype(np.float64)
    lab[..., 0] *= PESO_L
    return lab


def color_regiones(ca, ma, cb, mb, filas: int = REGIONES[0], cols: int = REGIONES[1]) -> dict:
    """ΔE (Lab ponderado) entre las medianas de cada celda de una rejilla sobre la intersección.
    Devuelve la media (la que veta) y el detalle por celda (None = celda casi vacía)."""
    la, lb = _lab_ponderado(ca), _lab_ponderado(cb)
    inter = ma & mb
    if inter.sum() < 100:
        return {"media": None, "celdas": []}
    ys, xs = np.nonzero(inter)
    fy = np.linspace(ys.min(), ys.max() + 1, filas + 1).astype(int)
    fx = np.linspace(xs.min(), xs.max() + 1, cols + 1).astype(int)
    celdas = []
    for i in range(filas):
        fila = []
        for j in range(cols):
            sel = np.zeros_like(inter)
            sel[fy[i]:fy[i + 1], fx[j]:fx[j + 1]] = True
            sel &= inter
            if sel.sum() < 0.01 * inter.sum():
                fila.append(None)
                continue
            fila.append(round(float(np.linalg.norm(np.median(la[sel], 0) - np.median(lb[sel], 0))), 2))
        celdas.append(fila)
    vals = [v for f in celdas for v in f if v is not None]
    return {"media": float(np.mean(vals)) if vals else None, "celdas": celdas}


def color_dominante(ca, ma, cb, mb, k: int = K_DOMINANTES) -> float | None:
    """Distancia simétrica ponderada entre los k colores dominantes (Lab ponderado) de cada figura:
    cada color de una se empareja con el más cercano de la otra, pesado por su área."""
    if ma.sum() < 50 or mb.sum() < 50:
        return None

    def dom(c, m):
        x = _lab_ponderado(c)[m]
        if len(x) > 6000:
            x = x[np.random.default_rng(3).choice(len(x), 6000, replace=False)]
        cen, asg = reconocer._kmeans(x, k)
        return cen, np.bincount(asg, minlength=len(cen)) / len(asg)
    (ca_, pa), (cb_, pb) = dom(ca, ma), dom(cb, mb)
    d = np.linalg.norm(ca_[:, None] - cb_[None], axis=-1)
    return float((pa * d.min(1)).sum() / 2 + (pb * d.min(0)).sum() / 2)


def ssim_lum(ca, ma, cb, mb) -> float:
    """SSIM global de luminancia en la caja común (informativa: el facetado de la ref y del render
    nunca coincide cara por cara)."""
    caja = ma | mb
    la = reconocer._srgb_a_lab(ca)[..., 0][caja]
    lb = reconocer._srgb_a_lab(cb)[..., 0][caja]
    c1, c2 = (0.01 * 100) ** 2, (0.03 * 100) ** 2
    mu_a, mu_b = la.mean(), lb.mean()
    va, vb = la.var(), lb.var()
    cov = ((la - mu_a) * (lb - mu_b)).mean()
    return float((2 * mu_a * mu_b + c1) * (2 * cov + c2) / ((mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2)))


def medir(ref: tuple, cand: tuple) -> dict:
    """Todas las medidas entre (rgb, máscara) normalizados de la referencia y del candidato."""
    ca, ma = ref
    cb, mb = cand
    inter, union = (ma & mb).sum(), (ma | mb).sum()
    alto = ALTO_FIG * ma.shape[0]
    cont = contorno(ma, mb, alto)
    reg = color_regiones(ca, ma, cb, mb)
    ra, rb = redondez(ma), redondez(mb)
    if ra["llenado"] is None or rb["llenado"] is None:
        llenado = esquinas = None
    else:
        llenado = abs(ra["llenado"] - rb["llenado"])
        esquinas = float(np.mean(np.abs(np.array(ra["esquinas"]) - np.array(rb["esquinas"]))))
    dom = color_dominante(ca, ma, cb, mb)
    return {
        "silueta_iou": round(float(inter / max(union, 1)), 4),
        "dice": round(float(2 * inter / max(ma.sum() + mb.sum(), 1)), 4),
        "contorno_p95": round(cont["p95"], 4),
        "contorno_chamfer": round(cont["chamfer"], 4),
        "forma_hu": round(distancia_hu(ma, mb), 4),
        "bandas_max": round(float(np.max(np.abs(anchos_por_banda(ma) - anchos_por_banda(mb)))), 4),
        "bandas_media": round(float(np.mean(np.abs(anchos_por_banda(ma) - anchos_por_banda(mb)))), 4),
        "compacidad": round(compacidad(ma, mb), 4),
        "aspecto": round(abs(np.log(aspecto(mb) / aspecto(ma))), 4),
        "redondez_llenado": None if llenado is None else round(llenado, 4),
        "redondez_esquinas": None if esquinas is None else round(esquinas, 4),
        "color_regiones": None if reg["media"] is None else round(reg["media"], 2),
        "color_regiones_celdas": reg["celdas"],
        "color_dominante": None if dom is None else round(dom, 2),
        "ssim_lum": round(ssim_lum(ca, ma, cb, mb), 4),
    }


# ================================================================ veredicto
def cargar_umbrales(ruta: Path = UMBRALES_RUTA) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def veredicto(medidas: dict, umbrales: dict) -> dict:
    """PASS sólo si TODAS las medidas aplicables pasan; un FAIL veta. Sin dato = N-A (se excluye)."""
    reglas = umbrales["umbrales"]
    res = {}
    for k in VETO:
        v, r = medidas.get(k), reglas.get(k)
        if r is None or v is None:
            res[k] = "N-A"
        elif "min" in r:
            res[k] = "PASS" if v >= r["min"] else "FAIL"
        else:
            res[k] = "PASS" if v <= r["max"] else "FAIL"
    aplicables = [x for x in res.values() if x != "N-A"]
    return {"por_medida": res, "fallas": [k for k, x in res.items() if x == "FAIL"],
            "decision": "PASS" if aplicables and all(x == "PASS" for x in aplicables) else "FAIL"}


def _puntaje(m: dict) -> float:
    """Sólo para ELEGIR vista entre las del render (no decide nada): silueta menos desvío de borde."""
    return m["silueta_iou"] - m["contorno_p95"]


# ================================================================ entradas
def vistas_de_hoja(hoja, vistas=VISTAS_DEFECTO) -> dict:
    """{vista: (rgb, máscara, datos)} de los cuadrantes de una hoja 2x2 de alth.revisar."""
    out = {}
    for v in vistas:
        rgb, m, sep = mascaras.cargar_con_mascara(hoja, CUADRANTES[v])
        out[v] = (rgb, m, sep)
    return out


def auditar(ref_rgb, ref_m, vistas: dict, umbrales: dict, vista_declarada: str | None = None,
            aprobado: dict | None = None) -> dict:
    """Audita las vistas de un candidato contra la referencia. `vistas` = {nombre: (rgb, máscara, datos)};
    `aprobado` igual para el asset aprobado (opcional)."""
    if ref_m.sum() < 200:
        raise ValueError("la referencia no tiene figura (¿recorte?)")
    R = normalizar(ref_rgb, ref_m)
    por_vista = {}
    for nombre, (rgb, m, sep) in vistas.items():
        if m.sum() < 200:
            por_vista[nombre] = {"error": "vista sin figura", "separacion": sep}
            continue
        try:
            med = medir(*igualar(R, normalizar(rgb, m)))
        except ValueError as e:
            por_vista[nombre] = {"error": str(e), "separacion": sep}
            continue
        por_vista[nombre] = {"medidas": med, "veredicto": veredicto(med, umbrales), "separacion": sep}
    validas = {k: v for k, v in por_vista.items() if "medidas" in v}
    if not validas:
        raise ValueError("ninguna vista del render tiene figura")
    mejor = max(validas, key=lambda k: _puntaje(validas[k]["medidas"]))
    elegida = vista_declarada if vista_declarada in validas else mejor
    v = validas[elegida]
    decision = v["veredicto"]["decision"]
    fallas = list(v["veredicto"]["fallas"])
    out = {"vista": elegida, "vista_mas_parecida": mejor,
           "vista_contradice_declarada": bool(vista_declarada and mejor != vista_declarada),
           "medidas": v["medidas"], "por_medida": v["veredicto"]["por_medida"], "por_vista": por_vista,
           "umbrales": umbrales["umbrales"], "calibrado": umbrales.get("calibrado", False)}
    if vista_declarada and vista_declarada not in validas:
        out["aviso"] = f"la vista declarada '{vista_declarada}' no está en el render; se usó {elegida}"
    if aprobado:
        ap = auditar(ref_rgb, ref_m, aprobado, umbrales, vista_declarada=elegida if elegida in aprobado else None)
        am, cm = ap["medidas"], v["medidas"]
        tol = umbrales.get("tolerancia_vs_aprobado", {"silueta_iou": 0.01, "contorno_p95": 0.005})
        no_peor = (cm["silueta_iou"] >= am["silueta_iou"] - tol["silueta_iou"]
                   and cm["contorno_p95"] <= am["contorno_p95"] + tol["contorno_p95"])
        out["aprobado"] = {"vista": ap["vista"], "medidas": am, "decision_propia": ap["decision"]}
        supera = bool(cm["silueta_iou"] > am["silueta_iou"] and cm["contorno_p95"] < am["contorno_p95"])
        out["no_peor_que_aprobado"] = bool(no_peor)
        out["supera_aprobado"] = supera
        # Reemplazar un asset aprobado exige SUPERARLO (decisión del dueño: "el chiste es superar la
        # manzana"); quedar igual o apenas peor no justifica cambiarlo.
        out["por_medida"]["supera_aprobado"] = "PASS" if supera else "FAIL"
        if not supera:
            fallas.append("supera_aprobado")
            decision = "FAIL"
    out["fallas"], out["decision"] = fallas, decision
    return out


# ================================================================ evidencia
def comparacion_png(ref_rgb, ref_m, cand_rgb, cand_m, ruta: Path) -> None:
    """Lado a lado: referencia | candidato | superposición (azul = sólo ref, naranja = sólo render)."""
    (ca, ma), (cb, mb) = igualar(normalizar(ref_rgb, ref_m), normalizar(cand_rgb, cand_m))
    fondo = np.array([227, 226, 233], np.float32)
    a = np.where(ma[..., None], ca, fondo)
    b = np.where(mb[..., None], cb, fondo)
    sup = np.tile(fondo, ma.shape + (1,))
    sup[ma & mb] = (150, 150, 160)
    sup[ma & ~mb] = (40, 110, 220)
    sup[mb & ~ma] = (240, 140, 30)
    for m, color in ((ma, (20, 60, 160)), (mb, (180, 80, 0))):
        sup[_borde(m)] = color
    sep = np.full((ma.shape[0], 4, 3), 255, np.float32)
    img = np.concatenate([a, sep, b, sep, sup], axis=1).astype(np.uint8)
    Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(ruta)


def _recorte(txt):
    if not txt:
        return None
    r = tuple(float(x) for x in txt.split(","))
    if len(r) != 4 or not all(0 <= x <= 1 for x in r) or r[0] >= r[2] or r[1] >= r[3]:
        raise ValueError("--recorte debe ser x0,y0,x1,y1 en fracciones 0-1")
    return r


def _vistas_cli(hoja, renders) -> dict:
    vistas = vistas_de_hoja(hoja) if hoja else {}
    for r in renders or []:
        nombre, _, ruta = r.partition("=")
        if not ruta:
            raise ValueError("--render va como vista=ruta.png")
        vistas[nombre] = mascaras.cargar_con_mascara(ruta)
    if not vistas:
        raise ValueError("falta --hoja o --render")
    return vistas


def auditar_archivos(ref, salida, recorte=None, hoja=None, renders=None, aprobado=None, vista=None,
                     umbrales=UMBRALES_RUTA) -> dict:
    """Audita archivos en disco y deja la evidencia (auditoria.json + comparacion.png) en `salida`.
    Lo usan la CLI, tools/crear_asset.py (gate de la corrida) y tools/publicar.py (gate de publicación).
    Lanza ValueError / OSError si la entrada no sirve."""
    ref_rgb, ref_m, ref_sep = mascaras.cargar_con_mascara(ref, recorte)
    vistas = _vistas_cli(hoja, renders)
    ap = vistas_de_hoja(aprobado) if aprobado and Path(aprobado).exists() else None
    r = auditar(ref_rgb, ref_m, vistas, cargar_umbrales(Path(umbrales)), vista, ap)
    r["entradas"] = {"ref": str(ref), "recorte": list(recorte) if recorte else None, "hoja": str(hoja) if hoja else None,
                     "render": renders, "aprobado": str(aprobado) if ap else None, "separacion_ref": ref_sep}
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    rgb, m, _ = vistas[r["vista"]]
    comparacion_png(ref_rgb, ref_m, rgb, m, salida / "comparacion.png")
    r["evidencia"] = {"json": str(salida / "auditoria.json"), "comparacion": str(salida / "comparacion.png")}
    (salida / "auditoria.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return r


def resumen_texto(r: dict) -> str:
    lineas = [f"auditoría visual: {r['decision']} · vista {r['vista']} · fallas: {', '.join(r['fallas']) or 'ninguna'}"]
    for k, v in r["por_medida"].items():
        lineas.append(f"  {v:4}  {k} = {r['medidas'].get(k, '')}")
    if r.get("aprobado"):
        lineas.append(f"  vs aprobado: no peor {r['no_peor_que_aprobado']} · lo supera {r['supera_aprobado']}")
    if not r["calibrado"]:
        lineas.append("  (umbrales provisionales: falta calibrarlos con veredictos del dueño, tools/calibrar_auditoria.py)")
    return "\n".join(lineas)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", required=True, help="imagen de referencia")
    ap.add_argument("--recorte", default=None, help="x0,y0,x1,y1 de la referencia (infografías)")
    ap.add_argument("--hoja", default=None, help="hoja 2x2 del candidato (final.png de alth.revisar)")
    ap.add_argument("--render", action="append", help="vista=ruta.png (se puede repetir)")
    ap.add_argument("--aprobado", default=None, help="hoja 2x2 del asset aprobado (RegressionGuard)")
    ap.add_argument("--vista", default=None, help="vista que muestra la referencia, si se sabe")
    ap.add_argument("--umbrales", default=str(UMBRALES_RUTA))
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    try:
        if a.aprobado and not Path(a.aprobado).exists():
            raise FileNotFoundError(f"no existe la hoja aprobada {a.aprobado}")
        r = auditar_archivos(a.ref, a.salida, _recorte(a.recorte), a.hoja, a.render, a.aprobado, a.vista, a.umbrales)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001  un fallo interno nunca debe leerse como FAIL "de forma"
        print(f"ERROR interno ({type(e).__name__}): {e}", file=sys.stderr)
        return 2
    print(resumen_texto(r))
    return 0 if r["decision"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
