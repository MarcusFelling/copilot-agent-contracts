import runpy
import sys
from pathlib import Path

import pytest

from copilot_agent_contracts.cli import _github_annotation, main
from copilot_agent_contracts.model import Finding


def _failing_config(tmp_path: Path) -> Path:
    (tmp_path / "agent.md").write_text("# Agent\n", encoding="utf-8")
    config = tmp_path / "contracts.toml"
    config.write_text(
        """version = 1
[[checks]]
id = "required-section"
type = "sections"
files = ["agent.md"]
required = ["Constraints"]
""",
        encoding="utf-8",
    )
    return config


def test_text_output_returns_one_for_contract_findings(tmp_path: Path, capsys) -> None:
    exit_code = main(["check", "--config", str(_failing_config(tmp_path))])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL required-section" in output
    assert "agent.md: missing required section" in output


def test_github_output_annotates_failure(tmp_path: Path, capsys) -> None:
    exit_code = main(["check", "--config", str(_failing_config(tmp_path)), "--format", "github"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "::error file=agent.md,title=required-section::" in output
    assert "Contracts failed" in output


def test_github_annotation_escapes_command_data() -> None:
    finding = Finding("check,one", "folder:file.md", "bad%value\nnext", 4)

    annotation = _github_annotation(finding)

    assert "file=folder%3Afile.md" in annotation
    assert "title=check%2Cone" in annotation
    assert "line=4" in annotation
    assert "bad%25value%0Anext" in annotation


def test_init_force_replaces_existing_configuration(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "contracts.toml"
    destination.parent.mkdir()
    destination.write_text("old", encoding="utf-8")

    exit_code = main(["init", "--config", str(destination), "--force"])

    assert exit_code == 0
    assert destination.read_text(encoding="utf-8").startswith("version = 1")


def test_module_entry_point_shows_version(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["copilot_agent_contracts", "--version"])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("copilot_agent_contracts.__main__", run_name="__main__")

    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
