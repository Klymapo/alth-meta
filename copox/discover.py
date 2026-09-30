from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="copox/cassettes/enabled")
    args = p.parse_args()
    root = Path(args.dir)
    items = sorted(str(x).replace("\\", "/") for x in root.glob("*.json")) if root.exists() else []
    print(json.dumps(items, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
