from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description="Genera reporte visible sólo para un ganador promovido")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--candidate-dir", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--title", default="COPOX · resultado aprobado")
    args = p.parse_args()

    run_dir = Path(args.run_dir)
    candidate_dir = Path(args.candidate_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    candidate = json.loads((candidate_dir / "candidate.json").read_text(encoding="utf-8"))

    if manifest.get("status") not in {"APPROVED_INTERNAL", "PROMOTED"}:
        raise SystemExit("El manifiesto no está aprobado/promovido: no se publica reporte")
    if candidate.get("status") != "ELIGIBLE":
        raise SystemExit("El candidato no obtuvo unanimidad: no se publica reporte")
    audit = candidate.get("audit", [])
    applicable = [x for x in audit if str(x.get("status", "")).upper() != "N-A"]
    if not applicable or any(str(x.get("status", "")).upper() != "PASS" for x in applicable):
        raise SystemExit("No hay unanimidad de auditores: no se publica reporte")

    evidence = sorted((candidate_dir / "evidence").glob("*"))
    captures = [x for x in evidence if x.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if not captures:
        raise SystemExit("No existe captura: no se publica reporte")

    lines = [
        f"# {args.title}",
        "",
        f"- Run: `{manifest.get('run_id')}`",
        f"- Cassette: `{manifest.get('cassette')}`",
        f"- Target: `{manifest.get('target')}`",
        f"- Baseline: `{manifest.get('baseline')}`",
        f"- Ganador: `{manifest.get('winner')}`",
        f"- Auditores aplicables: **{len(applicable)}/{len(applicable)} PASS**",
        "",
        "## Auditoría",
        "",
    ]
    for item in audit:
        lines.append(f"- **{item.get('id')}**: {item.get('status')} — {item.get('feedback', item.get('reason', ''))}")
    lines.extend(["", "## Capturas", ""])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    for image in captures:
        rel = image.relative_to(out.parent) if image.is_relative_to(out.parent) else image
        lines.append(f"![{image.stem}]({rel.as_posix()})")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
