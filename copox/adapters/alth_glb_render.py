from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402
import alth  # noqa: E402

HAIR_PREFIXES = ("Fleco_", "Mechon_", "Capa_", "Corona_")


def main() -> int:
    p = argparse.ArgumentParser(description="Render headless de un GLB para evidencia COPOX")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--title", default="COPOX · GLB candidate")
    args = p.parse_args()

    alth.nueva_escena()
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    imported = list(bpy.context.scene.objects)
    roots = [o for o in imported if o.parent is None]

    # El GLB aprobado entra en Blender con el eje longitudinal sobre -Y.
    # -90° X lo lleva a +Z y conserva la convención ALTH de personaje de pie.
    rotation = Matrix.Rotation(math.radians(-90.0), 4, "X")
    for root in roots:
        root.matrix_world = rotation @ root.matrix_world
    bpy.context.view_layer.update()

    objs = [o for o in imported if o.type == "MESH"]
    if not objs:
        raise RuntimeError("El GLB importado no contiene mallas")
    mn, mx = alth._limites(objs)
    dims = mx - mn

    hair = [o for o in objs if o.name.startswith(HAIR_PREFIXES)]
    if not hair:
        raise RuntimeError("No se detectaron grupos semánticos de cabello para validar orientación")
    hair_mn, hair_mx = alth._limites(hair)
    hair_center_z = float((hair_mn.z + hair_mx.z) / 2.0)
    body_center_z = float((mn.z + mx.z) / 2.0)
    vertical_ok = bool(dims.z > dims.y * 1.25)
    hair_above_body = bool(hair_center_z > body_center_z + float(dims.z) * 0.15)
    orientation_ok = bool(vertical_ok and hair_above_body)
    if not orientation_ok:
        raise RuntimeError(
            "Orientación inválida para cámaras ALTH: "
            f"W={dims.x} D={dims.y} H={dims.z} hair_z={hair_center_z} body_z={body_center_z}"
        )

    alth.estudio()
    out = Path(args.output_dir)
    report = alth.revisar(objs, out, modo="iteracion", titulo=args.title, asset=None)
    report["orientation"] = {
        "ok": orientation_ok,
        "vertical_ok": vertical_ok,
        "hair_above_body": hair_above_body,
        "correction": "rotate_x_-90deg_glb_to_alth_zup",
        "bounds": {"W": float(dims.x), "D": float(dims.y), "H": float(dims.z)},
        "hair_center_z": hair_center_z,
        "body_center_z": body_center_z,
    }
    (out / "reporte.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
