"""Load and validate TOML contract configurations."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CHECK_TYPES = {
    "contains",
    "forbid",
    "frontmatter",
    "precedence",
    "routing",
    "sections",
}


class ConfigError(ValueError):
    """Raised when a contract configuration cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class ContractConfig:
    """Validated project configuration."""

    path: Path
    root: Path
    checks: tuple[dict[str, Any], ...]


def load_config(path: Path, root_override: Path | None = None) -> ContractConfig:
    """Read a version 1 contract configuration."""
    config_path = path.resolve()
    if not config_path.is_file():
        raise ConfigError(f"configuration file not found: {path}")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc

    version = data.get("version")
    if version != 1:
        raise ConfigError(f"unsupported configuration version {version!r}; expected 1")

    project = data.get("project", {})
    if not isinstance(project, dict):
        raise ConfigError("[project] must be a TOML table")

    configured_root = project.get("root", ".")
    if not isinstance(configured_root, str):
        raise ConfigError("project.root must be a string")
    root = (
        root_override.resolve()
        if root_override is not None
        else (config_path.parent / configured_root).resolve()
    )
    if not root.is_dir():
        raise ConfigError(f"project root is not a directory: {root}")

    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise ConfigError("configuration must define at least one [[checks]] table")

    checks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_check in enumerate(raw_checks, 1):
        if not isinstance(raw_check, dict):
            raise ConfigError(f"checks entry {index} must be a TOML table")
        check = dict(raw_check)
        check_id = check.get("id")
        check_type = check.get("type")
        if not isinstance(check_id, str) or not check_id.strip():
            raise ConfigError(f"checks entry {index} needs a non-empty id")
        if check_id in seen_ids:
            raise ConfigError(f"duplicate check id: {check_id}")
        seen_ids.add(check_id)
        if check_type not in SUPPORTED_CHECK_TYPES:
            supported = ", ".join(sorted(SUPPORTED_CHECK_TYPES))
            raise ConfigError(
                f"check {check_id!r} has unsupported type {check_type!r}; "
                f"expected one of {supported}"
            )
        checks.append(check)

    return ContractConfig(path=config_path, root=root, checks=tuple(checks))


def require_string(check: dict[str, Any], key: str) -> str:
    """Return a required non-empty string from a check."""
    value = check.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"check {check['id']!r}: {key} must be a non-empty string")
    return value


def string_list(check: dict[str, Any], key: str, *, required: bool = False) -> list[str]:
    """Return and validate a list of strings from a check."""
    if key not in check:
        if required:
            raise ConfigError(f"check {check['id']!r}: {key} is required")
        return []
    value = check[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"check {check['id']!r}: {key} must be an array of strings")
    if required and not value:
        raise ConfigError(f"check {check['id']!r}: {key} must not be empty")
    return list(value)
