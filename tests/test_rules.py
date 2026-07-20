from pathlib import Path

import pytest

from copilot_agent_contracts.config import ConfigError
from copilot_agent_contracts.rules import (
    check_contains,
    check_forbid,
    check_frontmatter,
    check_precedence,
    check_routing,
    check_sections,
)


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_frontmatter_reports_missing_unknown_and_forbidden_keys(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/agents/demo.agent.md",
        "---\nname: Demo\ninfer: false\nextra: value\n---\n",
    )
    check = {
        "id": "frontmatter",
        "type": "frontmatter",
        "files": [".github/agents/*.agent.md"],
        "required": ["description"],
        "allowed": ["name", "description", "infer"],
        "forbidden": ["infer"],
    }

    result = check_frontmatter(tmp_path, check)

    messages = {finding.message for finding in result.findings}
    assert "missing required frontmatter key: description" in messages
    assert "frontmatter key is not allowed: extra" in messages
    assert "forbidden frontmatter key: infer" in messages


def test_sections_support_literal_and_regex_requirements(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "# Demo\n## Constraints\n")
    check = {
        "id": "sections",
        "type": "sections",
        "files": ["agent.md"],
        "required": ["Constraints", "Approach"],
        "required_regex": [r"^Output"],
    }

    result = check_sections(tmp_path, check)

    assert [finding.message for finding in result.findings] == [
        "missing required section: Approach",
        "no section heading matches required pattern: ^Output",
    ]


def test_contains_can_scope_required_text_to_a_section(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "## Constraints\nSafe\n## Notes\nRequired elsewhere\n")
    check = {
        "id": "contains",
        "type": "contains",
        "files": ["agent.md"],
        "under_section": "Constraints",
        "required": ["Required elsewhere"],
    }

    result = check_contains(tmp_path, check)

    assert len(result.findings) == 1
    assert "missing required text" in result.findings[0].message


def test_forbid_only_scans_selected_fence_language_and_section(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "prompt.md",
        """## Notes
```json
{"approved": true}
```
## Examples
```text
{"approved": true}
```
```json
{"approved": true}
```
""",
    )
    check = {
        "id": "forbid",
        "type": "forbid",
        "files": ["prompt.md"],
        "under_section": "Examples",
        "fence_language": "json",
        "patterns": [r'"approved"\s*:\s*true'],
    }

    result = check_forbid(tmp_path, check)

    assert len(result.findings) == 1
    assert result.findings[0].line == 10


def test_no_file_match_is_a_contract_failure(tmp_path: Path) -> None:
    result = check_sections(
        tmp_path,
        {"id": "missing", "type": "sections", "files": ["*.md"], "required": []},
    )

    assert not result.passed
    assert "matched no files" in result.findings[0].message


def test_invalid_regex_is_configuration_error(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "text")

    with pytest.raises(ConfigError, match="invalid forbidden regex"):
        check_forbid(
            tmp_path,
            {"id": "bad", "type": "forbid", "files": ["agent.md"], "patterns": ["["]},
        )


def test_routing_reports_a_wrong_winner(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.md",
        """## Routing
| Route | Keywords |
| --- | --- |
| Billing | refund, charge |
| Technical | error, crash |
""",
    )
    _write(
        tmp_path,
        "cases.jsonl",
        '{"id":"wrong","input":"refund please","expected":"Technical"}\n',
    )
    check = {
        "id": "routing",
        "type": "routing",
        "file": "agent.md",
        "section": "Routing",
        "route_column": "Route",
        "keywords_column": "Keywords",
        "cases": "cases.jsonl",
    }

    result = check_routing(tmp_path, check)

    assert len(result.findings) == 1
    assert "routed to 'Billing'" in result.findings[0].message


def test_precedence_uses_documented_order_for_overlapping_triggers(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.md",
        """## Mode precedence
1. **Specific**
2. **General**
""",
    )
    _write(
        tmp_path,
        "cases.jsonl",
        '{"id":"overlap","input":"specific request","expected":"Specific"}\n',
    )
    check = {
        "id": "precedence",
        "type": "precedence",
        "file": "agent.md",
        "section": "Mode precedence",
        "order": ["Specific", "General"],
        "cases": "cases.jsonl",
        "modes": [
            {"name": "Specific", "patterns": ["specific"]},
            {"name": "General", "patterns": [".*"]},
        ],
    }

    result = check_precedence(tmp_path, check)

    assert result.passed


def test_precedence_reports_document_order_drift(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "agent.md",
        """## Mode precedence
1. **General**
2. **Specific**
""",
    )
    check = {
        "id": "precedence",
        "type": "precedence",
        "file": "agent.md",
        "section": "Mode precedence",
        "order": ["Specific", "General"],
    }

    result = check_precedence(tmp_path, check)

    assert any("precedence order" in finding.message for finding in result.findings)
