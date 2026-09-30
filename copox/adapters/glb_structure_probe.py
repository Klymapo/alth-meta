from __future__ import annotations

import argparse
import json
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

JSON_CHUNK = 0x4E4F534A


def read_glb_json(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("No es un GLB válido")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2 or total != len(raw):
        raise ValueError(f"GLB header inválido: version={version} total={total} bytes={len(raw)}")
    pos = 12
    while pos + 8 <= len(raw):
        length, chunk_type = struct.unpack_from("<II", raw, pos)
        pos += 8
        data = raw[pos:pos + length]
        pos += length
        if chunk_type == JSON_CHUNK:
            return json.loads(data.rstrip(b" \t\r\n\x00").decode("utf-8"))
    raise ValueError("GLB sin chunk JSON")


def _semantic(name: str) -> str:
    low = name.lower()
    keywords = {
        "hair": ("fleco", "mechon", "capa_", "corona", "pelo", "hair"),
        "ears": ("oreja", "ear"),
        "eyes": ("ojo", "iris", "eye"),
        "mouth": ("boca", "mouth", "labio", "lip"),
        "hands": ("mano", "hand"),
        "fingers": ("dedo", "finger", "thumb", "pulgar"),
    }
    for group, tokens in keywords.items():
        if any(token in low for token in tokens):
            return group
    return "other"


def probe(path: str | Path, output: str | Path) -> dict[str, Any]:
    gltf = read_glb_json(path)
    nodes = gltf.get("nodes") or []
    meshes = gltf.get("meshes") or []
    materials = gltf.get("materials") or []
    textures = gltf.get("textures") or []
    images = gltf.get("images") or []
    skins = gltf.get("skins") or []
    animations = gltf.get("animations") or []

    material_usage: dict[int, list[str]] = defaultdict(list)
    semantic_materials: dict[str, set[int]] = defaultdict(set)
    node_rows: list[dict[str, Any]] = []
    for idx, node in enumerate(nodes):
        name = str(node.get("name") or f"node_{idx}")
        semantic = _semantic(name)
        mesh_index = node.get("mesh")
        used: set[int] = set()
        if isinstance(mesh_index, int) and 0 <= mesh_index < len(meshes):
            for primitive in meshes[mesh_index].get("primitives") or []:
                mat = primitive.get("material")
                if isinstance(mat, int):
                    used.add(mat)
                    material_usage[mat].append(name)
                    semantic_materials[semantic].add(mat)
        node_rows.append({"index": idx, "name": name, "semantic": semantic, "mesh": mesh_index, "materials": sorted(used)})

    material_rows = []
    for idx, material in enumerate(materials):
        pbr = material.get("pbrMetallicRoughness") or {}
        base_tex = (pbr.get("baseColorTexture") or {}).get("index")
        material_rows.append({
            "index": idx,
            "name": str(material.get("name") or f"material_{idx}"),
            "base_color_factor": pbr.get("baseColorFactor"),
            "base_color_texture": base_tex,
            "node_count": len(set(material_usage.get(idx, []))),
            "nodes": sorted(set(material_usage.get(idx, []))),
        })

    joints = sorted({int(j) for skin in skins for j in (skin.get("joints") or [])})
    joint_names = [str(nodes[j].get("name") or f"node_{j}") for j in joints if 0 <= j < len(nodes)]
    semantic_nodes = defaultdict(list)
    for row in node_rows:
        semantic_nodes[row["semantic"]].append(row["name"])

    shared_hair_ear_material = bool(
        set(semantic_materials.get("hair", set())) & set(semantic_materials.get("ears", set()))
    )
    rig_ready_basic = bool(skins and joints)
    finger_nodes = semantic_nodes.get("fingers", [])
    hand_nodes = semantic_nodes.get("hands", [])

    result = {
        "file": str(path),
        "counts": {
            "nodes": len(nodes), "meshes": len(meshes), "materials": len(materials),
            "textures": len(textures), "images": len(images), "skins": len(skins),
            "joints": len(joints), "animations": len(animations),
        },
        "materials": {
            "rows": material_rows,
            "semantic_material_indices": {k: sorted(v) for k, v in semantic_materials.items()},
            "hair_and_explicit_ears_share_material": shared_hair_ear_material,
            "all_primitives_have_material": all(
                isinstance(primitive.get("material"), int)
                for mesh in meshes for primitive in (mesh.get("primitives") or [])
            ),
        },
        "rig": {
            "basic_skin_present": rig_ready_basic,
            "joint_names": joint_names,
            "animations": [str(a.get("name") or f"animation_{i}") for i, a in enumerate(animations)],
            "separate_hand_nodes": hand_nodes,
            "separate_finger_nodes": finger_nodes,
            "hair_nodes": semantic_nodes.get("hair", []),
            "ear_nodes": semantic_nodes.get("ears", []),
        },
        "nodes": node_rows,
        "learning": {
            "materials": [
                "Separar error geométrico de error de atlas/UV antes de recolorear.",
                "Si orejas correctas están embebidas en la malla principal, un cambio de material por nodo no basta: localizar UV/polígonos primero.",
            ],
            "rig": [
                "No declarar rig-ready si no existe skin/joints o si manos/dedos no tienen topología deformable comprobada.",
                "Pelo, ojos, boca y dedos deben conservar separabilidad o pesos controlables para animación.",
            ],
        },
    }
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="Probe GLB: materiales/UV lógico y rig readiness")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = probe(args.input, args.output)
    print(json.dumps({"counts": result["counts"], "materials": result["materials"], "rig": result["rig"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
