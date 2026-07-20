from pathlib import Path

from copilot_agent_contracts.config import load_config
from copilot_agent_contracts.engine import run_contracts

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPOSITORY_ROOT / "examples" / "customer-support"


def test_customer_support_example_passes_all_contracts() -> None:
    config = load_config(EXAMPLE / "agent-contracts.toml")

    report = run_contracts(config)

    assert report.passed
    assert len(report.results) == 7
    assert not report.findings


def test_report_serializes_summary() -> None:
    config = load_config(EXAMPLE / "agent-contracts.toml")

    payload = run_contracts(config).to_dict()

    assert payload["passed"] is True
    assert payload["summary"] == {
        "checks": 7,
        "passed": 7,
        "failed": 0,
        "findings": 0,
    }
