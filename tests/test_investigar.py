"""Investigación sin IA (T1): memoria, búsqueda con fixtures, BM25, extracción y RESEARCH_REQUIRED.

    python3 -m pytest tests/test_investigar.py

Sin red: una `RedFalsa` responde con los archivos de tests/fixtures/investigar/ (ver su README).
La corrida con red real y la prueba en Blender van en Actions.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import investigar as iv  # noqa: E402

FIX = RAIZ / "tests" / "fixtures" / "investigar"
AHORA = datetime.now(timezone.utc)
API = "https://docs.blender.org/api/5.2/"


class RedFalsa(iv.Red):
    def __init__(self, respuestas, token="t"):
        super().__init__(token=token)
        self.respuestas = respuestas

    def get(self, url, aceptar=None):
        codigo, cuerpo = self.respuestas.get(url, (0, ""))
        self.registro.append({"url": url, "codigo": codigo, "bytes": len(cuerpo)})
        return codigo, cuerpo


def leer(nombre):
    return (FIX / nombre).read_text(encoding="utf-8")


def red_completa():
    busqueda = leer("github_search.json")
    r = {API + "bmesh.ops.html": (200, leer("bmesh_ops.html")),
         API + "bpy.ops.mesh.html": (200, leer("bpy_ops_mesh.html")),
         API + "bpy_types_enum_items/object_modifier_type_items.html": (200, leer("modificadores.html")),
         "https://raw.githubusercontent.com/ejemplo/manos/abc123/tools/ejemplo_split.py": (200, leer("ejemplo_split.py")),
         "https://raw.githubusercontent.com/ejemplo/escaneo/def456/scan/ejemplo_weld.py": (200, leer("ejemplo_weld.py"))}

    class R(RedFalsa):
        def get(self, url, aceptar=None):
            if url.startswith("https://api.github.com/search/code"):
                self.registro.append({"url": url, "codigo": 200, "bytes": len(busqueda)})
                return 200, busqueda
            return super().get(url, aceptar)
    return R(r)


@pytest.fixture
def kb(tmp_path):
    reg = json.loads((RAIZ / "kb" / "capacidades.json").read_text(encoding="utf-8"))
    (tmp_path / "capacidades.json").write_text(json.dumps(reg), encoding="utf-8")
    return {"kb_indice": tmp_path / "investigacion.json", "kb_briefs": tmp_path / "briefs",
            "kb_capacidades": tmp_path / "capacidades.json"}


# ---------------------------------------------------------------- texto
def test_terminos_traduce_y_quita_vacias():
    t = iv.terminos("separar los dedos de la mano", "soldar vértices")
    assert t[:3] == ["separate", "split", "finger"] and "hand" in t and "weld" in t and "vertex" in t
    assert "los" not in t and "de" not in t
    assert iv.terminos("protegiendo la cara") == ["face"]


def test_bm25_prefiere_el_documento_con_los_terminos():
    bm = iv.BM25([["split", "edge", "disconnect"], ["merge", "vertex"], ["fingers", "split", "hand"]])
    assert bm.puntaje(2, ["finger", "hand"]) > bm.puntaje(0, ["finger", "hand"]) == 0


# ---------------------------------------------------------------- parsers
def test_parsear_sphinx():
    sec = iv.parsear_sphinx(leer("bmesh_ops.html"), "bmesh.ops")
    nombres = [s["nombre"] for s in sec]
    assert "bmesh.ops.bisect_plane" in nombres and len(sec) == 6
    b = sec[nombres.index("bmesh.ops.bisect_plane")]
    assert b["params"][:2] == ["geom", "dist"] and "bm" not in b["params"]
    assert "Bisects the mesh by a plane" in b["texto"]


def test_parsear_opdefines_real():
    sec = iv.parsear_opdefines(leer("bmesh_opdefines_v5.2.2.cc"))
    nombres = {s["nombre"] for s in sec}
    assert len(sec) == 83 and "bmesh.ops.join_triangles" in nombres
    rd = next(s for s in sec if s["nombre"] == "bmesh.ops.remove_doubles")
    assert rd["params"] == ["verts", "use_connected", "dist"]
    assert rd["tipos"] == {"verts": "elementos", "use_connected": "bool", "dist": "float"}
    assert "merges them together" in rd["texto"]


def test_parsear_enum_modificadores():
    sec = iv.parsear_enum(leer("modificadores.html"))
    assert [s["nombre"] for s in sec] == ["modificador:BOOLEAN", "modificador:DECIMATE", "modificador:WELD",
                                          "modificador:SOLIDIFY"]


def test_extraer_llamadas_con_parametros():
    ll = iv.extraer_llamadas(leer("ejemplo_split.py"))
    assert [x["tecnica"] for x in ll] == ["bmesh.ops.bisect_plane", "bmesh.ops.split_edges"]
    assert ll[0]["parametros"] == {"geom": "<expr>", "dist": 0.0001, "plane_co": (0.0, 0.0, 0.5),
                                   "plane_no": (1.0, 0.0, 0.0)}
    ll = iv.extraer_llamadas(leer("ejemplo_weld.py"))
    assert [x["tecnica"] for x in ll] == ["bmesh.ops.remove_doubles", "modificador:DECIMATE"]
    assert iv.extraer_llamadas("bmesh.ops.weld_verts(bm, targetmap=m") == [
        {"tecnica": "bmesh.ops.weld_verts", "parametros": {}, "linea": 1}]          # código roto: regex


def test_url_raw():
    assert iv.url_raw("https://github.com/a/b/blob/sha/x/y.py") == "https://raw.githubusercontent.com/a/b/sha/x/y.py"
    assert iv.url_raw("https://example.com/x") is None


# ---------------------------------------------------------------- buscar
def test_buscar_con_fixtures_escribe_brief_valido(kb):
    r = iv.buscar("dedos", "separar y cortar dedos de una mano tipo mitón", red_completa(), version="5.2.2",
                  ahora=AHORA, **kb)
    assert r["estado"] == "CANDIDATOS", r["gate"]
    brief = json.loads((RAIZ / r["ruta_brief"]).read_text() if not Path(r["ruta_brief"]).is_absolute()
                       else Path(r["ruta_brief"]).read_text())
    assert brief["estado"] == "unverified" and brief["status"] == "READY"
    assert brief["selected_technique"] in brief["techniques_found"]
    assert len(brief["sources"]) >= 2 and all(s["url"].startswith("https://") for s in brief["sources"])
    assert {s["source_type"] for s in brief["sources"]} <= {"official_docs", "community"}
    # el ejemplo publicado aporta parámetros concretos con su URL
    bis = next(t for t in brief["techniques"] if t["name"] == "bmesh.ops.bisect_plane")
    assert bis["parametros"]["plane_no"] == [1.0, 0.0, 0.0] or bis["parametros"]["plane_no"] == (1.0, 0.0, 0.0)
    assert bis["ejemplos"] == ["https://github.com/ejemplo/manos/blob/abc123/tools/ejemplo_split.py"]
    # booleano ya falló en dedos (kb/capacidades.json): no se repite; bpy.ops se descarta por regla ALTH
    rech = {t["name"]: t["reason"] for t in brief["techniques_rejected"]}
    assert "modificador:BOOLEAN" in rech and "fallida" in rech["modificador:BOOLEAN"]
    assert all(not n.startswith("bpy.ops") for n in brief["techniques_found"])
    assert len(brief["no_repetir"]) == 3
    indice = json.loads(kb["kb_indice"].read_text())
    assert indice["entradas"][0]["capacidad"] == "dedos"
    assert all(c["estado"] == "unverified" for c in indice["entradas"][0]["candidatos"])
    from copox.production.research_gate import validate_research
    assert validate_research(brief, "dedos", technique=brief["selected_technique"])["status"] == "READY"


def test_buscar_sin_red_es_research_required(kb):
    r = iv.buscar("dedos", "separar dedos", RedFalsa({}), version="5.2.2", ahora=AHORA, **kb)
    assert r["estado"] == "RESEARCH_REQUIRED" and "sin_red" in r["gate"]["reasons"]
    assert not kb["kb_indice"].exists() and not kb["kb_briefs"].exists()


def test_buscar_sin_hallazgos_es_research_required(kb):
    red = RedFalsa({API + "bmesh.ops.html": (200, leer("bmesh_ops.html"))})
    r = iv.buscar("texto_legible", "zzz qqq", red, version="5.2.2", ahora=AHORA, **kb)
    assert r["estado"] == "RESEARCH_REQUIRED" and not kb["kb_indice"].exists()


def test_respaldo_con_la_fuente_oficial_si_la_doc_no_responde(kb):
    url = iv.FUENTE_OPDEFINES[1].format(version="5.2.2")
    red = RedFalsa({url: (200, leer("bmesh_opdefines_v5.2.2.cc"))}, token=None)
    r = iv.buscar("dedos", "soldar vértices duplicados", red, version="5.2.2", ahora=AHORA, guardar=False, **kb)
    assert r["estado"] == "RESEARCH_REQUIRED"          # una sola fuente: el gate exige dos
    assert "insufficient_sources" in r["gate"]["reasons"]
    assert "bmesh.ops.remove_doubles" in r["candidatos"] or "bmesh.ops.weld_verts" in r["candidatos"]


def test_verified_vigente_se_usa_y_termina(kb):
    iv.guardar_json(kb["kb_indice"], {"entradas": [{"capacidad": "dedos", "blender": "5.2.2", "brief": "b.json",
                                                    "candidatos": [{"tecnica": "bmesh.ops.x", "estado": "verified"}]}]})
    r = iv.buscar("dedos", "otra cosa", RedFalsa({}), version="5.2.2", ahora=AHORA, **kb)
    assert r["estado"] == "USAR_VERIFICADA" and r["tecnica"] == "bmesh.ops.x"
    r = iv.buscar("dedos", "otra cosa", RedFalsa({}), version="5.3.0", ahora=AHORA, **kb)
    assert r["estado"] == "RESEARCH_REQUIRED"          # otra versión de Blender: no vale


def test_failed_previa_no_se_repite(kb):
    iv.guardar_json(kb["kb_indice"], {"entradas": [{"capacidad": "dedos", "blender": "5.2.2", "brief": "b.json",
                                                    "candidatos": [{"tecnica": "bmesh.ops.bisect_plane",
                                                                    "estado": "failed", "motivo": "rompe"}]}]})
    r = iv.buscar("dedos", "separar dedos de una mano", red_completa(), version="5.2.2", ahora=AHORA,
                  guardar=False, **kb)
    assert "bmesh.ops.bisect_plane" not in r["candidatos"]
    assert any(d["name"] == "bmesh.ops.bisect_plane" for d in r["descartadas"])


def test_marcar_estados():
    brief = {"candidatos": [{"tecnica": "a", "estado": "unverified"}, {"tecnica": "b", "estado": "unverified"}],
             "techniques": [{"name": "a"}, {"name": "b"}]}
    indice = {"entradas": [{"brief": "x.json", "candidatos": [{"tecnica": "a", "estado": "unverified"}]}]}
    iv.marcar(indice, brief, "x.json", "a", "failed", "rompe")
    assert brief["estado"] == "unverified" and indice["entradas"][0]["candidatos"][0]["estado"] == "failed"
    iv.marcar(indice, brief, "x.json", "b", "verified", "pasa")
    assert brief["estado"] == "verified" and brief["techniques"][1]["estado"] == "verified"


def test_respaldo_por_repositorios_si_la_busqueda_de_codigo_no_sirve(kb):
    """Con el token de Actions `search/code` no busca en repos ajenos: se usa search/repositories + árbol."""
    r = {API + "bmesh.ops.html": (200, leer("bmesh_ops.html")),
         API + "bpy.ops.mesh.html": (200, leer("bpy_ops_mesh.html")),
         "https://api.github.com/repos/ejemplo/manos/git/trees/main?recursive=1": (200, leer("github_tree.json")),
         "https://raw.githubusercontent.com/ejemplo/manos/main/tools/ejemplo_split.py": (200, leer("ejemplo_split.py"))}

    class R(RedFalsa):
        def get(self, url, aceptar=None):
            if url.startswith("https://api.github.com/search/code"):
                self.registro.append({"url": url, "codigo": 403, "bytes": 0})
                return 403, ""
            if url.startswith("https://api.github.com/search/repositories"):
                self.registro.append({"url": url, "codigo": 200, "bytes": 1})
                return 200, leer("github_repos.json")
            return super().get(url, aceptar)
    res = iv.buscar("dedos", "separar y cortar dedos de una mano", R(r), version="5.2.2", ahora=AHORA,
                    guardar=False, **kb)
    assert res["estado"] == "CANDIDATOS", res["gate"]
    b = res["brief"]
    assert any(s["source_type"] == "community" and "ejemplo/manos" in s["url"] for s in b["sources"])
    assert any(c.startswith("403 https://api.github.com/search/code") for c in
               [f"{x['codigo']} {x['url']}" for x in b["consultas_http"]])


def test_parsear_enum_en_lista():
    html = ('<ul><li><p><code class="docutils literal notranslate"><span class="pre">WELD</span></code> '
            'Weld – Find groups of vertices closer than dist.</p></li><li><p><code><span class="pre">DECIMATE</span>'
            '</code> Decimate – Reduce the geometry density.</p></li></ul>')
    sec = iv.parsear_enum(html)
    assert [s["nombre"] for s in sec] == ["modificador:WELD", "modificador:DECIMATE"]
    assert "closer than dist" in sec[0]["texto"]
