from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bpy  # noqa: E402
import alth  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Render headless de un GLB para evidencia COPOX")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--title", default="COPOX · GLB candidate")
    args = p.parse_args()

    alth.nueva_escena()
    bpy.ops.import_scene.gltf(filepath=str(Path(args.input).resolve()))
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise RuntimeError("El GLB importado no contiene mallas")
    alth.estudio()
    alth.revisar(objs, Path(args.output_dir), modo="iteracion", titulo=args.title, asset=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
