"""Static contract tests for GitHub Copilot agent customizations."""

from copilot_agent_contracts.engine import run_contracts
from copilot_agent_contracts.model import CheckResult, Finding, Report

__all__ = ["CheckResult", "Finding", "Report", "run_contracts"]
__version__ = "0.1.0"
