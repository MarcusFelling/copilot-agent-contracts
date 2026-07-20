"""Result types returned by contract checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Finding:
    """One contract violation."""

    check_id: str
    path: str
    message: str
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "check": self.check_id,
            "path": self.path,
            "message": self.message,
        }
        if self.line is not None:
            result["line"] = self.line
        return result


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one configured check."""

    check_id: str
    check_type: str
    inspected: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "type": self.check_type,
            "passed": self.passed,
            "inspected": self.inspected,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True, slots=True)
class Report:
    """Aggregate result for one contract configuration."""

    config_path: str
    root: str
    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(finding for result in self.results for finding in result.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "config": self.config_path,
            "root": self.root,
            "summary": {
                "checks": len(self.results),
                "passed": sum(result.passed for result in self.results),
                "failed": sum(not result.passed for result in self.results),
                "findings": len(self.findings),
            },
            "results": [result.to_dict() for result in self.results],
        }
