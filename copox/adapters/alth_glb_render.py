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
    rotation = Matrix.Rotation(math.radians(90.0), 4, "X")
    for root in roots:
        root.matrix_world = rotation @ root.matrix_world
    bpy.context.view_layer.update()

    objs = [o for o in imported if o.type == "MESH"]
    if not objs:
        raise RuntimeError("El GLB importado no contiene mallas")
    mn, mx = alth._limites(objs)
    dims = mx - mn
    orientation_ok = bool(dims.z > dims.y * 1.25)
    if not orientation_ok:
        raise RuntimeError(f"Orientación inválida para cámaras ALTH: W={dims.x} D={dims.y} H={dims.z}")

    alth.estudio()
    out = Path(args.output_dir)
    report = alth.revisar(objs, out, modo="iteracion", titulo=args.title, asset=None)
    report["orientation"] = {
        "ok": orientation_ok,
        "correction": "rotate_x_+90deg_glb_yup_to_alth_zup",
        "bounds": {"W": float(dims.x), "D": float(dims.y), "H": float(dims.z)},
    }
    (out / "reporte.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
