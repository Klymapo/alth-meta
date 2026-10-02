"""ALTH-META · importa un avatar riggeado (GLB) a la escala del mundo ALTH, sin Blender.

Decisión del dueño (1 oct 2026): los avatares nuevos (Theo y el detective, riggeados, con caras y
animaciones) entran "a la escala adecuada para la ciudad, los objetos y sus armas". Esa escala la fija
Theo Alpha (`spec/alth_spec.json` → `escala_alpha`), que NO se reemplaza: sigue siendo la regla de medir.

Qué hace:
  1. mide el avatar en su pose de reposo: alto total y alto SIN PELO (sin las primitivas con material
     `Hair`), igual que se midió Alpha (de la suela al tope de la cabeza, sin pelo);
  2. toma el alto objetivo de su arquetipo (`arquetipos_alpha.<arquetipo>.alto_mm`; Theo y el detective
     son `estandar` = 95.69 mm) y lo pasa a unidades del GLB con `unidades.export_godot.escala_raiz` (×0.01: 1 mm
     de maqueta = 1 cm en Godot);
  3. HORNEA la escala en los datos (no deja un nodo escalado, que en Godot complica el esqueleto):
     posiciones, deltas de las expresiones (morph targets), traslaciones de los nodos y huesos, matrices
     de bind inversas y canales de traslación de las animaciones. Rotaciones, escalas locales, pesos,
     normales y expresiones quedan iguales;
  4. comprueba que la piel sigue pegada al esqueleto (pose de reposo reconstruida con los huesos =
     posiciones escaladas) y escribe el GLB, `spec.json` y `medidas.json`.

  python3 tools/importar_avatar.py medir theo_chibi.glb
  python3 tools/importar_avatar.py importar theo_chibi.glb --nombre theo_chibi --carpeta assets/joven_rubio \\
      --arquetipo estandar --personaje "Theo (joven rubio)"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import date
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
SPEC = RAIZ / "spec" / "alth_spec.json"
PROTEGIDO = RAIZ / "assets" / "joven_rubio" / "theo_alpha.glb"
MATERIALES_PELO = ("Hair",)
TOL_PIEL = 1e-4          # error máximo (fracción del alto) al reconstruir la pose de reposo con el esqueleto
_TIPOS = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
_N = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


# ================================================================ GLB crudo
def leer(ruta) -> tuple[dict, bytearray]:
    b = Path(ruta).read_bytes()
    magia, version, _ = struct.unpack("<III", b[:12])
    if magia != 0x46546C67 or version != 2:
        raise ValueError(f"{ruta} no es un GLB 2.0")
    largo_json, tipo = struct.unpack("<II", b[12:20])
    j = json.loads(b[20:20 + largo_json])
    o = 20 + largo_json
    largo_bin, _ = struct.unpack("<II", b[o:o + 8])
    return j, bytearray(b[o + 8:o + 8 + largo_bin])


def escribir(ruta, j: dict, binario: bytearray) -> None:
    bn = bytes(binario) + b"\0" * (-len(binario) % 4)
    j["buffers"][0]["byteLength"] = len(binario)
    js = json.dumps(j, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(bn)
    with open(ruta, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bn), 0x004E4942) + bn)


def _vista(j, binario, i) -> tuple[np.ndarray, int, int, int]:
    """(arreglo copia, offset, stride, bytes por elemento) de un accesor float/int sin sparse."""
    a = j["accessors"][i]
    if "sparse" in a:
        raise ValueError("accesores sparse no soportados")
    bv = j["bufferViews"][a["bufferView"]]
    dt = np.dtype(_TIPOS[a["componentType"]])
    n = _N[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    paso = bv.get("byteStride") or n * dt.itemsize
    filas = np.frombuffer(binario, np.uint8, (a["count"] - 1) * paso + n * dt.itemsize, o)
    out = np.empty((a["count"], n), dt)
    for k in range(a["count"]):
        out[k] = filas[k * paso:k * paso + n * dt.itemsize].view(dt)
    return out, o, paso, n * dt.itemsize


def accesor(j, binario, i) -> np.ndarray:
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    dt = np.dtype(_TIPOS[a["componentType"]])
    n = _N[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    paso = bv.get("byteStride") or n * dt.itemsize
    if paso == n * dt.itemsize:
        return np.frombuffer(binario, dt, a["count"] * n, o).reshape(a["count"], n).copy()
    return _vista(j, binario, i)[0]


def _guardar_accesor(j, binario, i, datos: np.ndarray) -> None:
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    dt = np.dtype(_TIPOS[a["componentType"]])
    n = _N[a["type"]]
    o = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    paso = bv.get("byteStride") or n * dt.itemsize
    datos = np.ascontiguousarray(datos, dt).reshape(a["count"], n)
    if paso == n * dt.itemsize:
        binario[o:o + datos.nbytes] = datos.tobytes()
    else:
        for k in range(a["count"]):
            binario[o + k * paso:o + k * paso + n * dt.itemsize] = datos[k].tobytes()
    if "min" in a:
        a["min"] = [float(x) for x in datos.min(0)]
        a["max"] = [float(x) for x in datos.max(0)]


def _matriz(n: dict) -> np.ndarray:
    if "matrix" in n:
        return np.array(n["matrix"], float).reshape(4, 4).T
    t = n.get("translation", [0, 0, 0])
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = n.get("scale", [1, 1, 1])
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * np.array(s, float)
    M[:3, 3] = t
    return M


def matrices_mundo(j) -> dict[int, np.ndarray]:
    out = {}

    def bajar(i, P):
        out[i] = P @ _matriz(j["nodes"][i])
        for c in j["nodes"][i].get("children", []):
            bajar(c, out[i])
    for r in j["scenes"][j.get("scene", 0)]["nodes"]:
        bajar(r, np.eye(4))
    return out


# ================================================================ medir
def medir(ruta) -> dict:
    """Alto total y sin pelo (eje Y del GLB), ancho, fondo, triángulos, huesos, expresiones y animaciones."""
    j, binario = leer(ruta)
    mundo = matrices_mundo(j)
    todo, sin_pelo, tris = [], [], 0
    for i, n in enumerate(j["nodes"]):
        if "mesh" not in n:
            continue
        # una malla con piel se dibuja en el espacio del esqueleto: su nodo no la mueve (spec glTF)
        M = np.eye(4) if "skin" in n else mundo.get(i, np.eye(4))
        for p in j["meshes"][n["mesh"]]["primitives"]:
            v = accesor(j, binario, p["attributes"]["POSITION"]).astype(float)
            v = (M @ np.c_[v, np.ones(len(v))].T).T[:, :3]
            todo.append(v)
            mat = j["materials"][p["material"]]["name"] if "material" in p else ""
            if mat not in MATERIALES_PELO:
                sin_pelo.append(v)
            tris += (j["accessors"][p["indices"]]["count"] if "indices" in p else len(v)) // 3
    if not todo:
        raise ValueError("el GLB no tiene mallas")
    T, S = np.vstack(todo), np.vstack(sin_pelo)
    nombres = [n.get("name", "") for n in j["nodes"]]
    expresiones = sorted({t for m in j["meshes"] for t in (m.get("extras") or {}).get("targetNames", [])})
    return {"alto_total": float(T[:, 1].max() - T[:, 1].min()),
            "alto_sin_pelo": float(S[:, 1].max() - T[:, 1].min()),
            "pie_y": float(T[:, 1].min()),
            "ancho_x": float(T[:, 0].max() - T[:, 0].min()), "fondo_z": float(T[:, 2].max() - T[:, 2].min()),
            "centro_x": float((T[:, 0].max() + T[:, 0].min()) / 2),
            "tris": int(tris), "huesos": len(j["skins"][0]["joints"]) if j.get("skins") else 0,
            "dedos": sorted({x.replace("Left", "").replace("Right", "").rstrip("0123456789")
                             .replace("Proximal", "").replace("Intermediate", "").replace("Distal", "")
                             .replace("Metacarpal", "") for x in nombres
                             if any(d in x for d in ("Thumb", "Index", "Middle", "Ring", "Little", "Pinky"))}),
            "expresiones": expresiones,
            "animaciones": [a.get("name", "") for a in j.get("animations", [])],
            "materiales": [m.get("name", "") for m in j.get("materials", [])]}


# ================================================================ escalar
def escalar(j: dict, binario: bytearray, s: float) -> None:
    """Hornea una escala uniforme `s` en todo lo que mide longitud. Modifica j y binario en el lugar."""
    hechos = set()

    def una_vez(i, f):
        if i in hechos:
            return
        hechos.add(i)
        _guardar_accesor(j, binario, i, f(accesor(j, binario, i)))
    for m in j["meshes"]:
        for p in m["primitives"]:
            una_vez(p["attributes"]["POSITION"], lambda v: v * s)
            for t in p.get("targets", []):
                if "POSITION" in t:
                    una_vez(t["POSITION"], lambda v: v * s)
    for n in j["nodes"]:
        if "matrix" in n:
            M = np.array(n["matrix"], float).reshape(4, 4).T
            M[:3, 3] *= s
            n["matrix"] = [float(x) for x in M.T.reshape(-1)]
        elif "translation" in n:
            n["translation"] = [float(x) * s for x in n["translation"]]
    for sk in j.get("skins", []):
        if "inverseBindMatrices" in sk:
            def ibm(v):
                M = v.reshape(-1, 4, 4).copy()     # columnas: la traslación está en la fila 3 (column-major)
                M[:, 3, :3] *= s
                return M.reshape(-1, 16)
            una_vez(sk["inverseBindMatrices"], ibm)
    for a in j.get("animations", []):
        for c in a["channels"]:
            if c["target"]["path"] == "translation":
                una_vez(a["samplers"][c["sampler"]]["output"], lambda v: v * s)


def error_de_piel(j: dict, binario: bytearray) -> float:
    """Reconstruye la pose de reposo con el esqueleto (Σ w · J_mundo · IBM · v) y devuelve el error máximo
    respecto de las posiciones guardadas, en fracción del alto. ~0 = la piel sigue pegada a los huesos."""
    if not j.get("skins"):
        return 0.0
    mundo = matrices_mundo(j)
    peor, alto = 0.0, 1e-9
    for i, n in enumerate(j["nodes"]):
        if "mesh" not in n or "skin" not in n:
            continue
        sk = j["skins"][n["skin"]]
        ibm = accesor(j, binario, sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
        J = np.array([mundo[x] @ ibm[k] for k, x in enumerate(sk["joints"])])
        for p in j["meshes"][n["mesh"]]["primitives"]:
            v = accesor(j, binario, p["attributes"]["POSITION"]).astype(float)
            idx = accesor(j, binario, p["attributes"]["JOINTS_0"]).astype(int)
            w = accesor(j, binario, p["attributes"]["WEIGHTS_0"]).astype(float)
            w = w / np.maximum(w.sum(1, keepdims=True), 1e-9)
            vh = np.c_[v, np.ones(len(v))]
            r = np.zeros_like(v)
            for k in range(idx.shape[1]):
                r += w[:, k:k + 1] * np.einsum("nij,nj->ni", J[idx[:, k]], vh)[:, :3]
            peor = max(peor, float(np.abs(r - v).max()))
            alto = max(alto, float(v[:, 1].max() - v[:, 1].min()))
    return peor / alto


# ================================================================ importar
def alto_objetivo(arquetipo: str, spec: dict | None = None) -> tuple[float, float]:
    """(alto sin pelo en unidades del GLB, en mm de maqueta) del arquetipo, con la escala de exportación."""
    spec = spec or json.loads(SPEC.read_text(encoding="utf-8"))
    arq = spec["arquetipos_alpha"].get(arquetipo)
    if arq is None:
        raise ValueError(f"arquetipo desconocido: {arquetipo} (hay {', '.join(spec['arquetipos_alpha'])})")
    raiz = spec["unidades"]["export_godot"]["escala_raiz"]
    return arq["alto_mm"] * raiz, arq["alto_mm"]


def importar(origen, nombre: str, carpeta, arquetipo: str = "estandar", personaje: str = "",
             spec: dict | None = None) -> dict:
    origen, carpeta = Path(origen), Path(carpeta)
    destino = carpeta / f"{nombre}.glb"
    if destino.resolve() == PROTEGIDO.resolve():
        raise ValueError("theo_alpha.glb está protegido: es la regla de medir del repo y no se reemplaza")
    sha_alpha = hashlib.sha256(PROTEGIDO.read_bytes()).hexdigest() if PROTEGIDO.exists() else None
    antes = medir(origen)
    objetivo, objetivo_mm = alto_objetivo(arquetipo, spec)
    s = objetivo / antes["alto_sin_pelo"]
    j, binario = leer(origen)
    error_antes = error_de_piel(j, binario)
    escalar(j, binario, s)
    error_despues = error_de_piel(j, binario)
    if error_despues > max(TOL_PIEL, 2 * error_antes):
        raise RuntimeError(f"la piel se despegó del esqueleto al escalar (error {error_despues:.2e})")
    j.setdefault("asset", {}).setdefault("extras", {})["alth"] = {
        "importado": date.today().isoformat(), "escala_horneada": round(s, 6), "arquetipo": arquetipo,
        "alto_sin_pelo_mm_maqueta": objetivo_mm, "origen_sha256": hashlib.sha256(origen.read_bytes()).hexdigest()}
    carpeta.mkdir(parents=True, exist_ok=True)
    escribir(destino, j, binario)
    despues = medir(destino)
    if abs(despues["alto_sin_pelo"] / objetivo - 1) > 1e-3:
        raise RuntimeError(f"alto final {despues['alto_sin_pelo']:.4f} ≠ objetivo {objetivo:.4f}")
    if sha_alpha and hashlib.sha256(PROTEGIDO.read_bytes()).hexdigest() != sha_alpha:
        raise RuntimeError("theo_alpha.glb cambió: abortar")
    raiz = (spec or json.loads(SPEC.read_text(encoding="utf-8")))["unidades"]["export_godot"]["escala_raiz"]
    medidas = {"personaje": personaje or nombre, "arquetipo": arquetipo, "escala_horneada": round(s, 6),
               "error_piel_antes": error_antes, "error_piel_despues": error_despues,
               "antes": antes, "despues": despues,
               "despues_mm_maqueta": {k: round(despues[k] / raiz, 2) for k in ("alto_total", "alto_sin_pelo",
                                                                                 "ancho_x", "fondo_z")}}
    (carpeta / f"{nombre}.medidas.json").write_text(json.dumps(medidas, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    return medidas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("glb")
    i = sub.add_parser("importar")
    i.add_argument("glb")
    i.add_argument("--nombre", required=True)
    i.add_argument("--carpeta", required=True)
    i.add_argument("--arquetipo", default="estandar")
    i.add_argument("--personaje", default="")
    a = ap.parse_args(argv)
    try:
        r = medir(a.glb) if a.cmd == "medir" else importar(a.glb, a.nombre, a.carpeta, a.arquetipo, a.personaje)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
