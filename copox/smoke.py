from __future__ import annotations

import argparse
import json
import struct
import zlib
from pathlib import Path


def png(path: Path, rgb: tuple[int, int, int]) -> None:
    width = height = 32
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    blob = b"\x89PNG\r\n\x1a\n"
    blob += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    blob += chunk(b"IDAT", zlib.compress(raw))
    blob += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def capture(candidate_dir: Path, candidate_id: str) -> None:
    # t01-c01 falla deliberadamente; los demás pasan para demostrar torneo + veto.
    passing = not candidate_id.endswith("c01")
    score = 0.91 if candidate_id.endswith("c02") else 0.95
    metrics = {
        "smoke": {
            "build_ok": True,
            "quality_ok": passing,
            "score": score,
        },
        "learning": {"ready_to_promote": passing},
    }
    (candidate_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    color = (80, 180, 100) if passing else (180, 80, 80)
    png(candidate_dir / "evidence" / "capture.png", color)


def promote(candidate_dir: Path) -> None:
    (candidate_dir / "PROMOTED").write_text("ok\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["capture", "promote"])
    p.add_argument("--candidate-dir", required=True)
    p.add_argument("--candidate-id", default="")
    args = p.parse_args()
    candidate_dir = Path(args.candidate_dir)
    candidate_dir.mkdir(parents=True, exist_ok=True)
    if args.phase == "capture":
        capture(candidate_dir, args.candidate_id)
    else:
        promote(candidate_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
