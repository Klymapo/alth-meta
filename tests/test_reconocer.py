"""Pruebas del reconocimiento de imagen y del registro de capacidades (sin Blender, sin red, sin API).

    python3 -m pytest tests/test_reconocer.py
"""
import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "alth"))
sys.path.insert(0, str(RAIZ / "tools"))
import capacidades as cap  # noqa: E402
import reconocer as rec  # noqa: E402

VOCAB = rec.cargar_vocab()


def ficha_base(**cambios):
    f = {"tipo": "objeto", "nombre": "manzana_roja", "descripcion": "Una manzana roja con tallo y una hoja.",
         "partes": ["cuerpo", "tallo", "hoja"],
         "capacidades": [{"id": "torno", "motivo": "cuerpo redondo"}, {"id": "hoja", "motivo": "hoja en el tallo"}],
         "capacidades_nuevas": [], "tamano_real_mm": {"alto": 72, "ancho": 80, "fondo": 80},
         "fuente_tamano": "estimado", "colores_dominantes": ["#A8453B", "#5F6944"], "confianza": 0.9}
    f.update(cambios)
    return f


# ---------------------------------------------------------------- extracción
def test_extraer_json_con_cercas_y_texto():
    r = rec.extraer_json('Claro:\n```json\n{"a": {"b": "}"}, "c": 1}\n```\nlisto')
    assert r == {"a": {"b": "}"}, "c": 1}


def test_extraer_json_sin_json_o_incompleto():
    for malo in ("no hay nada", '{"a": 1'):
        try:
            rec.extraer_json(malo)
        except ValueError:
            continue
        raise AssertionError("debió fallar")


# ---------------------------------------------------------------- validación
def test_ficha_valida_se_normaliza():
    f, avisos = rec.validar_ficha(ficha_base(), VOCAB)
    assert [c["id"] for c in f["capacidades"]] == ["torno", "hoja"]
    assert f["colores_dominantes"] == ["#A8453B", "#5F6944"]
    assert avisos == []


def test_id_fuera_del_vocabulario_va_a_nuevas_y_no_a_capacidades():
    f, avisos = rec.validar_ficha(
        ficha_base(capacidades=[{"id": "torno"}, {"id": "soldadura_laser", "motivo": "x"}]), VOCAB)
    assert [c["id"] for c in f["capacidades"]] == ["torno"]
    assert [c["id"] for c in f["capacidades_nuevas"]] == ["soldadura_laser"]
    assert any("soldadura_laser" in a for a in avisos)


def test_errores_duros():
    casos = [ficha_base(tipo="dragon"), ficha_base(nombre="Con Espacios"), ficha_base(descripcion="  "),
             ficha_base(capacidades=[], capacidades_nuevas=[]),
             ficha_base(tamano_real_mm={"alto": -3, "ancho": None, "fondo": None}),
             ficha_base(confianza=1.5), ficha_base(fuente_tamano="adivinado"),
             ficha_base(tamano_real_mm="grande")]
    for caso in casos:
        try:
            rec.validar_ficha(caso, VOCAB)
        except ValueError:
            continue
        raise AssertionError(f"debió fallar: {caso}")


def test_correcciones_suaves_de_tamano_y_color():
    f, avisos = rec.validar_ficha(ficha_base(tamano_real_mm={"alto": None, "ancho": None, "fondo": None},
                                             fuente_tamano="visible", colores_dominantes=["rojo", "#ABCDEF"]), VOCAB)
    assert f["fuente_tamano"] == "desconocido"
    assert f["colores_dominantes"] == ["#ABCDEF"]
    f2, _ = rec.validar_ficha(ficha_base(fuente_tamano="desconocido"), VOCAB)
    assert f2["fuente_tamano"] == "estimado"


