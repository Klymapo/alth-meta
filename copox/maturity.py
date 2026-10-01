from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

LEVELS = ("M0", "M1", "M2", "M3", "M4", "M5")
LEVEL_INDEX = {name: idx for idx, name in enumerate(LEVELS)}

# La madurez se calcula por capacidades reales, no por una etiqueta escrita a mano.
# M0: sin cobertura
# M1: observable
# M2: auditable
# M3: editable
# M4: aprendizaje/regresión
# M5: persistencia + gate de promoción seguro
REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "M0": (),
    "M1": ("evidence",),
    "M2": ("evidence", "auditor"),
    "M3": ("evidence", "auditor", "mutator"),
    "M4": ("evidence", "auditor", "mutator", "learning", "regression"),
    "M5": ("evidence", "auditor", "mutator", "learning", "regression", "persistence", "loop_gate"),
}


def _read(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compute_level(capabilities: dict[str, Any]) -> str:
    achieved = "M0"
    for level in LEVELS[1:]:
        if all(bool(capabilities.get(name, False)) for name in REQUIREMENTS[level]):
            achieved = level
        else:
            break
    return achieved


def next_missing(capabilities: dict[str, Any], level: str) -> list[str]:
    idx = LEVEL_INDEX[level]
    if idx >= LEVEL_INDEX["M5"]:
        return []
    target = LEVELS[idx + 1]
    return [name for name in REQUIREMENTS[target] if not bool(capabilities.get(name, False))]


def _apply_production_policy(modules: list[dict[str, Any]], policy: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not policy:
        return modules
    registered = set((policy.get("modules") or {}).keys())
    result: list[dict[str, Any]] = []
    for raw in modules:
        module = dict(raw)
        caps = dict(module.get("capabilities", {}))
        # El gate universal sólo completa M5 cuando M4 y persistencia ya existían.
        m4_ready = all(bool(caps.get(name, False)) for name in REQUIREMENTS["M4"])
        if module.get("id") in registered and m4_ready and bool(caps.get("persistence", False)):
            caps["loop_gate"] = True
            processes = dict(module.get("processes", {}))
            processes["production_gate"] = "copox.production.module_gate + policy"
            module["processes"] = processes
        module["capabilities"] = caps
        result.append(module)
    return result


def assess_module(module: dict[str, Any]) -> dict[str, Any]:
    caps = dict(module.get("capabilities", {}))
    level = compute_level(caps)
    declared = module.get("declared_level")
    declared_ok = declared is None or LEVEL_INDEX.get(str(declared), -1) <= LEVEL_INDEX[level]
    return {
        "id": str(module["id"]),
        "label": str(module.get("label", module["id"])),
        "domain": str(module.get("domain", "unknown")),
        "critical": bool(module.get("critical", False)),
        "priority": int(module.get("priority", 100)),
        "computed_level": level,
        "declared_level": declared,
        "declared_level_valid": declared_ok,
        "capabilities": caps,
        "missing_for_next_level": next_missing(caps, level),
        "learning_questions": list(module.get("learning_questions", [])),
        "signals": list(module.get("signals", [])),
        "processes": dict(module.get("processes", {})),
    }


def assess_coverage(
    path: str | Path,
    min_level: str = "M4",
    critical_only: bool = True,
    production_policy: str | Path | dict[str, Any] | None = None,
) -> dict[str, Any]:
    if min_level not in LEVEL_INDEX:
        raise ValueError(f"Nivel de madurez inválido: {min_level}")
    data = _read(path)
    if isinstance(production_policy, (str, Path)):
        policy = _read(production_policy)
        policy_path = str(production_policy)
    elif isinstance(production_policy, dict):
        policy = production_policy
        policy_path = "<dict>"
    else:
        policy = None
        policy_path = None

    raw_modules = list(data.get("modules", []))
    if policy:
        ids = {str(x.get("id")) for x in raw_modules}
        registered = set((policy.get("modules") or {}).keys())
        unknown = sorted(registered - ids)
        if unknown:
            raise ValueError(f"Policy contiene módulos desconocidos: {unknown}")
        missing_policy = sorted({str(x.get("id")) for x in raw_modules if x.get("critical", False)} - registered)
        if missing_policy:
            raise ValueError(f"Policy no cubre módulos críticos: {missing_policy}")
    raw_modules = _apply_production_policy(raw_modules, policy)
    modules = [assess_module(x) for x in raw_modules]
    if not modules:
        raise ValueError(f"Coverage sin modules: {path}")
    considered = [m for m in modules if (m["critical"] or not critical_only)]
    blockers = [m for m in considered if LEVEL_INDEX[m["computed_level"]] < LEVEL_INDEX[min_level] or not m["declared_level_valid"]]
    ordered = sorted(modules, key=lambda m: (LEVEL_INDEX[m["computed_level"]], m["priority"], m["id"]))
    return {
        "id": data.get("id", Path(path).stem),
        "target": data.get("target"),
        "kind": data.get("kind"),
        "minimum_level": min_level,
        "critical_only": critical_only,
        "ready": not blockers,
        "production_policy": policy_path,
        "modules": modules,
        "blockers": blockers,
        "learning_backlog": [
            {
                "module": m["id"],
                "label": m["label"],
                "level": m["computed_level"],
                "next_missing": m["missing_for_next_level"],
                "questions": m["learning_questions"],
                "signals": m["signals"],
            }
            for m in ordered
            if m["computed_level"] != "M5"
        ],
        "summary": {level: sum(1 for m in modules if m["computed_level"] == level) for level in LEVELS},
    }


def cassette_maturity(cassette: dict[str, Any], repo_root: str | Path = ".") -> dict[str, Any] | None:
    cfg = cassette.get("maturity")
    if not cfg:
        return None
    coverage = Path(str(cfg["coverage"]))
    root = Path(repo_root).resolve()
    if not coverage.is_absolute():
        coverage = root / coverage
    production_policy = cfg.get("production_policy")
    if production_policy:
        production_policy = Path(str(production_policy))
        if not production_policy.is_absolute():
            production_policy = root / production_policy
    result = assess_coverage(
        coverage,
        min_level=str(cfg.get("min_level", "M4")),
        critical_only=bool(cfg.get("critical_only", True)),
        production_policy=production_policy,
    )
    result["coverage_path"] = str(coverage)
    result["block_execution"] = bool(cfg.get("block_execution", True))
    return result


def write_report(result: dict[str, Any], path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# COPOX Maturity · {result['id']}",
        "",
        f"Ready: **{result['ready']}** · mínimo {result['minimum_level']} · critical_only={result['critical_only']}",
        "",
        "| Módulo | Dominio | Crítico | Nivel | Falta para siguiente |",
        "|---|---|---:|---:|---|",
    ]
    for m in sorted(result["modules"], key=lambda x: (x["priority"], x["id"])):
        missing = ", ".join(m["missing_for_next_level"]) or "—"
        lines.append(f"| {m['label']} | {m['domain']} | {'sí' if m['critical'] else 'no'} | {m['computed_level']} | {missing} |")
    if result["blockers"]:
        lines += ["", "## Bloqueos", ""]
        for m in result["blockers"]:
            lines.append(f"- **{m['label']}** ({m['computed_level']}): {', '.join(m['missing_for_next_level']) or 'nivel insuficiente'}")
    if result["learning_backlog"]:
        lines += ["", "## Learning backlog", ""]
        for item in result["learning_backlog"]:
            lines.append(f"### {item['label']} · {item['level']}")
            for q in item["questions"]:
                lines.append(f"- {q}")
            if not item["questions"]:
                lines.append("- Definir preguntas de diagnóstico antes de subir de nivel.")
            lines.append("")
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="COPOX maturity M0-M5")
    p.add_argument("coverage")
    p.add_argument("--min-level", default="M4", choices=LEVELS)
    p.add_argument("--production-policy")
    p.add_argument("--all-modules", action="store_true", help="Evalúa también módulos no críticos")
    p.add_argument("--output")
    p.add_argument("--check", action="store_true", help="Devuelve 4 si la cobertura no alcanza el mínimo")
    args = p.parse_args()
    result = assess_coverage(
        args.coverage,
        args.min_level,
        critical_only=not args.all_modules,
        production_policy=args.production_policy,
    )
    if args.output:
        write_report(result, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.check and not result["ready"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
