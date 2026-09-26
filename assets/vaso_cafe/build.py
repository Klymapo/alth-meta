"""Vaso de café para llevar ALTH · objeto de mano (k=2.0).

    alth-python assets/vaso_cafe/build.py            # iteración
    alth-python assets/vaso_cafe/build.py final      # render final + GLB (solo tras aprobación)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"
H, R_TAPA, R_BASE = 12.86, 10.06 / 2, 6.71 / 2      # de spec.json
LADOS = 14
BLANCO, FUNDA, TAPA = "#FBF8F4", "#B08A62", "#2C2320"   # funda: carton_kraft (paleta_notas)
Z_BOCA = 11.1                                       # donde termina el vaso y empieza la tapa
R_BOCA = 4.75
F0, F1 = 3.9, 8.6                                   # funda
CARTON = 0.16                                       # grosor de la funda

alth.nueva_escena()


def radio(z):  # pared cónica del vaso
    return R_BASE + (R_BOCA - R_BASE) * z / Z_BOCA


# Una sola malla: vaso, funda (escalón hacia afuera) y tapa (faldón + segundo nivel), coloreada por bandas.
perfil = [
    (R_BASE * 0.93, 0.0), (radio(0.3), 0.3),
    (radio(F0), F0), (radio(F0) + CARTON, F0 + 0.08), (radio(F1) + CARTON, F1 - 0.08), (radio(F1), F1),
    (R_BOCA, Z_BOCA),
    # v2: faldón más bajo y segundo nivel más alto y metido, para que el escalón de la tapa se lea
    (R_TAPA, Z_BOCA + 0.1), (R_TAPA, 11.65), (R_TAPA - 0.25, 11.8),          # faldón de la tapa
    (R_TAPA - 0.75, 11.85), (R_TAPA - 0.9, H - 0.15), (R_TAPA - 1.1, H),     # segundo nivel
]
cuerpo = alth.torno(
    "Vaso_cuerpo", perfil, segmentos=LADOS, alternar=False, ruido_r=0, ruido_z=0, giro=0,
    centro_abajo=0.12, centro_arriba=H,
    bandas=[(F0 + 0.01, BLANCO), (F1 - 0.01, FUNDA), (Z_BOCA - 0.01, BLANCO), (99, TAPA)])

objs = [cuerpo]
alth.estudio()
rep = alth.revisar(objs, alth.RAIZ / "renders" / "vaso_cafe" / MODO, modo=MODO, titulo=f"vaso_cafe v2 · {MODO}",
                   asset=alth.RAIZ / "assets" / "vaso_cafe" / "spec.json")
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["medidas_mm"], rep["segundos_total"])
if MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "vaso_cafe" / "vaso_cafe.glb")
