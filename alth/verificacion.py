"""ALTH-META · verificación automática de un asset.

Revisa lo que se puede medir sin mirar el render, para que la sesión no tenga que adivinar:

- cotas: medidas de piezas contra `assets/<nombre>/spec.json` → "cotas" (±2 % por defecto)
- triángulos: total después de modificadores contra el tope de su categoría
- paleta: cada color usado existe en `spec/alth_spec.json` (paleta, medidos o paleta_notas)
- flotantes: toda pieza toca el piso o toca otra pieza que llega al piso
- apoyo: el asset descansa en Z=0 (ni hundido ni en el aire)

Lo que NO revisa (eso sigue siendo trabajo de mirar la hoja de contacto): si se parece a la
referencia, si se lee bien la forma y si los detalles se entienden.

La lógica de evaluación (`evaluar`) no depende de Blender; `recolectar` es la parte que lo usa.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
TOLERANCIA = 0.02          # ±2 % en cotas
CONTACTO_MM = 0.1          # distancia máxima para considerar que dos piezas se tocan
PISO_MM = 0.05             # z_min máximo para considerar que una pieza toca el piso

TOPE_POR_CATEGORIA = {     # categoría del asset → clave en spec geometria.tris_max
    "de_mano": "objeto_mano", "portatil": "objeto_mano", "largo_en_mano": "objeto_mano",
    "animal_pequeno": "personaje", "personaje": "personaje",
    "anclado_al_cuerpo": "mueble", "mueble": "mueble", "vehiculo": "mueble", "arquitectura": "mueble",
}


# ---------------------------------------------------------------- lógica pura
def colores_paleta(spec: dict) -> set[str]:
    """Todos los hex que aparezcan en paleta y paleta_notas (incluye medidos y añadidos)."""
    texto = json.dumps({k: spec.get(k) for k in ("paleta", "paleta_notas")})
    return {h.upper() for h in HEX.findall(texto)}


def tope_tris(spec: dict, asset: dict) -> int | None:
    if asset.get("tris_max"):
        return int(asset["tris_max"])
    clave = TOPE_POR_CATEGORIA.get(asset.get("categoria", ""), None)
    return spec.get("geometria", {}).get("tris_max", {}).get(clave) if clave else None


def evaluar(datos: dict, spec: dict, asset: dict) -> dict:
    """datos = {"piezas": {nombre: {"W","D","H","z_min","tris","colores":[hex], "toca":[nombres]}}}"""
    piezas = datos["piezas"]
    checks = []

    def check(nombre, ok, detalle):
        checks.append({"check": nombre, "ok": bool(ok), "detalle": detalle})

    # cotas
    tol = asset.get("tolerancia_cotas", TOLERANCIA)
    cotas = asset.get("cotas", [])
    if not cotas:
        check("cotas", False, "spec.json no tiene bloque \"cotas\"; agrégalo para poder verificar medidas")
    for c in cotas:
        p = piezas.get(c["pieza"])
        if p is None:
            check(f"cota {c['pieza']}.{c['eje']}", False, f"no existe la pieza {c['pieza']}")
            continue
        med, obj = p[c["eje"]], c["mm"]
        err = (med - obj) / obj
        check(f"cota {c['pieza']}.{c['eje']}", abs(err) <= c.get("tolerancia", tol),
              f"{med:.2f} mm vs {obj:.2f} mm ({err:+.1%})")

    # triángulos
    total = sum(p["tris"] for p in piezas.values())
    tope = tope_tris(spec, asset)
    check("triangulos", tope is None or total <= tope, f"{total} de {tope if tope else 'sin tope'}")

    # paleta
    validos = colores_paleta(spec)
    fuera = sorted({h.upper() for p in piezas.values() for h in p["colores"]} - validos)
    check("paleta", not fuera, "todos los colores están en la paleta" if not fuera
          else f"fuera de paleta: {', '.join(fuera)} (propónselos al usuario o usa uno de la spec)")

    # flotantes: componente conectada con el piso
    permitidas = set(asset.get("permitir_flotantes", []))
    anclado = {n for n, p in piezas.items() if p["z_min"] <= PISO_MM}
    cambio = True
    while cambio:
        cambio = False
        for n, p in piezas.items():
            if n not in anclado and any(v in anclado for v in p["toca"]):
                anclado.add(n)
                cambio = True
    flotan = sorted(set(piezas) - anclado - permitidas)
    check("flotantes", not flotan, "todas las piezas están unidas al piso" if not flotan
          else f"piezas en el aire o sin tocar a otra: {', '.join(flotan)}")

    # apoyo
    zmin = min(p["z_min"] for p in piezas.values())
    check("apoyo", -PISO_MM <= zmin <= PISO_MM, f"z mínimo del asset: {zmin:+.2f} mm")

    return {"ok": all(c["ok"] for c in checks), "triangulos": total, "checks": checks}


def resumen(ver: dict) -> str:
    lineas = [f"VERIFICACION {'OK' if ver['ok'] else 'CON FALLAS'}"]
    lineas += [f"  {'✓' if c['ok'] else '✗'} {c['check']}: {c['detalle']}" for c in ver["checks"]]
    return "\n".join(lineas)


def cargar_asset(asset) -> dict:
    if isinstance(asset, dict):
        return asset
    return json.loads(Path(asset).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- parte que usa Blender
def recolectar(objs, colores_por_material: dict) -> dict:
    import bpy
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    info, arboles, vertices = {}, {}, {}
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        polys = [tuple(p.vertices) for p in me.polygons]
        tris = sum(len(p) - 2 for p in polys)
        ev.to_mesh_clear()
        xs, ys, zs = [v.x for v in vs], [v.y for v in vs], [v.z for v in vs]
        info[o.name] = {
            "W": max(xs) - min(xs), "D": max(ys) - min(ys), "H": max(zs) - min(zs),
            "z_min": min(zs), "tris": tris, "toca": [],
            "colores": [colores_por_material.get(m.name, "#??????") for m in o.data.materials if m],
        }
        arboles[o.name] = BVHTree.FromPolygons(vs, polys)
        vertices[o.name] = vs

    nombres = list(info)
    for i, a in enumerate(nombres):
        for b in nombres[i + 1:]:
            toca = bool(arboles[a].overlap(arboles[b]))
            if not toca:
                for va, tb in ((vertices[a], arboles[b]), (vertices[b], arboles[a])):
                    for v in va:
                        hit = tb.find_nearest(v, CONTACTO_MM)
                        if hit[0] is not None:
                            toca = True
                            break
                    if toca:
                        break
            if toca:
                info[a]["toca"].append(b)
                info[b]["toca"].append(a)
    return {"piezas": info}
