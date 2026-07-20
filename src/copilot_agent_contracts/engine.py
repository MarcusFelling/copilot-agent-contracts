"""Contract evaluation engine."""

from __future__ import annotations

from copilot_agent_contracts.config import ContractConfig
from copilot_agent_contracts.model import Report
from copilot_agent_contracts.rules import RULES


def run_contracts(config: ContractConfig) -> Report:
    """Run every configured check and return an aggregate report."""
    results = tuple(RULES[check["type"]](config.root, check) for check in config.checks)
    return Report(
        config_path=config.path.as_posix(),
        root=config.root.as_posix(),
        results=results,
    )
