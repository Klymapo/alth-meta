from __future__ import annotations

import argparse
import json
from pathlib import Path

from copox.contracts import ContractError, load_cassette


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default="copox/cassettes/enabled")
    p.add_argument("--include-blocked", action="store_true")
    args = p.parse_args()
    root = Path(args.dir)
    items: list[str] = []
    blocked: list[dict[str, object]] = []
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        normalized = str(path).replace("\\", "/")
        try:
            cassette = load_cassette(path)
        except ContractError as exc:
            blocked.append({"path": normalized, "reason": "contract", "detail": str(exc)})
            continue
        maturity = cassette.maturity
        if maturity is not None and maturity.get("block_execution", True) and not maturity.get("ready", False):
            blocked.append({
                "path": normalized,
                "reason": "maturity",
                "blockers": [f"{x['id']}:{x['computed_level']}" for x in maturity.get("blockers", [])],
            })
            if not args.include_blocked:
                continue
        items.append(normalized)
    if blocked:
        print("[copox] blocked=" + json.dumps(blocked, ensure_ascii=False, separators=(",", ":")), file=__import__("sys").stderr)
    print(json.dumps(items, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
