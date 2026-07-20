from pathlib import Path

import pytest

from copilot_agent_contracts.config import ConfigError, load_config, require_string, string_list


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_uses_root_override(tmp_path: Path) -> None:
    configured = tmp_path / "configured"
    override = tmp_path / "override"
    configured.mkdir()
    override.mkdir()
    config = _write(
        tmp_path / "contracts.toml",
        """version = 1
[project]
root = "configured"
[[checks]]
id = "sections"
type = "sections"
files = ["*.md"]
""",
    )

    loaded = load_config(config, override)

    assert loaded.root == override.resolve()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not valid toml =", "cannot read"),
        ('version = 1\nproject = "wrong"\n[[checks]]\nid="x"\ntype="sections"\n', "table"),
        ("version=1\n[project]\nroot=3\n[[checks]]\nid='x'\ntype='sections'\n", "string"),
        (
            "version=1\n[project]\nroot='missing'\n[[checks]]\nid='x'\ntype='sections'\n",
            "not a directory",
        ),
        ("version=1\nchecks=['wrong']\n", "TOML table"),
        ("version=1\n[[checks]]\ntype='sections'\n", "non-empty id"),
    ],
)
def test_load_config_reports_structural_errors(tmp_path: Path, content: str, message: str) -> None:
    config = _write(tmp_path / "contracts.toml", content)

    with pytest.raises(ConfigError, match=message):
        load_config(config)


def test_require_string_accepts_and_rejects_values() -> None:
    assert require_string({"id": "x", "field": " value "}, "field") == " value "

    with pytest.raises(ConfigError, match="non-empty string"):
        require_string({"id": "x", "field": ""}, "field")


@pytest.mark.parametrize("value", [None, "wrong", ["ok", 3]])
def test_string_list_rejects_non_string_arrays(value: object) -> None:
    with pytest.raises(ConfigError, match="array of strings"):
        string_list({"id": "x", "field": value}, "field")


def test_string_list_handles_optional_and_required_values() -> None:
    check = {"id": "x"}
    assert string_list(check, "field") == []
    assert string_list({"id": "x", "field": ["a"]}, "field", required=True) == ["a"]

    with pytest.raises(ConfigError, match="is required"):
        string_list(check, "field", required=True)
    with pytest.raises(ConfigError, match="must not be empty"):
        string_list({"id": "x", "field": []}, "field", required=True)
