"""Manzana ALTH · objeto de mano (k=2.0). Uso: alth-python assets/manzana/build.py [iteracion|final]"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402
import bmesh  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
RAIZ = alth.RAIZ
R, H = 8.94 / 2, 8.05          # radio y alto del cuerpo (mm)
SEG = 12                       # segmentos alrededor
ROJO, MARRON, VERDE = "#A8453B", "#69472D", "#7E9B7A"

# Perfil (r relativo a R, z relativo a H), de abajo hacia arriba
PERFIL = [(0.38, 0.00), (0.68, 0.07), (0.88, 0.24), (0.99, 0.47),
          (1.00, 0.68), (0.84, 0.87), (0.44, 0.97)]
Z_BASE_CENTRO, Z_HUNDIDO = 0.03, 0.76   # hundido leve abajo y cuenca del tallo


def cuerpo():
    rnd = random.Random(7)
    bm = bmesh.new()
    anillos = []
    for i, (rr, zz) in enumerate(PERFIL):
        desfase = (i % 2) * math.pi / SEG      # anillos alternados → facetas triangulares
        anillo = []
        for s in range(SEG):
            a = 2 * math.pi * s / SEG + desfase
            j = 1 + rnd.uniform(-0.05, 0.05) if 0 < i < len(PERFIL) - 1 else 1
            z = zz * H + (rnd.uniform(-0.12, 0.12) if 0 < i < len(PERFIL) - 1 else 0)
            anillo.append(bm.verts.new((rr * R * j * math.cos(a), rr * R * j * math.sin(a), z)))
        anillos.append(anillo)
    abajo = bm.verts.new((0, 0, Z_BASE_CENTRO * H))
    arriba = bm.verts.new((0, 0, Z_HUNDIDO * H))
    for s in range(SEG):
        n = (s + 1) % SEG
        bm.faces.new((abajo, anillos[0][n], anillos[0][s]))
        bm.faces.new((arriba, anillos[-1][s], anillos[-1][n]))
    for i in range(len(anillos) - 1):
        a, b = anillos[i], anillos[i + 1]
        for s in range(SEG):
            n = (s + 1) % SEG
            if i % 2 == 0:   # el anillo de arriba va adelantado medio segmento
                bm.faces.new((a[s], a[n], b[s]))
                bm.faces.new((a[n], b[n], b[s]))
            else:            # el de abajo va adelantado
                bm.faces.new((a[s], b[n], b[s]))
                bm.faces.new((a[s], a[n], b[n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = alth._objeto("Manzana_cuerpo", bm)
    obj.data.materials.append(alth.material("M_manzana_rojo", ROJO))
    return obj


def tallo():
    bm = bmesh.new()
    base, punta, largo = 0.78, 0.58, 3.1
    abajo = [bm.verts.new((x * base / 2, y * base / 2, 0)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    arriba = [bm.verts.new((x * punta / 2, y * punta / 2, largo)) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(abajo[::-1])
    bm.faces.new(arriba)
    for s in range(4):
        n = (s + 1) % 4
        bm.faces.new((abajo[s], abajo[n], arriba[n], arriba[s]))
    obj = alth._objeto("Manzana_tallo", bm)
    obj.location = (0, 0, Z_HUNDIDO * H - 0.3)
    obj.rotation_euler = (math.radians(6), math.radians(-18), math.radians(20))
    obj.data.materials.append(alth.material("M_manzana_tallo", MARRON))
    return obj


def hoja():
    bm = bmesh.new()
    L, W, t, alza = 3.8, 1.15, 0.2, 0.35
    sup = [(0, 0, 0), (0.45 * L, W, 0), (L, 0, 0), (0.45 * L, -W, 0), (0.45 * L, 0, alza)]
    vs = [bm.verts.new(p) for p in sup]
    vi = [bm.verts.new((x, y, z - t)) for x, y, z in sup]
    b, izq, tip, der, m = vs
    bi, ii, ti, di, mi = vi
    for f in ((b, m, izq), (m, tip, izq), (b, der, m), (m, der, tip)):
        bm.faces.new(f)
    for f in ((bi, ii, mi), (mi, ii, ti), (bi, mi, di), (mi, ti, di)):
        bm.faces.new(f)
    for p, q, pi, qi in ((b, izq, bi, ii), (izq, tip, ii, ti), (tip, der, ti, di), (der, b, di, bi)):
        bm.faces.new((p, pi, qi, q))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = alth._objeto("Manzana_hoja", bm)
    obj.location = (0.3, 0.0, Z_HUNDIDO * H + 1.5)
    obj.rotation_euler = (math.radians(50), math.radians(-32), math.radians(-10))
    obj.data.materials.append(alth.material("M_manzana_hoja", VERDE))
    return obj


alth.nueva_escena()
objs = [cuerpo(), tallo(), hoja()]
alth.estudio()
rep = alth.revisar(objs, RAIZ / "renders" / "manzana" / MODO, modo=MODO, titulo=f"manzana · {MODO}")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, RAIZ / "assets" / "manzana" / "manzana.glb")
