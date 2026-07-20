import json
from pathlib import Path

from copilot_agent_contracts.cli import main

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = REPOSITORY_ROOT / "examples" / "customer-support" / "agent-contracts.toml"


def test_check_command_returns_zero_for_example(capsys) -> None:
    exit_code = main(["check", "--config", str(EXAMPLE_CONFIG), "--verbose"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Checks: 7" in output
    assert "Failed: 0" in output


def test_check_command_outputs_json(capsys) -> None:
    exit_code = main(["check", "--config", str(EXAMPLE_CONFIG), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["passed"] is True


def test_init_refuses_to_replace_without_force(tmp_path: Path, capsys) -> None:
    destination = tmp_path / "contracts.toml"
    assert main(["init", "--config", str(destination)]) == 0

    exit_code = main(["init", "--config", str(destination)])

    assert exit_code == 2
    assert "refusing to replace" in capsys.readouterr().err


def test_configuration_error_returns_two(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.toml"

    exit_code = main(["check", "--config", str(missing)])

    assert exit_code == 2
    assert "Configuration error" in capsys.readouterr().err
