from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


REQUIRED_TOP_LEVEL = {
    "id",
    "kind",
    "profile",
    "target",
    "baseline",
    "strategy",
    "commands",
    "promotion",
    "reporting",
}


@dataclass(frozen=True)
class Cassette:
    path: Path
    data: dict[str, Any]
    profile: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def kind(self) -> str:
        return str(self.data["kind"])

    @property
    def tournament_size(self) -> int:
        return int(self.data["strategy"].get("tournament_size", 3))

    @property
    def max_candidates(self) -> int:
        return int(self.data["strategy"].get("max_candidates", 6))

    @property
    def unanimity_required(self) -> bool:
        return bool(self.data["promotion"].get("unanimous", True))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"No existe: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"JSON inválido en {path}: {exc}") from exc


def load_cassette(path: str | Path, repo_root: str | Path = ".") -> Cassette:
    repo_root = Path(repo_root).resolve()
    path = Path(path)
    if not path.is_absolute():
        path = repo_root / path
    data = _load_json(path)

    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        raise ContractError(f"Cassette sin campos obligatorios: {', '.join(missing)}")

    profile_path = Path(str(data["profile"]))
    if not profile_path.is_absolute():
        profile_path = repo_root / profile_path
    profile = _load_json(profile_path)

    strategy = data.get("strategy", {})
    tournament_size = int(strategy.get("tournament_size", 3))
    max_candidates = int(strategy.get("max_candidates", 6))
    if tournament_size < 1:
        raise ContractError("strategy.tournament_size debe ser >= 1")
    if max_candidates < tournament_size:
        raise ContractError("strategy.max_candidates no puede ser menor que tournament_size")

    if data.get("promotion", {}).get("unanimous") is not True:
        raise ContractError("COPOX v1 exige promotion.unanimous=true")

    auditors = profile.get("auditors", [])
    if not auditors:
        raise ContractError("El perfil debe declarar al menos un auditor")
    for auditor in auditors:
        if not auditor.get("id"):
            raise ContractError("Cada auditor necesita id")
        if auditor.get("applicable", True) and "command" not in auditor:
            raise ContractError(f"Auditor {auditor['id']} no tiene command")

    required_evidence = data.get("reporting", {}).get("required_evidence", [])
    if not required_evidence:
        raise ContractError("reporting.required_evidence no puede estar vacío")

    return Cassette(path=path, data=data, profile=profile)
