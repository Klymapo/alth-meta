"""Ajuste numérico (T3): reglas del torneo COPOX con un `construir` falso (sin Blender).

    python3 -m pytest tests/test_ajustar.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import ajustar as A  # noqa: E402

RECETA = {"nombre": "x", "piezas": [{"id": "cuerpo", "params": {"escala_r": 1.0, "ruido_r": 0.06, "segmentos": 10}}],
          "ajustables": [{"ruta": "piezas.0.params.ruido_r", "min": 0.0, "max": 0.12, "paso": 0.02},
                         {"ruta": "piezas.0.params.segmentos", "min": 8, "max": 12, "paso": 1},
                         {"ruta": "piezas.0.params.escala_r", "min": 0.9, "max": 1.1, "paso": 0.02}]}


def resultado(iou, dif_w=0.0, verif=True, tris=200):
    return {"iou": iou, "dimensiones_ok": abs(dif_w) <= 0.02, "dif_dimensiones": {"ancho": dif_w},
            "dif_cuerpo": {"W": dif_w}, "verificacion_ok": verif, "verificacion": {"checks": []},
            "tris": tris, "tris_max": 500, "hoja": "h.png"}


def falso(tabla):
    """construir(receta) → resultado según los parámetros (determinista)."""
    def construir(rc, carpeta):
        p = rc["piezas"][0]["params"]
        return tabla(p)
    return construir


def test_un_fail_veta_aunque_el_puntaje_sea_mayor():
    aud = A.auditar(resultado(0.99, verif=False), 0.8)
    assert not A.unanime(aud)
    aud = A.auditar(resultado(0.70), 0.8)                     # pierde más de 1 pp: regresión
    assert not A.unanime(aud) and any(x["id"] == "regresion_iou" and x["status"] == "FAIL" for x in aud)


def test_hermanos_son_deterministas_y_parten_de_la_baseline():
    h1 = A.hermanos(RECETA, resultado(0.8), 1)
    assert h1 == A.hermanos(RECETA, resultado(0.8), 1) and len(h1) == 3
    assert all(len(c) == 1 for c in h1)                       # sin corrección de escala si la medida cuadra
    h = A.hermanos(RECETA, resultado(0.8, dif_w=-0.04), 1)
    assert h[0] == [("piezas.0.params.escala_r", round(1 / 0.96, 4))]   # corrección en forma cerrada
    assert all(c[0][0] == "piezas.0.params.escala_r" for c in h)
    assert A.hermanos(RECETA, resultado(0.8), 2) != h1        # otra ronda, otros hermanos


def test_movimientos_respetan_limites():
    r = A.aplicar(RECETA, [("piezas.0.params.segmentos", 12)])
    movs = dict((v, k) for k, v in A.movimientos(r) if k == "piezas.0.params.segmentos")
    assert 13 not in movs and 11 in movs


def test_plateau_conserva_la_baseline(tmp_path):
    r = A.ajustar(RECETA, tmp_path, base=resultado(0.8, dif_w=-0.05),
                  construir=falso(lambda p: resultado(0.9, dif_w=-0.05)))    # nadie arregla la medida
    assert r["estado"] == "PLATEAU" and r["receta"] is None and r["iou_final"] == 0.8 and r["rondas"] == 3
    import json
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["status"] == "PLATEAU" and len(m["candidates"]) == 9
    assert all(c["padre"] == "baseline" and c["status"] == "REJECTED" for c in m["candidates"])


def test_gana_el_unanime_de_mayor_iou_y_los_rechazados_no_son_padres(tmp_path):
    def tabla(p):
        if p["escala_r"] == 1.0:
            return resultado(0.8, dif_w=-0.05)                 # sin corrección la medida falla
        return resultado(0.8 + p["ruido_r"], dif_w=0.0, verif=p["ruido_r"] < 0.07)   # más ruido, más IoU… hasta romper
    r = A.ajustar(RECETA, tmp_path, base=resultado(0.8, dif_w=-0.05), construir=falso(tabla))
    assert r["estado"] == "AJUSTADO" and r["ganador"] and r["receta"] is not None
    assert r["receta"]["piezas"][0]["params"]["ruido_r"] < 0.07   # el de 0.08 (más IoU) quedó vetado
    assert r["resultado"]["verificacion_ok"]


def test_sin_tiempo(tmp_path):
    r = A.ajustar(RECETA, tmp_path, base=resultado(0.8), plazo=0.0, construir=falso(lambda p: resultado(0.9)))
    assert r["estado"] == "SIN_TIEMPO" and r["rondas"] == 0
