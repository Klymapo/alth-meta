"""Revisión y publicación (T4), sin Blender: filas de medidas, hoja de revisión y memoria de 4 vistas.

    python3 -m pytest tests/test_publicar.py
"""
import csv
import json
import sys
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import hoja_revision as hr  # noqa: E402
import publicar as pub  # noqa: E402
import reconocer as rec  # noqa: E402

RECETA = {"nombre": "manzana", "categoria": "de_mano", "k": 2.0,
          "medidas_mm": {"ancho": 8.51, "alto": 9.62, "dadas": ["ancho"]},
          "origen": {"imagen": "refs/infografias/objeto-01-manzana.png", "recorte": [0.52, 0.1, 1.0, 1.0]}}


def test_filas_medidas_solo_lo_que_dio_el_usuario():
    f = pub.filas_medidas(RECETA, {"ancho": 8.525, "alto": 9.358}, 0.05316, "2026-10-01")
    assert len(f) == 1 and f[0]["medida"] == "ancho" and f[0]["real_mm"] == "80"
    assert f[0]["alth_mm"] == "8.53" and f[0]["k_observado"] == "2.00" and f[0]["aprobado"] == "si"


def test_reemplazar_filas_no_duplica(tmp_path):
    ruta = tmp_path / "m.csv"
    ruta.write_text((RAIZ / "data" / "medidas.csv").read_text(encoding="utf-8"), encoding="utf-8")
    nuevas = pub.filas_medidas(RECETA, {"ancho": 8.525}, 0.05316, "2026-10-01")
    pub.reemplazar_filas("manzana", nuevas, ruta)
    pub.reemplazar_filas("manzana", nuevas, ruta)
    filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    assert [f["medida"] for f in filas if f["asset"] == "manzana"] == ["ancho"]
    assert len([f for f in filas if f["asset"] == "lata"]) == 2           # lo demás no se toca


def test_hoja_revision(tmp_path):
    (tmp_path / "receta.json").write_text(json.dumps(RECETA), encoding="utf-8")
    hoja = RAIZ / "assets" / "taza" / "final.png"                          # cualquier hoja 2x2 sirve
    (tmp_path / "resumen.json").write_text(json.dumps({"final": {"hoja": str(hoja), "iou": 0.88}}), encoding="utf-8")
    out = hr.componer(tmp_path, tmp_path / "revision.png")
    im = Image.open(out)
    assert im.width == 3 * hr.PANEL and im.height > hr.PANEL


def test_memoria_de_cuatro_vistas():
    memoria = rec.cargar_huellas()
    for h in memoria["huellas"]:
        assert set(h["vistas"]) == {"frente", "lateral", "espalda", "tres_cuartos"}, h["asset"]
        assert h["vistas"]["frente"]["forma"] == h["forma"]
    # la lateral de la taza (asa de perfil) se reconoce por su propia vista
    f = rec.reconocer(RAIZ / "assets/taza/final.png", "algo", None, None, rec.VISTAS_HOJA["lateral"], huellas=memoria)
    assert f["parecidos"][0]["nombre"] == "taza" and f["parecidos"][0]["vista"] == "lateral"


def _corrida(tmp_path, hoja, verif_ok=True):
    """Corrida falsa de crear_asset (sin Blender) con la hoja indicada como versión final."""
    final = tmp_path / "final"
    final.mkdir(parents=True)
    (final / "resultado.json").write_text(json.dumps({"verificacion": {"checks": [
        {"check": c, "ok": verif_ok} for c in ("paleta", "flotantes", "apoyo")]}}), encoding="utf-8")
    import shutil
    shutil.copyfile(hoja, final / "hoja.png")
    (tmp_path / "receta.json").write_text(json.dumps(dict(RECETA, tris_max=300)), encoding="utf-8")
    (tmp_path / "resumen.json").write_text(json.dumps({
        "imagen": str(RAIZ / RECETA["origen"]["imagen"]), "recorte": RECETA["origen"]["recorte"], "segundos": 60,
        "final": {"hoja": str(final / "hoja.png"), "dimensiones_ok": True, "tris": 200,
                  "dif_dimensiones": {"ancho": 0.0}}}), encoding="utf-8")
    return tmp_path


def test_aceptacion_exige_auditoria_visual(tmp_path):
    import aceptacion as ac
    ok = ac.evaluar(_corrida(tmp_path / "a", RAIZ / "assets" / "manzana" / "final.png"), None)
    assert ok["criterios"]["auditoria_visual"] and ok["aceptado"]
    # contra la manzana aprobada, la misma manzana no la supera: no se acepta como reemplazo
    igual = ac.evaluar(_corrida(tmp_path / "a2", RAIZ / "assets" / "manzana" / "final.png"), RAIZ / "assets" / "manzana")
    assert not igual["criterios"]["supera_aprobado"] and not igual["aceptado"]
    mal = ac.evaluar(_corrida(tmp_path / "b", RAIZ / "assets" / "taza" / "final.png"), RAIZ / "assets" / "manzana")
    assert not mal["criterios"]["auditoria_visual"] and not mal["aceptado"]


def test_publicar_no_toca_assets_si_la_auditoria_falla(tmp_path, monkeypatch):
    """Gate de publicación sin Blender: construir 'pasa' la verificación pero la hoja es de otro objeto."""
    import construir_receta as C
    hoja = RAIZ / "assets" / "taza" / "final.png"
    carpeta = _corrida(tmp_path / "c", hoja)

    def construir_falso(receta, salida, modo="iteracion", exportar=None, ref=None):
        Path(exportar).mkdir(parents=True, exist_ok=True)
        (Path(exportar) / "manzana.glb").write_bytes(b"glb falso")
        return {"ok": True, "hoja": str(hoja), "dif_dimensiones": {}, "verificacion_ok": True, "iou": 0.0}
    monkeypatch.setattr(C, "construir", construir_falso)
    antes = {p: p.stat().st_mtime_ns for p in (RAIZ / "assets" / "manzana").iterdir()}
    try:
        pub.publicar(carpeta, issue=0)
    except pub.PublicacionRechazada as e:
        assert "auditoría visual" in str(e)
    else:
        raise AssertionError("debió rechazar la publicación")
    assert {p: p.stat().st_mtime_ns for p in (RAIZ / "assets" / "manzana").iterdir()} == antes


def test_publicar_no_escribe_en_la_carpeta_de_theo(tmp_path):
    carpeta = _corrida(tmp_path / "d", RAIZ / "assets" / "manzana" / "final.png")
    (carpeta / "receta.json").write_text(json.dumps(dict(RECETA, nombre="joven_rubio")), encoding="utf-8")
    try:
        pub.publicar(carpeta, issue=0)
    except pub.PublicacionRechazada as e:
        assert "protegido" in str(e)
    else:
        raise AssertionError("debió negarse a publicar en assets/joven_rubio")
