from pathlib import Path

import pytest

from copilot_agent_contracts.config import ConfigError, load_config


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_resolves_root_from_config_location(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = _write(
        tmp_path / "contracts.toml",
        """version = 1
[project]
root = "project"
[[checks]]
id = "headings"
type = "sections"
files = ["*.md"]
required = ["Test"]
""",
    )

    loaded = load_config(config)

    assert loaded.root == project.resolve()
    assert loaded.checks[0]["id"] == "headings"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("version = 2\n[[checks]]\nid='x'\ntype='sections'\n", "unsupported"),
        ("version = 1\n", "at least one"),
        (
            "version=1\n[[checks]]\nid='x'\ntype='sections'\n[[checks]]\nid='x'\ntype='sections'\n",
            "duplicate",
        ),
        ("version=1\n[[checks]]\nid='x'\ntype='unknown'\n", "unsupported type"),
    ],
)
def test_load_config_rejects_invalid_contracts(tmp_path: Path, content: str, message: str) -> None:
    config = _write(tmp_path / "contracts.toml", content)

    with pytest.raises(ConfigError, match=message):
        load_config(config)