def test_capacidad_nueva_que_ya_existe_en_vocabulario_se_reubica():
    f, avisos = rec.validar_ficha(ficha_base(capacidades=[{"id": "torno"}],
                                             capacidades_nuevas=[{"id": "dedos", "motivo": "manos"}]), VOCAB)
    assert {c["id"] for c in f["capacidades"]} == {"torno", "dedos"} and f["capacidades_nuevas"] == []


def test_prompt_lista_todo_el_vocabulario():
    sistema, texto = rec.prompt_reconocimiento(VOCAB, "ojo con las manos")
    assert "JSON" in sistema
    for k in VOCAB["capacidades"]:
        assert f"- {k}:" in texto
    for t in VOCAB["tipos"]:
        assert t in texto
    assert "ojo con las manos" in texto


# ---------------------------------------------------------------- llamada al modelo (inyectada)
def _img(d: Path) -> Path:
    p = d / "ref.png"
    p.write_bytes(b"\x89PNG fake")
    return p


def test_solo_proveedores_con_vision():
    cadena = [{"nombre": "groq", "vision": False}, {"nombre": "gemini", "vision": True}]
    assert [c["nombre"] for c in rec.cadena_con_vision(cadena)] == ["gemini"]


def test_sin_proveedor_con_vision_se_detiene():
    with tempfile.TemporaryDirectory() as d:
        try:
            rec.reconocer(_img(Path(d)), [{"nombre": "groq", "vision": False}], VOCAB, llamar=lambda *a: ("", {}))
        except SystemExit as e:
            assert "paquete" in str(e)
            return
    raise AssertionError("debió detenerse")


def test_reconoce_y_agrega_metadatos():
    cfg = {"nombre": "gemini", "modelo": "m", "vision": True}
    with tempfile.TemporaryDirectory() as d:
        f = rec.reconocer(_img(Path(d)), [cfg], VOCAB, llamar=lambda *a: (json.dumps(ficha_base()), cfg))
    assert f["_meta"]["proveedor"] == "gemini" and len(f["_meta"]["imagen_sha256"]) == 64


def test_reintenta_una_vez_con_el_error_en_el_prompt():
    cfg = {"nombre": "gemini", "modelo": "m", "vision": True}
    pedidos = []

    def llamar(cadena, sistema, texto, imagenes, temp):
        pedidos.append(texto)
        return ("esto no es json" if len(pedidos) == 1 else json.dumps(ficha_base())), cfg

    with tempfile.TemporaryDirectory() as d:
        f = rec.reconocer(_img(Path(d)), [cfg], VOCAB, llamar=llamar)
    assert len(pedidos) == 2 and "no fue válida" in pedidos[1] and f["nombre"] == "manzana_roja"


def test_si_siempre_falla_no_inventa_nada():
    cfg = {"nombre": "gemini", "modelo": "m", "vision": True}
    with tempfile.TemporaryDirectory() as d:
        try:
            rec.reconocer(_img(Path(d)), [cfg], VOCAB, llamar=lambda *a: ("basura", cfg))
        except SystemExit as e:
            assert "ficha válida" in str(e)
            return
    raise AssertionError("debió detenerse")


# ---------------------------------------------------------------- registro de capacidades
def test_registro_real_es_consistente():
    """Guarda contra regresiones: todo 'dominada' del registro real trae evidencia que existe,
    y todo id del registro está en el vocabulario."""
    reg = cap.cargar_registro()
    for cid, entrada in reg["capacidades"].items():
        assert cid in VOCAB["capacidades"], f"{cid} no está en el vocabulario"
        estado, avisos = cap.estado_efectivo(entrada)
        assert estado == entrada["estado"] and not avisos, f"{cid}: {avisos}"
        if entrada["estado"] == "fallida":
            assert entrada["motivo"] and entrada.get("intentos_fallidos")


def test_manzana_se_puede_construir_directo():
    f, _ = rec.validar_ficha(ficha_base(capacidades=[{"id": "torno"}, {"id": "prisma"}, {"id": "hoja"}]), VOCAB)
    r = cap.comparar(f, cap.cargar_registro(), VOCAB)
    assert r["listo"] and r["dominadas"] == ["torno", "prisma", "hoja"] and r["brechas"] == []


