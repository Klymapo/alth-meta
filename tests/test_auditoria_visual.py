"""Pruebas de la auditoría visual (gate de aprobación), de las máscaras compartidas y de la calibración.

    python3 -m pytest tests/test_auditoria_visual.py

Sin Blender, sin red, sin IA. Dos tipos de prueba:
  - figuras sintéticas: cada medida por separado, con resultado conocido de antemano;
  - la matriz real del repo: cada asset aprobado PASA contra su referencia y FALLA contra la de otro
    objeto (si un cambio rompe esto, la auditoría dejó de distinguir lo que ya distinguía).
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import auditoria_visual as A  # noqa: E402
import calibrar_auditoria as C  # noqa: E402
import mascaras as M  # noqa: E402

FONDO = (227, 226, 233)
U = A.cargar_umbrales()
MANZANA = ("refs/infografias/objeto-01-manzana.png", (0.52, 0.1, 1, 1))
LATA = ("refs/infografias/objeto-02-lata-aceitunas.png", (0.66, 0.1, 1, 1))


def figura(forma="elipse", color=(190, 70, 60), w=300, h=300, caja=(80, 60, 220, 250), sombra=False, segundo=None):
    im = Image.new("RGB", (w, h), FONDO)
    d = ImageDraw.Draw(im)
    if sombra:   # sombra de piso pegada: gris neutro, más oscuro que el fondo, borde suave
        x0, y0, x1, y1 = caja
        for i in range(12):
            g = 205 + i * 2
            d.ellipse((x0 - 30 + i * 2, y1 - 14 + i, x1 + 60 - i * 2, y1 + 14 - i), fill=(g, g, g + 6))
    (d.ellipse if forma == "elipse" else d.rectangle)(caja, fill=color)
    if segundo:
        d.rectangle(segundo[0], fill=segundo[1])
    return np.asarray(im, np.float32)


def vistas_de(rgb):
    m, sep = M.mascara_limpia(rgb)
    return {"frente": (rgb, m, sep)}


def auditar(ref, cand, umbrales=U, **kw):
    ref_m, _ = M.mascara_limpia(ref)
    return A.auditar(ref, ref_m, vistas_de(cand), umbrales, **kw)


# ---------------------------------------------------------------- máscaras
def test_mascara_quita_sombra_pegada():
    con = figura(sombra=True)
    sin = figura()
    m_con, sep = M.mascara_limpia(con)
    m_sin, _ = M.mascara_limpia(sin)
    iou = (m_con & m_sin).sum() / (m_con | m_sin).sum()
    assert iou > 0.95, iou


def test_mascara_conserva_pieza_gris_de_borde_nitido():
    # base gris metálica pegada abajo, de borde nítido: es pieza, no sombra
    rgb = figura(color=(120, 160, 90), caja=(90, 60, 210, 220), segundo=((80, 220, 220, 250), (150, 152, 158)))
    m, _ = M.mascara_limpia(rgb)
    assert m[235, 150] and m[235, 85], "la base gris se perdió"


def test_kaggle_usa_las_mismas_mascaras():
    import kaggle_proveedor as K
    assert K.quitar_sombra_pegada is M.quitar_sombra_pegada


# ---------------------------------------------------------------- medidas sintéticas
def test_misma_figura_pasa():
    r = auditar(figura(), figura())
    assert r["decision"] == "PASS", r["fallas"]
    assert r["medidas"]["silueta_iou"] > 0.97


def test_encuadre_fijo_ignora_tamano_y_posicion():
    chica = figura(caja=(30, 100, 100, 195))      # misma proporción (140x190 → 70x95), otro lugar
    r = auditar(figura(), chica)
    assert r["decision"] == "PASS", (r["fallas"], r["medidas"])


def test_otra_forma_falla_por_forma():
    r = auditar(figura("elipse"), figura("rect"))
    assert r["decision"] == "FAIL"
    assert {"silueta_iou", "contorno_p95"} & set(r["fallas"]), r["fallas"]


def test_proporcion_distinta_falla():
    r = auditar(figura(caja=(80, 60, 220, 250)), figura(caja=(40, 60, 260, 250)))
    assert "aspecto" in r["fallas"] or "bandas_media" in r["fallas"], r["fallas"]


def test_color_distinto_falla_aunque_la_forma_coincida():
    r = auditar(figura(color=(190, 70, 60)), figura(color=(70, 120, 190)))
    assert r["decision"] == "FAIL"
    assert "color_dominante" in r["fallas"] and "color_regiones" in r["fallas"], r["fallas"]
    assert r["por_medida"]["silueta_iou"] == "PASS"


def test_un_fail_veta_aunque_todo_lo_demas_pase():
    medidas = {k: 0.0 for k in A.VETO}
    medidas["silueta_iou"] = 0.99
    assert A.veredicto(medidas, U)["decision"] == "PASS"
    medidas["color_dominante"] = 99.0
    v = A.veredicto(medidas, U)
    assert v["decision"] == "FAIL" and v["fallas"] == ["color_dominante"]


def test_medida_sin_dato_es_na_y_no_cuenta():
    medidas = {k: 0.0 for k in A.VETO}
    medidas["silueta_iou"] = 0.99
    medidas["color_regiones"] = None
    v = A.veredicto(medidas, U)
    assert v["por_medida"]["color_regiones"] == "N-A" and v["decision"] == "PASS"


def test_sin_medidas_aplicables_no_pasa():
    assert A.veredicto({}, {"umbrales": {}})["decision"] == "FAIL"


def test_peor_que_aprobado_falla():
    ref = figura()
    ref_m, _ = M.mascara_limpia(ref)
    bueno = vistas_de(figura())
    regular = vistas_de(figura(caja=(80, 60, 228, 250)))     # un poco más ancha: pasa sola
    solo = A.auditar(ref, ref_m, regular, U)
    assert solo["decision"] == "PASS", solo["fallas"]
    r = A.auditar(ref, ref_m, regular, U, aprobado=bueno)
    assert r["no_peor_que_aprobado"] is False and r["decision"] == "FAIL"
    r2 = A.auditar(ref, ref_m, bueno, U, aprobado=regular)
    assert r2["no_peor_que_aprobado"] and r2["supera_aprobado"] and r2["decision"] == "PASS"


def test_elige_la_vista_mas_parecida_y_avisa_si_contradice():
    ref = figura()
    ref_m, _ = M.mascara_limpia(ref)
    vistas = {"frente": vistas_de(figura("rect"))["frente"], "tres_cuartos": vistas_de(figura())["frente"]}
    r = A.auditar(ref, ref_m, vistas, U)
    assert r["vista"] == "tres_cuartos" and r["decision"] == "PASS"
    r = A.auditar(ref, ref_m, vistas, U, vista_declarada="frente")
    assert r["vista"] == "frente" and r["vista_contradice_declarada"] and r["decision"] == "FAIL"


def test_referencia_vacia_es_error():
    vacia = np.full((200, 200, 3), FONDO, np.float32)
    try:
        auditar(vacia, figura())
    except ValueError:
        return
    raise AssertionError("una referencia sin figura debe ser error de entrada")


# ---------------------------------------------------------------- CLI y evidencia
def test_cli_codigos_y_evidencia():
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        Image.fromarray(figura().astype(np.uint8)).save(t / "ref.png")
        Image.fromarray(figura().astype(np.uint8)).save(t / "ok.png")
        Image.fromarray(figura("rect").astype(np.uint8)).save(t / "mal.png")
        assert A.main(["--ref", str(t / "ref.png"), "--render", f"frente={t / 'ok.png'}", "--salida", str(t / "a")]) == 0
        d = json.loads((t / "a" / "auditoria.json").read_text(encoding="utf-8"))
        assert d["decision"] == "PASS" and (t / "a" / "comparacion.png").exists()
        assert A.main(["--ref", str(t / "ref.png"), "--render", f"frente={t / 'mal.png'}", "--salida", str(t / "b")]) == 1
        assert A.main(["--ref", str(t / "no_existe.png"), "--render", f"frente={t / 'ok.png'}", "--salida", str(t / "c")]) == 2
        assert A.main(["--ref", str(t / "ref.png"), "--salida", str(t / "d")]) == 2      # sin candidato
        assert A.main(["--ref", str(t / "ref.png"), "--recorte", "0.5,0,0.2,1", "--render",
                       f"frente={t / 'ok.png'}", "--salida", str(t / "e")]) == 2


# ---------------------------------------------------------------- matriz real del repo
def test_matriz_real_aprobados_pasan_y_cruces_fallan():
    hojas = ["manzana", "lata", "taza", "vaso", "vaso_cafe"]
    vistas = {h: A.vistas_de_hoja(RAIZ / "assets" / h / "final.png") for h in hojas}
    malos = []
    for nombre, (ref, rc) in {"manzana": MANZANA, "lata": LATA}.items():
        rgb, m, _ = M.cargar_con_mascara(RAIZ / ref, rc)
        for h in hojas:
            r = A.auditar(rgb, m, vistas[h], U)
            if (r["decision"] == "PASS") != (h == nombre):
                malos.append((nombre, h, r["decision"], r["fallas"]))
    assert not malos, malos


def test_manzana_aprobada_no_es_peor_que_si_misma():
    rgb, m, _ = M.cargar_con_mascara(RAIZ / MANZANA[0], MANZANA[1])
    v = A.vistas_de_hoja(RAIZ / "assets" / "manzana" / "final.png")
    r = A.auditar(rgb, m, v, U, aprobado=v)
    assert r["no_peor_que_aprobado"] and not r["supera_aprobado"] and r["decision"] == "PASS"


# ---------------------------------------------------------------- calibración
def test_umbral_optimo_separa_y_deja_margen():
    r = C.umbral_optimo([0.1, 0.2, 0.3], [0.5, 0.6], "max")
    assert r["separa"] and 0.3 < r["umbral"] < 0.5
    r = C.umbral_optimo([0.9, 0.85], [0.6, 0.7], "min")
    assert r["separa"] and 0.7 < r["umbral"] < 0.85


def test_umbral_optimo_reporta_si_no_separa():
    r = C.umbral_optimo([0.1, 0.5, 0.9], [0.2, 0.6, 0.8], "max")
    assert not r["separa"] and r["j"] < 1


def test_calibracion_con_pocos_pares_sigue_provisional():
    pares = json.loads((RAIZ / "kb" / "pares_auditoria.json").read_text(encoding="utf-8"))["pares"]
    cal = C.calibrar(pares)
    assert not cal["suficiente"] and not cal["errores_conjunto"]
    with tempfile.TemporaryDirectory() as t:
        ruta = Path(t) / "u.json"
        ruta.write_text(A.UMBRALES_RUTA.read_text(encoding="utf-8"), encoding="utf-8")
        spec = C.escribir(cal, ruta)
        assert spec["calibrado"] is False and "PROVISIONAL" in spec["nota"]


def test_umbrales_declaran_todas_las_medidas_que_vetan():
    assert set(A.VETO) <= set(U["umbrales"]), set(A.VETO) - set(U["umbrales"])
    for k, r in U["umbrales"].items():
        assert ("min" in r) != ("max" in r), k


# ---------------------------------------------------------------- estado de la corrida
def test_estado_de_la_corrida_lo_decide_la_auditoria():
    import crear_asset as CA
    ok, mal = {"decision": "PASS"}, {"decision": "FAIL"}
    assert CA.estado_final(True, ok, []) == "APROBADO_POR_AUDITORIA"
    assert CA.estado_final(True, mal, []) == "AUDITORIA_FALLIDA"
    assert CA.estado_final(False, ok, []) == "VERIFICACION_FALLIDA"
    assert CA.estado_final(True, ok, [{"capacidad": "dedos"}]) == "FALTANTES"      # silueta OK no basta
    assert CA.ESTADOS_SALIDA["APROBADO_POR_AUDITORIA"] == 0 and CA.ESTADOS_SALIDA["AUDITORIA_FALLIDA"] == 3


def test_auditar_corrida_error_de_entrada_es_fail():
    import crear_asset as CA
    with tempfile.TemporaryDirectory() as t:
        r = CA.auditar_corrida(Path(t) / "no_hay.png", None, Path(t) / "tampoco.png", "nada", Path(t) / "a")
    assert r["decision"] == "FAIL" and r["fallas"] == ["entrada"]
