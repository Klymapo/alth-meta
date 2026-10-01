"""Re-dimensiona los assets aprobados a la escala de Alpha (bloque T0 de docs/BRIEF_LINEA_UNICA.md).

    alth-python tools/redimensionar.py                       # muestra el plan, no toca nada
    alth-python tools/redimensionar.py --aplicar             # los 5 assets aprobados
    alth-python tools/redimensionar.py --aplicar manzana     # solo uno

Los assets NO se rehacen: se abre su .blend (la fuente aprobada), se escala todo uniforme alrededor del
origen (pies en Z=0, centro en X=0, así el apoyo y el centrado no cambian) por
    f = s0_nuevo / s0_con_que_se_hizo
y se re-exporta con alth.exportar_glb, que unifica unidades y eje: raíz ×0.01 (1 mm de maqueta = 1 cm
en Godot) y glTF Y-up. Después:
  - se corre la verificación automática (cotas ±2 %, tris, paleta, flotantes, apoyo Z=0) con las cotas
    nuevas de su spec.json;
  - se revisa el GLB sin Blender (raíz ×0.01, alto sobre +Y, piso en Y=0);
  - se reescriben spec.json (medidas, cotas, historial) y data/medidas.csv.
Es idempotente: un asset cuyo spec.json ya dice "escala": {"version": "v2.0"} se salta.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
APROBADOS = ["manzana", "lata", "taza", "vaso", "vaso_cafe"]
MEDIDAS_CSV = RAIZ / "data" / "medidas.csv"
VERSION = "v2.0"
FECHA = "2026-10-01"
S0_FORMULA = re.compile(r"mm_real \* ([0-9.]+) \* ([0-9.]+)")


# ---------------------------------------------------------------- lógica pura (sin Blender)
def cargar_spec() -> dict:
    return json.loads((RAIZ / "spec" / "alth_spec.json").read_text(encoding="utf-8"))


def s0_nuevo(spec: dict) -> float:
    return float(spec["escala_alpha"]["s0"])


def s0_viejo(asset: dict, spec: dict) -> float:
    """s0 con que se hizo el asset: el de su fórmula; si no la trae, el de la spec v1."""
    m = S0_FORMULA.search(str(asset.get("medidas_alth_mm", {}).get("formula", "")))
    if m:
        return float(m.group(1))
    return float(spec["escala_congelada"].get("anterior", {}).get("s0", 0.0559))


def ya_redimensionado(asset: dict) -> bool:
    return (asset.get("escala") or {}).get("version") == VERSION


def spec_asset_nueva(asset: dict, f: float, s0: float, s0v: float) -> dict:
    """spec.json del asset con medidas y cotas ×f, fórmula nueva y una línea de historial."""
    nuevo = json.loads(json.dumps(asset))
    k = asset.get("k", 1.0)
    med = nuevo.get("medidas_alth_mm", {})
    for c, v in list(med.items()):
        if isinstance(v, (int, float)):
            med[c] = round(v * f, 2)
    med["formula"] = f"mm_real * {s0} * {k}"
    for c in nuevo.get("cotas", []):
        c["mm"] = round(c["mm"] * f, 2)
    nuevo["escala"] = {"version": VERSION, "s0": s0, "factor": round(f, 5),
                       "nota": "re-dimensionado uniforme con tools/redimensionar.py; forma sin cambios"}
    nuevo.setdefault("historial", []).append(
        {"vuelta": "escala v2", "nota": f"×{f:.4f} (s0 {s0v:g} → {s0}); solo tamaño, aprobado sin rehacer",
         "fecha": FECHA})
    return nuevo


def filas_csv_nuevas(filas: list[dict], factores: dict[str, float], s0: float) -> list[dict]:
    """Escala alth_mm de los assets re-dimensionados y recalcula k_observado con el s0 nuevo."""
    out = []
    for f in filas:
        f = dict(f)
        if f["asset"] in factores:
            alth = float(f["alth_mm"]) * factores[f["asset"]]
            f["alth_mm"] = f"{alth:.2f}"
            f["k_observado"] = f"{alth / (float(f['real_mm']) * s0):.2f}"
            f["fecha"] = FECHA
        out.append(f)
    return out


def leer_glb(ruta: Path) -> dict:
    """JSON de un GLB (sin Blender)."""
    b = ruta.read_bytes()
    magia, _, _ = struct.unpack_from("<4sII", b, 0)
    assert magia == b"glTF", f"{ruta} no es GLB"
    largo, tipo = struct.unpack_from("<I4s", b, 12)
    assert tipo == b"JSON"
    return json.loads(b[20:20 + largo])


def revisar_glb(ruta: Path, escala_raiz: float) -> dict:
    """Raíz ×escala_raiz y alto sobre +Y con el piso en Y≈0 (glTF Y-up), mirando solo el GLB."""
    g = leer_glb(ruta)
    nodos = g["nodes"]
    hijos = {c for n in nodos for c in n.get("children", [])}
    raices = [i for i in range(len(nodos)) if i not in hijos]
    raiz = nodos[raices[0]] if len(raices) == 1 else None
    escala_ok = bool(raiz) and all(abs(s - escala_raiz) < 1e-6 for s in raiz.get("scale", [1, 1, 1]))
    sin_rot = bool(raiz) and raiz.get("rotation", [0, 0, 0, 1]) == [0, 0, 0, 1]
    # piso: el mínimo Y (en mundo) de los hijos sin rotación propia ≈ 0
    y_min = None
    for i in (raiz or {}).get("children", []):
        n = nodos[i]
        if "mesh" not in n or n.get("rotation", [0, 0, 0, 1]) != [0, 0, 0, 1]:
            continue
        sy = n.get("scale", [1, 1, 1])[1]
        ty = n.get("translation", [0, 0, 0])[1]
        for p in g["meshes"][n["mesh"]]["primitives"]:
            acc = g["accessors"][p["attributes"]["POSITION"]]
            y = (acc["min"][1] * sy + ty) * escala_raiz
            y_min = y if y_min is None else min(y_min, y)
    return {"raiz_unica": raiz is not None, "escala_raiz_ok": escala_ok, "raiz_sin_rotacion": sin_rot,
            "piso_y_m": None if y_min is None else round(y_min, 6),
            "ok": bool(raiz) and escala_ok and sin_rot and (y_min is not None and abs(y_min) < 1e-4)}


# ---------------------------------------------------------------- Blender
def _hex_de_material(mat) -> str | None:
    """Color base del material (lineal) → hex sRGB."""
    nodos = mat.node_tree.nodes if mat.node_tree else []
    bsdf = next((n for n in nodos if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return None
    lin = list(bsdf.inputs["Base Color"].default_value)[:3]
    srgb = [12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in lin]
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in srgb)


def _a_paleta(hexa: str, paleta: set[str]) -> str:
    """El color de vuelta del material puede diferir ±1 por redondeo: se ajusta al hex de paleta más cercano."""
    if hexa in paleta:
        return hexa
    rgb = [int(hexa[i:i + 2], 16) for i in (1, 3, 5)]
    mejor = min(paleta, key=lambda h: sum((int(h[i:i + 2], 16) - c) ** 2 for i, c in zip((1, 3, 5), rgb)))
    d = sum((int(mejor[i:i + 2], 16) - c) ** 2 for i, c in zip((1, 3, 5), rgb))
    return mejor if d <= 3 * 2 ** 2 else hexa


def redimensionar(nombre: str, spec: dict, aplicar: bool) -> dict:
    import bpy
    from mathutils import Matrix
    sys.path.insert(0, str(RAIZ))
    import alth
    from alth import verificacion as ver

    carpeta = RAIZ / "assets" / nombre
    ruta_spec = carpeta / "spec.json"
    asset = json.loads(ruta_spec.read_text(encoding="utf-8"))
    if ya_redimensionado(asset):
        return {"asset": nombre, "estado": "ya en " + VERSION, "factor": asset["escala"]["factor"]}
    s0n, s0v = s0_nuevo(spec), s0_viejo(asset, spec)
    f = s0n / s0v
    plan = {"asset": nombre, "s0_viejo": s0v, "s0_nuevo": s0n, "factor": round(f, 5)}
    if not aplicar:
        return {**plan, "estado": "plan"}

    bpy.ops.wm.open_mainfile(filepath=str(carpeta / f"{nombre}.blend"))
    objs = [o for o in bpy.data.objects if o.type == "MESH" and o.name != "Piso_ALTH"]
    S = Matrix.Scale(f, 4)
    for o in objs:
        assert o.parent is None, f"{o.name} tiene padre: el escalado alrededor del origen no aplica"
        o.matrix_world = S @ o.matrix_world
    bpy.context.view_layer.update()

    paleta = ver.colores_paleta(alth.SPEC)
    alth.COLORES_USADOS.clear()
    for o in objs:
        for m in o.data.materials:
            if m and (h := _hex_de_material(m)):
                alth.COLORES_USADOS[m.name] = _a_paleta(h, paleta)
    nuevo = spec_asset_nueva(asset, f, s0n, s0v)
    verif = alth.verificar(objs, nuevo)
    if not verif["ok"]:
        return {**plan, "estado": "FALLA verificación", "verificacion": verif}
    medidas = alth.medidas(objs)          # antes de exportar: exportar_glb cuelga todo de la raíz ×0.01
    alth.exportar_glb(objs, carpeta / f"{nombre}.glb")
    glb = revisar_glb(carpeta / f"{nombre}.glb", alth.SPEC["unidades"]["export_godot"]["escala_raiz"])
    if not glb["ok"]:
        return {**plan, "estado": "FALLA GLB", "glb": glb}
    ruta_spec.write_text(json.dumps(nuevo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**plan, "estado": "aplicado", "verificacion": ver.resumen(verif), "glb": glb,
            "medidas_mm": medidas}


def actualizar_csv(factores: dict[str, float], s0: float):
    with MEDIDAS_CSV.open(encoding="utf-8", newline="") as fh:
        lector = csv.DictReader(fh)
        campos, filas = lector.fieldnames, list(lector)
    with MEDIDAS_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        w.writerows(filas_csv_nuevas(filas, factores, s0))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("assets", nargs="*", default=APROBADOS)
    ap.add_argument("--aplicar", action="store_true", help="escala, re-exporta y reescribe spec/csv")
    args = ap.parse_args(argv)
    spec = cargar_spec()
    if "escala_alpha" not in spec:
        print("ERROR: la spec no trae escala_alpha.s0; corre antes tools/medir_alpha.py --spec", file=sys.stderr)
        return 2
    resultados, factores, ok = [], {}, True
    for nombre in args.assets:
        r = redimensionar(nombre, spec, args.aplicar)
        resultados.append(r)
        print(json.dumps(r, ensure_ascii=False, default=str))
        if r["estado"] == "aplicado":
            factores[nombre] = r["factor"]
        ok &= not r["estado"].startswith("FALLA")
    if factores:
        actualizar_csv(factores, s0_nuevo(spec))
        print("data/medidas.csv actualizado:", ", ".join(factores))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
