"""Pruebas del reconocimiento SOLO con código y del registro de capacidades (sin Blender, sin red, sin IA).

    python3 -m pytest tests/test_reconocer.py

Dos tipos de prueba:
  - figuras sintéticas dibujadas aquí (cada regla por separado, resultado conocido de antemano);
  - imágenes reales del repo (refs/ y assets/*/final.png) para que una mejora no rompa lo que ya funciona.
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import capacidades as cap  # noqa: E402
import reconocer as rec  # noqa: E402

VOCAB = rec.cargar_vocab()
SPEC = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))
FONDO = (227, 226, 233)        # fondo de revisión ALTH
SIN_MEMORIA = {"huellas": []}


# ---------------------------------------------------------------- utilidades
def lienzo(w=400, h=400):
    im = Image.new("RGB", (w, h), FONDO)
    return im, ImageDraw.Draw(im)


def guardar(im, d: Path, nombre="img.png") -> Path:
    p = Path(d) / nombre
    im.save(p)
    return p


def ficha_de(im, nombre="cosa", tamano=None, tipo=None, huellas=SIN_MEMORIA):
    with tempfile.TemporaryDirectory() as d:
        return rec.reconocer(guardar(im, d), nombre, tamano, tipo, huellas=huellas)


def ids(ficha):
    return {c["id"] for c in ficha["capacidades"]}


def ficha_minima(capacidades, tipo="objeto"):
    """Ficha válida mínima para probar el registro sin pasar por una imagen."""
    return {"tipo": tipo, "nombre": "prueba", "capacidades": [{"id": c, "confianza": 0.9, "motivo": "prueba"}
                                                               for c in capacidades],
            "capacidades_nuevas": [], "tamano_real_mm": {"alto": None, "ancho": None, "fondo": None},
            "fuente_tamano": "desconocido", "confianza": 1.0}


# ---------------------------------------------------------------- separación figura / fondo
def test_figura_clara_casi_del_color_del_fondo_no_se_pierde():
    im, dr = lienzo()
    dr.rectangle((140, 100, 260, 300), fill=(248, 240, 230))        # crema, ΔE≈10 contra el fondo
    fig, sep = rec.separar_figura(np.asarray(im, dtype=np.float32))
    assert sep["componentes"] == 1 and fig.sum() > 0.9 * 120 * 200


def test_sombra_suave_se_quita_y_objeto_gris_nitido_se_queda():
    im, dr = lienzo()
    sombra = Image.new("L", im.size, 0)
    ImageDraw.Draw(sombra).ellipse((90, 270, 330, 330), fill=150)
    sombra = sombra.filter(ImageFilter.GaussianBlur(14))
    oscuro = Image.new("RGB", im.size, (120, 119, 125))
    im = Image.composite(oscuro, im, sombra)
    dr = ImageDraw.Draw(im)
    dr.ellipse((140, 120, 260, 290), fill=(168, 69, 59))            # cuerpo rojo
    rgb = np.asarray(im, dtype=np.float32)
    fig, sep = rec.separar_figura(rgb)
    assert sep["sombra_quitada"] > 0.05
    filas = np.where(fig.any(1))[0]
    assert filas[-1] <= 295                                          # la sombra de abajo ya no cuenta

    im2, dr2 = lienzo()
    dr2.rectangle((150, 200, 250, 300), fill=(150, 152, 158))       # bloque gris de borde nítido (metal)
    fig2, sep2 = rec.separar_figura(np.asarray(im2, dtype=np.float32))
    assert fig2.sum() > 0.95 * 100 * 100 and sep2["sombra_quitada"] == 0


# ---------------------------------------------------------------- reglas de forma
def test_disco_simetrico_es_torno():
    im, dr = lienzo()
    dr.ellipse((120, 110, 280, 290), fill=(168, 69, 59))
    f = ficha_de(im)
    assert {"torno", "simetria_bilateral"} <= ids(f) and "anillo" not in ids(f)


def test_taza_con_asa_tiene_hueco_y_es_anillo():
    im, dr = lienzo()
    dr.rectangle((110, 120, 250, 300), fill=(240, 228, 210))
    dr.ellipse((230, 160, 320, 260), fill=(240, 228, 210))
    dr.ellipse((255, 185, 295, 235), fill=FONDO)                      # el hueco del asa
    f = ficha_de(im)
    assert "anillo" in ids(f) and f["medidas"]["silueta"]["huecos"] == 1


def test_palito_arriba_es_prisma():
    im, dr = lienzo()
    dr.ellipse((120, 150, 280, 310), fill=(168, 69, 59))
    dr.rectangle((193, 80, 207, 160), fill=(105, 71, 45))           # tallo delgado y largo
    f = ficha_de(im)
    assert "prisma" in ids(f)


def _mano(dr, piel=(250, 200, 160)):
    dr.rounded_rectangle((130, 200, 270, 340), 20, fill=piel)       # palma
    for x in (132, 167, 202, 237):                                  # 4 dedos con huecos entre ellos
        dr.rounded_rectangle((x, 70, x + 28, 215), 10, fill=piel)
    dr.rounded_rectangle((60, 230, 140, 262), 12, fill=piel)        # pulgar


def test_mano_abierta_tiene_dedos_y_no_tallos_ni_hojas():
    im, dr = lienzo()
    _mano(dr)
    f = ficha_de(im, nombre="cosa")                                   # nombre neutro: solo cuenta la medición
    assert "dedos" in ids(f) and f["medidas"]["piel_objeto"]["huecos_dedos"] >= 2
    assert not ({"prisma", "hoja"} & ids(f))


def test_puno_cerrado_no_tiene_dedos():
    im, dr = lienzo()
    dr.rounded_rectangle((130, 150, 270, 320), 30, fill=(250, 200, 160))
    f = ficha_de(im, nombre="cosa")
    assert "dedos" not in ids(f)


def test_sin_figura_es_error():
    im, _ = lienzo()
    with tempfile.TemporaryDirectory() as d:
        try:
            rec.reconocer(guardar(im, d), "nada", huellas=SIN_MEMORIA)
        except ValueError as e:
            assert "figura" in str(e)
            return
    raise AssertionError("debió fallar")


def test_infografia_con_muchas_manchas_baja_la_confianza():
    im, dr = lienzo(600, 400)
    dr.ellipse((350, 100, 550, 300), fill=(168, 69, 59))
    for i in range(8):
        dr.rectangle((20, 20 + 45 * i, 60 + 25 * i, 50 + 45 * i), fill=(40, 40, 60))
    f = ficha_de(im)
    assert f["confianza"] < 1 and any("recorte" in a for a in f["_meta"]["avisos"])


# ---------------------------------------------------------------- color
def test_lab_y_paleta():
    blanco = rec._srgb_a_lab(np.array([255.0, 255, 255]))
    assert abs(blanco[0] - 100) < 0.1 and abs(blanco[1]) < 0.1
    paleta = rec.cargar_paleta(SPEC)
    assert any(h == "#B08A62" for _, h, _ in paleta)                # carton_kraft viene de paleta_notas
    assert not any(f == "fondo_revision" for f, _, _ in paleta)


def test_colores_dominantes_se_ajustan_a_la_paleta():
    im, dr = lienzo()
    dr.ellipse((100, 100, 300, 300), fill=(168, 69, 59))            # #A8453B, rojo_calido
    f = ficha_de(im)
    top = f["colores_dominantes"][0]
    assert top["paleta"] == "#A8453B" and top["delta_e"] < 3


def test_distancia_color():
    a = [[50, 40, 25, 1.0]]
    assert rec.distancia_color(a, a) == 0
    assert rec.distancia_color(a, [[90, 0, 0, 1.0]]) > 0.9
    assert rec.distancia_color(a, []) == 1.0


# ---------------------------------------------------------------- nombre (lo que el código no ve)
def test_capacidades_y_tipo_por_nombre():
    caps = rec.capacidades_por_nombre("Vaso de VIDRIO con agua", VOCAB)
    assert {"transparencia_vidrio", "liquido", "torno"} <= set(caps)
    assert "material_metal" in rec.capacidades_por_nombre("lata de atún", VOCAB)
    assert rec.capacidades_por_nombre("manzana", VOCAB).keys() == {"torno"}
    assert rec.tipo_por_nombre("perro corgi", VOCAB) == "animal"
    assert rec.tipo_por_nombre("Theo", VOCAB) == "personaje"
    assert rec.tipo_por_nombre("manzana", VOCAB) is None
    assert rec.nombre_id("Taza de Café ") == "taza_de_cafe"


def test_metal_no_se_deduce_del_color():
    im, dr = lienzo()
    dr.ellipse((120, 110, 280, 290), fill=(183, 186, 190))          # gris metálico de la paleta
    assert "material_metal" not in ids(ficha_de(im, nombre="cosa"))
    assert "material_metal" in ids(ficha_de(im, nombre="lata"))


def test_no_medible_lista_lo_que_falta():
    im, dr = lienzo()
    dr.ellipse((120, 110, 280, 290), fill=(168, 69, 59))
    f = ficha_de(im, nombre="cosa")
    assert "transparencia_vidrio" in f["no_medible"] and "torno" not in f["no_medible"]
    f2 = ficha_de(im, nombre="botella de vidrio")
    assert "transparencia_vidrio" not in f2["no_medible"] and "transparencia_vidrio" in ids(f2)


# ---------------------------------------------------------------- tamaño y escala
def test_parsear_tamano():
    assert rec.parsear_tamano("8cm") == {"mayor": 80.0}
    assert rec.parsear_tamano("80") == {"mayor": 80.0}
    assert rec.parsear_tamano("10x8 cm") == {"alto": 100.0, "ancho": 80.0}
    assert rec.parsear_tamano("alto=10cm, ancho=8") == {"alto": 100.0, "ancho": 80.0}
    assert rec.parsear_tamano("1.8 m") == {"mayor": 1800.0}
    assert rec.parsear_tamano("") == {} and rec.parsear_tamano(None) == {}
    for malo in ("grande", "0cm"):
        try:
            rec.parsear_tamano(malo)
        except ValueError:
            continue
        raise AssertionError(malo)


def test_completar_tamano_con_la_proporcion_de_la_silueta():
    sil = {"aspecto_alto_ancho": 2.0}
    assert rec.completar_tamano({"mayor": 100}, sil) == {"alto": 100, "ancho": 50, "fondo": None}
    assert rec.completar_tamano({"mayor": 100}, {"aspecto_alto_ancho": 0.5})["alto"] == 50
    assert rec.completar_tamano({"ancho": 40}, sil)["alto"] == 80


def test_escala_provisional_y_de_spec():
    s0, fuente = rec.escala_s0({})
    assert abs(s0 - 95.7 / 1800) < 1e-9 and "PROVISIONAL" in fuente
    assert rec.escala_s0({"escala_alpha": {"s0": 0.05}}) == (0.05, "spec/alth_spec.json → escala_alpha.s0")


def test_factor_k_por_categoria():
    sil = {"aspecto_alto_ancho": 1.0}
    assert rec.factor_k("objeto", {"alto": 80}, sil, SPEC)[0] == 2.0           # de mano
    assert rec.factor_k("objeto", {"alto": 400}, sil, SPEC)[0] == 1.3          # portátil
    assert rec.factor_k("objeto", {"alto": 900}, {"aspecto_alto_ancho": 6}, SPEC)[1] == "largo_en_mano"
    assert rec.factor_k("personaje", {"alto": 1800}, sil, SPEC)[0] == 1.0
    assert rec.factor_k("vehiculo", {"alto": 1500}, sil, SPEC)[0] == 0.9


def test_manzana_de_8cm_queda_en_mm_alth():
    im, dr = lienzo()
    dr.ellipse((120, 120, 280, 280), fill=(168, 69, 59))
    f = ficha_de(im, nombre="cosa", tamano="8cm")
    assert f["fuente_tamano"] == "usuario" and f["escala"]["categoria"] == "de_mano"
    esperado = 80 * (95.7 / 1800) * 2.0
    assert abs(f["tamano_alth_mm"]["alto"] - round(esperado, 2)) < 0.15


# ---------------------------------------------------------------- memoria
def _asset_falso(d: Path, nombre: str, color, medidas):
    carpeta = Path(d) / nombre
    carpeta.mkdir()
    hoja = Image.new("RGB", (800, 800), FONDO)
    ImageDraw.Draw(hoja).ellipse((100, 120, 300, 330), fill=color)    # cuadrante de frente (arriba-izq.)
    hoja.save(carpeta / "final.png")
    (carpeta / "spec.json").write_text(json.dumps({"nombre": nombre, "categoria": "de_mano",
                                                   "medidas_reales_mm": medidas}))
    return carpeta


def test_memorizar_y_reconocer_lo_parecido_y_su_tamano():
    with tempfile.TemporaryDirectory() as d:
        huellas = Path(d) / "huellas.json"
        rec.memorizar(_asset_falso(d, "tomate", (168, 69, 59), {"diametro": 70, "alto": 60}), huellas)
        rec.memorizar(_asset_falso(d, "limon", (220, 197, 114), {"diametro": 60, "alto": 70}), huellas)
        memoria = rec.cargar_huellas(huellas)
        assert len(memoria["huellas"]) == 2
        im, dr = lienzo()
        dr.ellipse((110, 110, 290, 300), fill=(168, 69, 59))
        f = ficha_de(im, nombre="tomate", huellas=memoria)              # sin tamaño: lo toma de la memoria
        assert f["parecidos"][0]["nombre"] == "tomate" and f["parecidos"][0]["similitud"] > 0.5
        assert f["fuente_tamano"] == "memoria" and f["tamano_real_mm"]["alto"] == 60
        f2 = ficha_de(im, nombre="otra cosa", huellas=memoria)
        assert f2["fuente_tamano"] == "desconocido" and f2["parecidos"][0]["nombre"] == "tomate"
        # memorizar el mismo asset otra vez reemplaza, no duplica
        rec.memorizar(Path(d) / "tomate", huellas)
        assert len(rec.cargar_huellas(huellas)["huellas"]) == 2


def test_memorizar_exige_final_png():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "x").mkdir()
        try:
            rec.memorizar(Path(d) / "x", Path(d) / "h.json")
        except ValueError as e:
            assert "aprobados" in str(e)
            return
    raise AssertionError("debió fallar")


# ---------------------------------------------------------------- imágenes reales del repo (regresión)
def _real(ruta, nombre, tamano=None, recorte=None):
    return rec.reconocer(RAIZ / ruta, nombre, tamano, None, recorte, huellas=SIN_MEMORIA)


def test_real_manzana_aprobada():
    f = _real("assets/manzana/final.png", "manzana", "8cm", (0, 0.03, 0.5, 0.5))
    assert f["tipo"] == "objeto" and {"torno", "hoja"} <= ids(f)
    assert not ({"dedos", "cuerpo_humanoide", "anillo"} & ids(f))


def test_real_taza_aprobada_tiene_asa():
    f = _real("assets/taza/final.png", "taza", None, (0, 0.03, 0.5, 0.5))
    assert "anillo" in ids(f) and f["medidas"]["silueta"]["huecos"] >= 1


def test_real_theo_es_personaje_sin_dedos_visibles():
    f = _real("refs/personajes/joven-rubio.jpg", "Theo", "180cm")
    assert f["tipo"] == "personaje" and f["fuente_tipo"].startswith("medido")
    assert {"cuerpo_humanoide", "cabeza_cara", "calzado", "rig_esqueleto"} <= ids(f)
    assert f["medidas"]["personaje"]["pelo"] is True
    # En esta referencia las manos están en los bolsillos: la medición no ve dedos (0 huecos)…
    assert f["medidas"]["personaje"]["huecos_dedos"] == 0
    # …pero la decisión de diseño del usuario los exige igual.
    dedos = next(c for c in f["capacidades"] if c["id"] == "dedos")
    assert dedos["confianza"] == 1.0 and "decisión del usuario" in dedos["motivo"]
    assert abs(f["tamano_alth_mm"]["alto"] - 95.7) < 0.1


def test_real_alastor_lentes_y_abrigo():
    f = _real("refs/pendientes/alastor-1790548802009.jpg", "Alastor", "175cm")
    assert f["tipo"] == "personaje" and f["fuente_tipo"].startswith("medido")
    assert {"accesorio_rigido", "ropa_holgada_tela", "cabeza_cara", "dedos"} <= ids(f)
    assert f["medidas"]["personaje"]["huecos_dedos"] == 0


def test_real_mano_abierta_tiene_cuatro_huecos():
    f = _real("refs/infografias/mano-con-regla.jpg", "cosa", "19cm", (0, 0, 0.69, 1))
    assert "dedos" in ids(f) and f["medidas"]["piel_objeto"]["huecos_dedos"] >= 3


def test_real_memoria_reconoce_los_assets_aprobados():
    memoria = rec.cargar_huellas()
    nombres = {h["nombre"] for h in memoria["huellas"]}
    assert {"manzana", "lata", "taza", "vaso", "vaso_cafe"} <= nombres
    for h in memoria["huellas"]:
        assert (RAIZ / h["evidencia"]).exists()
    f = rec.reconocer(RAIZ / "assets/taza/final.png", "algo", None, None, (0, 0.03, 0.5, 0.5), huellas=memoria)
    assert f["parecidos"][0]["nombre"] == "taza" and f["parecidos"][0]["similitud"] > 0.9


# ---------------------------------------------------------------- validación de la ficha
def test_validar_ficha_errores():
    for cambio in ({"tipo": "dragon"}, {"nombre": "Con Espacios"}, {"fuente_tamano": "adivinado"},
                   {"capacidades": [{"id": "telepatia", "confianza": 0.5}]},
                   {"tamano_real_mm": {"alto": -3}}, {"confianza": 1.5}):
        f = {**ficha_minima(["torno"]), **cambio}
        try:
            rec.validar_ficha(f, VOCAB)
        except ValueError:
            continue
        raise AssertionError(cambio)
    assert rec.validar_ficha(ficha_minima(["torno"]), VOCAB)


# ---------------------------------------------------------------- registro de capacidades
def test_registro_real_es_consistente():
    reg = cap.cargar_registro()
    for cid, entrada in reg["capacidades"].items():
        assert cid in VOCAB["capacidades"], f"{cid} no está en el vocabulario"
        estado, avisos = cap.estado_efectivo(entrada)
        assert estado == entrada["estado"] and not avisos, f"{cid}: {avisos}"
        if entrada["estado"] == "fallida":
            assert entrada["motivo"] and entrada.get("intentos_fallidos")


def test_manzana_se_puede_construir_directo():
    r = cap.comparar(ficha_minima(["torno", "prisma", "hoja"]), cap.cargar_registro(), VOCAB)
    assert r["listo"] and r["dominadas"] == ["torno", "prisma", "hoja"] and r["brechas"] == []


def test_dedos_es_brecha_fallida_y_no_repite_lo_que_fallo():
    r = cap.comparar(ficha_minima(["cuerpo_humanoide", "dedos"], "personaje"), cap.cargar_registro(), VOCAB)
    assert not r["listo"]
    dedos = next(b for b in r["brechas"] if b["id"] == "dedos")
    assert dedos["estado"] == "fallida" and len(dedos["no_repetir"]) == 3
    assert any(b["id"] == "cuerpo_humanoide" and b["estado"] == "parcial" for b in r["brechas"])


def test_ficha_real_de_alastor_contra_el_registro():
    f = _real("refs/pendientes/alastor-1790548802009.jpg", "Alastor", "175cm")
    r = cap.comparar(f, cap.cargar_registro(), VOCAB)
    estados = {b["id"]: b["estado"] for b in r["brechas"]}
    assert estados["cuerpo_humanoide"] == "parcial" and estados["ropa_holgada_tela"] == "desconocida"
    assert not r["listo"]


def test_capacidad_nunca_vista_es_desconocida():
    r = cap.comparar(ficha_minima(["liquido", "torno"]), cap.cargar_registro(), VOCAB)
    assert r["desconocidas"] == ["liquido"] and {b["id"] for b in r["brechas"]} == {"liquido"}


def test_dominada_sin_evidencia_o_con_evidencia_inexistente_se_degrada():
    assert cap.estado_efectivo({"estado": "dominada"})[0] == "parcial"
    estado, avisos = cap.estado_efectivo({"estado": "dominada", "evidencia": ["assets/no_existe/final.png"]})
    assert estado == "parcial" and "no existe" in avisos[0]


def test_aprender_exige_evidencia_real_y_motivo():
    reg = {"capacidades": {}}
    for kwargs in ({"estado": "dominada", "evidencia": []},
                   {"estado": "dominada", "evidencia": ["assets/no_existe.png"]},
                   {"estado": "fallida", "motivo": "  "}):
        try:
            cap.aprender(reg, "torno", motivo=kwargs.pop("motivo", "x"), vocab=VOCAB, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"debió fallar: {kwargs}")
    try:
        cap.aprender(reg, "engranes", "dominada", "x", ["spec/capacidades_vocab.json"], vocab=VOCAB)
    except ValueError as e:
        assert "capacidades_vocab" in str(e)
    else:
        raise AssertionError("debió exigir alta en el vocabulario")


def test_aprender_dominada_y_fallida_actualizan_el_registro():
    reg = {"capacidades": {}}
    cap.aprender(reg, "caja", "dominada", "Librero aprobado", ["spec/capacidades_vocab.json"], vocab=VOCAB)
    assert reg["capacidades"]["caja"]["estado"] == "dominada"
    cap.aprender(reg, "dedos", "fallida", "Método X rechazado", None, "método X", vocab=VOCAB)
    cap.aprender(reg, "dedos", "fallida", "Método Y rechazado", None, "método Y", vocab=VOCAB)
    assert [t["tecnica"] for t in reg["capacidades"]["dedos"]["intentos_fallidos"]] == ["método X", "método Y"]
    r = cap.comparar(ficha_minima(["dedos"]), reg, VOCAB)
    assert r["brechas"][0]["no_repetir"] == ["método X", "método Y"]


# ---------------------------------------------------------------- línea de comandos
def test_cli_reconocer_validar_y_capacidades():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        im, dr = lienzo()
        dr.ellipse((120, 110, 280, 290), fill=(168, 69, 59))
        img = guardar(im, d)
        salida = d / "ficha.json"
        assert rec.main(["reconocer", str(img), "--nombre", "tomate", "--tamano", "7cm", "--salida", str(salida)]) == 0
        assert rec.main(["validar", str(salida)]) == 0
        assert rec.main(["reconocer", str(d / "no_existe.png"), "--nombre", "x"]) == 2
        assert rec.main(["reconocer", str(img), "--nombre", "x", "--tamano", "grande",
                         "--salida", str(d / "otra.json")]) == 2
        con_dedos = d / "dedos.json"
        con_dedos.write_text(json.dumps(ficha_minima(["dedos"])))
        assert cap.main(["comparar", str(salida)]) in (0, 3)
        assert cap.main(["comparar", str(con_dedos)]) == 3
        reg = d / "reg.json"
        assert cap.main(["aprender", "caja", "--estado", "dominada", "--evidencia", "spec/capacidades_vocab.json",
                         "--motivo", "prueba", "--registro", str(reg)]) == 0
        assert cap.main(["aprender", "caja", "--estado", "dominada", "--registro", str(reg)]) == 2


def test_objeto_no_hereda_la_regla_de_dedos_de_personaje():
    im, dr = lienzo()
    dr.ellipse((120, 110, 280, 290), fill=(168, 69, 59))
    assert "dedos" not in ids(ficha_de(im, nombre="cosa"))


def test_ficha_de_theo_marca_dedos_como_brecha_fallida():
    f = _real("refs/personajes/joven-rubio.jpg", "Theo", "180cm")
    r = cap.comparar(f, cap.cargar_registro(), VOCAB)
    dedos = next(b for b in r["brechas"] if b["id"] == "dedos")
    assert dedos["estado"] == "fallida" and len(dedos["no_repetir"]) == 3
