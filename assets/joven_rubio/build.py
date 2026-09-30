"""Joven rubio · primer personaje ALTH-META, arquetipo estándar 95 mm, T-pose.

    alth-python assets/joven_rubio/build.py            # iteración
    alth-python assets/joven_rubio/build.py final      # render final + GLB

COPOX puede inyectar un JSON por ``COPOX_PARAMS`` y pedir un GLB de iteración mediante
``COPOX_EXPORT_GLTF``. Sin esas variables el resultado conserva exactamente los defaults
históricos de este build.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import alth  # noqa: E402
from alth import personaje, ropa, pelo  # noqa: E402

MODO = sys.argv[-1] if sys.argv[-1] in alth.MODOS else "iteracion"

PIEL = "#FBC39C"
RUBIO = "#EFC989"
CAMISA = "#FBEFE1"
CHALECO = "#302E2D"
CORBATA = "#41598D"
PANTALON = "#4A5770"
ZAPATO = "#292929"
OJO_IRIS = "#4A3220"
BOTON = "#B7BABE"
OJO_BLANCO = "#FBF8F4"

DEFAULT_PARAMS = {
    "body": {"grosor_extremidades": 1.25},
    "face": {
        "eye_width_scale": 1.0,
        "eye_height_scale": 1.0,
        "iris_width": 3.9,
        "iris_height": 6.3,
        "iris_outward": 0.6,
        "iris_z": -0.3,
        "brow_width": 8.4,
        "brow_height": 1.6,
        "brow_z": 2.8,
        "mouth_width": 6.0,
        "mouth_height": 0.9,
        "mouth_z": -6.6,
    },
    "hair": {
        "escala": 1.3,
        "sesgo_atras": 2.5,
        "margen_arriba": 3.0,
        "cunias": 10,
        "ancho_base": [8.0, 12.0],
        "largo": [10.0, 17.0],
        "caida": [3.0, 8.0],
        "copete": 3,
        "semilla": 1,
    },
}


def merge(base, extra):
    out = json.loads(json.dumps(base))
    for key, value in (extra or {}).items():
        if key == "_copox":
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_params():
    path = os.environ.get("COPOX_PARAMS")
    if not path:
        return json.loads(json.dumps(DEFAULT_PARAMS))
    return merge(DEFAULT_PARAMS, json.loads(Path(path).read_text(encoding="utf-8")))


P = load_params()
body = P["body"]
face = P["face"]
hair = P["hair"]

alth.nueva_escena()

GROSOR_EXTREMIDADES = float(body["grosor_extremidades"])
pl = personaje.plan("estandar", grosor_extremidades=GROSOR_EXTREMIDADES)
piezas = pl["piezas"]
cuerpo = personaje.construir("estandar", color_piel=PIEL, color_zapato=ZAPATO,
                              grosor_extremidades=GROSOR_EXTREMIDADES)
objs = list(cuerpo.values())

CB = alth.SPEC["cuerpo_base_95mm"]
cabeza = piezas["cabeza"]
z_cabeza_top = cabeza["pos"][2] + cabeza["tam"][2]
z_ojo = z_cabeza_top - (95.0 - CB["ojo_centro_xz"][1])
x_ojo = CB["ojo_centro_xz"][0]
ojo_w, ojo_h = CB["ojo_WH"]
ojo_w *= float(face["eye_width_scale"])
ojo_h *= float(face["eye_height_scale"])


def y_cara_en(z_mundo):
    t = max(0.0, min(1.0, (z_mundo - cabeza["pos"][2]) / cabeza["h"]))
    d = cabeza["d_abajo"] + (cabeza["d_arriba"] - cabeza["d_abajo"]) * t
    return cabeza["pos"][1] - d / 2


for lado, s in (("izq", -1), ("der", 1)):
    ox = s * x_ojo
    o = alth.caja(f"Joven_ojo_blanco_{lado}", (ojo_w, 0.35, ojo_h), pos=(ox, y_cara_en(z_ojo) - 0.1, z_ojo),
                  color=OJO_BLANCO, biselar=False, apoyada=False)
    objs.append(o)
    o = alth.caja(
        f"Joven_iris_{lado}",
        (float(face["iris_width"]), 0.35, float(face["iris_height"])),
        pos=(ox + s * float(face["iris_outward"]), y_cara_en(z_ojo) - 0.25, z_ojo + float(face["iris_z"])),
        color=OJO_IRIS, biselar=False, apoyada=False,
    )
    objs.append(o)
    z_ceja = z_ojo + ojo_h / 2 + float(face["brow_z"])
    o = alth.caja(
        f"Joven_ceja_{lado}",
        (float(face["brow_width"]), 0.5, float(face["brow_height"])),
        pos=(ox, y_cara_en(z_ceja) - 0.1, z_ceja),
        color=OJO_IRIS, biselar=False, apoyada=False,
    )
    objs.append(o)

z_boca = z_ojo + float(face["mouth_z"])
o = alth.caja(
    "Joven_boca",
    (float(face["mouth_width"]), 0.5, float(face["mouth_height"])),
    pos=(0.0, y_cara_en(z_boca) - 0.1, z_boca),
    color=OJO_IRIS, biselar=False, apoyada=False,
)
objs.append(o)

objs += ropa.traje_formal(piezas, "Joven", camisa=CAMISA, chaleco=CHALECO, corbata=CORBATA,
                           boton=BOTON, pantalon=PANTALON)

objs.append(pelo.construir_pelo(
    cabeza,
    escala=float(hair["escala"]),
    sesgo_atras=float(hair["sesgo_atras"]),
    margen_arriba=float(hair["margen_arriba"]),
    cunias=int(hair["cunias"]),
    ancho_base=tuple(float(x) for x in hair["ancho_base"]),
    largo=tuple(float(x) for x in hair["largo"]),
    caida=tuple(float(x) for x in hair["caida"]),
    copete=int(hair["copete"]),
    semilla=int(hair["semilla"]),
    color=RUBIO,
    nombre="Joven_pelo",
))

alth.estudio()
maniqui = alth.junto_a_maniqui(objs)
rep = alth.revisar(objs, alth.RAIZ / "renders" / "joven_rubio" / MODO, modo=MODO,
                    titulo=f"joven_rubio · {MODO}", asset=alth.RAIZ / "assets" / "joven_rubio" / "spec.json",
                    extras=maniqui)
print("TOTAL_TRIS", sum(v["tris_sin_modificadores"] for v in rep["medidas_mm"].values()))
print(rep["segundos_total"])

export_override = os.environ.get("COPOX_EXPORT_GLTF")
if export_override:
    alth.exportar_glb(objs, Path(export_override))
elif MODO == "final":
    alth.exportar_glb(objs, alth.RAIZ / "assets" / "joven_rubio" / "joven_rubio.glb")
