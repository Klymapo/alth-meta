"""Avatares riggeados a la escala ALTH (tools/importar_avatar.py), sin Blender.

    python3 -m pytest tests/test_importar_avatar.py
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tools"))
import importar_avatar as I  # noqa: E402

SPEC = json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))
AVATARES = {k: v for k, v in SPEC["avatares"].items() if isinstance(v, dict)}
ALPHA_SHA = "ed2b04ecd9e22a19794591b873c19c2b30323a9ae836f7dd820134bd0113580b"


def test_avatares_a_la_altura_de_su_arquetipo():
    for nombre, a in AVATARES.items():
        m = I.medir(RAIZ / a["glb"])
        objetivo, _ = I.alto_objetivo(a["arquetipo"], SPEC)
        assert abs(m["alto_sin_pelo"] / objetivo - 1) < 1e-3, (nombre, m["alto_sin_pelo"], objetivo)
        assert abs(m["pie_y"]) < 1e-4 and abs(m["centro_x"]) < 1e-3, nombre          # pies en el piso, centrado


def test_avatares_conservan_rig_dedos_y_caras():
    for nombre, a in AVATARES.items():
        m = I.medir(RAIZ / a["glb"])
        assert m["huesos"] >= 50, nombre
        assert {"Thumb", "Index", "Middle", "Ring"} <= set(m["dedos"]), (nombre, m["dedos"])   # dedos separados
        assert {"Blink", "MouthOpen", "MouthSmile"} <= set(m["expresiones"]), nombre
        assert "Talk-loop" in m["animaciones"], nombre
        assert m["tris"] <= SPEC["geometria"]["tris_max"]["avatar_riggeado"], (nombre, m["tris"])


def test_la_piel_sigue_pegada_al_esqueleto():
    for nombre, a in AVATARES.items():
        j, b = I.leer(RAIZ / a["glb"])
        assert I.error_de_piel(j, b) < I.TOL_PIEL, nombre


def test_escalar_hornea_todo_y_no_despega_la_piel():
    a = next(iter(AVATARES.values()))
    j, b = I.leer(RAIZ / a["glb"])
    antes = I.medir(RAIZ / a["glb"])
    I.escalar(j, b, 2.0)
    with tempfile.TemporaryDirectory() as t:
        ruta = Path(t) / "x2.glb"
        I.escribir(ruta, j, b)
        despues = I.medir(ruta)
        j2, b2 = I.leer(ruta)
    assert abs(despues["alto_total"] / antes["alto_total"] - 2) < 1e-5
    assert I.error_de_piel(j2, b2) < I.TOL_PIEL
    # la escala queda horneada: ningún nodo con escala ≠ 1 por culpa de la importación
    assert all(np.allclose(n.get("scale", [1, 1, 1]), [1, 1, 1]) for n in j2["nodes"] if "skin" not in n
               and n.get("name") in ("Armature", "Root", "Hips"))


def test_theo_alpha_no_se_reemplaza():
    assert hashlib.sha256((RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb").read_bytes()).hexdigest() == ALPHA_SHA
    try:
        I.importar(RAIZ / next(iter(AVATARES.values()))["glb"], "theo_alpha", RAIZ / "assets" / "joven_rubio")
    except ValueError as e:
        assert "protegido" in str(e)
    else:
        raise AssertionError("debió negarse a escribir theo_alpha.glb")
    assert hashlib.sha256((RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb").read_bytes()).hexdigest() == ALPHA_SHA


def test_importar_es_idempotente_en_escala():
    """Importar un avatar ya importado no lo vuelve a agrandar: la escala sale ≈ 1."""
    a = next(iter(AVATARES.values()))
    with tempfile.TemporaryDirectory() as t:
        r = I.importar(RAIZ / a["glb"], "copia", Path(t), a["arquetipo"])
    assert abs(r["escala_horneada"] - 1) < 1e-3