def test_dedos_es_brecha_fallida_y_no_repite_lo_que_fallo():
    f, _ = rec.validar_ficha(ficha_base(tipo="personaje", nombre="theo",
                                        capacidades=[{"id": "cuerpo_humanoide"}, {"id": "dedos", "motivo": "manos con dedos"}]), VOCAB)
    r = cap.comparar(f, cap.cargar_registro(), VOCAB)
    assert not r["listo"]
    dedos = next(b for b in r["brechas"] if b["id"] == "dedos")
    assert dedos["estado"] == "fallida" and len(dedos["no_repetir"]) == 3
    assert dedos["necesidad"] == "manos con dedos"
    assert any(b["id"] == "cuerpo_humanoide" and b["estado"] == "parcial" for b in r["brechas"])


def test_capacidad_nunca_vista_es_desconocida_y_la_nueva_es_brecha():
    f, _ = rec.validar_ficha(ficha_base(capacidades=[{"id": "liquido"}, {"id": "torno"}],
                                        capacidades_nuevas=[{"id": "engranes", "motivo": "mecanismo"}]), VOCAB)
    r = cap.comparar(f, cap.cargar_registro(), VOCAB)
    assert r["desconocidas"] == ["liquido"] and r["nuevas"] == ["engranes"]
    assert {b["id"] for b in r["brechas"]} == {"liquido", "engranes"}


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
    f, _ = rec.validar_ficha(ficha_base(capacidades=[{"id": "dedos"}]), VOCAB)
    # el registro de esta prueba no tiene la evidencia real, pero 'fallida' no la necesita
    r = cap.comparar(f, reg, VOCAB)
    assert r["brechas"][0]["no_repetir"] == ["método X", "método Y"]


# ---------------------------------------------------------------- línea de comandos
def test_cli_comparar_codigos_de_salida_y_aprender_guarda_en_disco():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ok, _ = rec.validar_ficha(ficha_base(), VOCAB)
        con_dedos, _ = rec.validar_ficha(ficha_base(capacidades=[{"id": "dedos"}]), VOCAB)
        (d / "ok.json").write_text(json.dumps(ok))
        (d / "dedos.json").write_text(json.dumps(con_dedos))
        assert cap.main(["comparar", str(d / "ok.json")]) == 0
        assert cap.main(["comparar", str(d / "dedos.json")]) == 3
        reg = d / "reg.json"
        assert cap.main(["aprender", "caja", "--estado", "dominada", "--evidencia", "spec/capacidades_vocab.json",
                         "--motivo", "prueba", "--registro", str(reg)]) == 0
        assert json.loads(reg.read_text())["capacidades"]["caja"]["estado"] == "dominada"
        assert cap.main(["aprender", "caja", "--estado", "dominada", "--registro", str(reg)]) == 2


def test_cli_reconocer_validar_paquete_y_aplicar():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        img = _img(d)
        (d / "ficha.json").write_text(json.dumps(ficha_base()))
        assert rec.main(["validar", str(d / "ficha.json")]) == 0
        (d / "mala.json").write_text(json.dumps(ficha_base(tipo="dragon")))
        assert rec.main(["validar", str(d / "mala.json")]) == 2
        assert rec.main(["paquete", str(img), "--destino", str(d / "p.md")]) == 0
        assert "capacidades" in (d / "p.md").read_text()
        (d / "resp.md").write_text("Aquí va:\n```json\n" + json.dumps(ficha_base()) + "\n```")
        assert rec.main(["aplicar", str(d / "resp.md"), "--imagen", str(img), "--salida", str(d / "out.json")]) == 0
        salida = json.loads((d / "out.json").read_text())
        assert salida["_meta"]["proveedor"] == "manual" and salida["nombre"] == "manzana_roja"
