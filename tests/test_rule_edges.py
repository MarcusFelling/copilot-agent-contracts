import json
from pathlib import Path
from typing import Any

import pytest

from copilot_agent_contracts.config import ConfigError
from copilot_agent_contracts.rules import (
    _display_path,
    _expand_files,
    _load_jsonl,
    _parse_precedence_labels,
    _route,
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


def _routing_check(**overrides: Any) -> dict[str, Any]:
    check: dict[str, Any] = {
        "id": "routing",
        "type": "routing",
        "file": "agent.md",
        "section": "Routing",
        "route_column": "Route",
        "keywords_column": "Keywords",
        "cases": "cases.jsonl",
    }
    check.update(overrides)
    return check


def _precedence_check(**overrides: Any) -> dict[str, Any]:
    check: dict[str, Any] = {
        "id": "precedence",
        "type": "precedence",
        "file": "agent.md",
        "section": "Mode precedence",
        "order": ["Specific", "General"],
    }
    check.update(overrides)
    return check


def _write_routing_source(root: Path, rows: str | None = None) -> None:
    rows = rows or "| A | foo, blue |\n| B | foo, bar |"
    _write(
        root,
        "agent.md",
        "## Routing\n| Route | Keywords |\n| --- | --- |\n" + rows + "\n",
    )


def _write_precedence_source(root: Path, body: str | None = None) -> None:
    body = body or "1. **Specific**\n2. **General**"
    _write(root, "agent.md", "## Mode precedence\n" + body + "\n")


def _write_cases(root: Path, cases: list[dict[str, Any]]) -> None:
    _write(root, "cases.jsonl", "".join(json.dumps(case) + "\n" for case in cases))


@pytest.mark.parametrize(
    "check",
    [
        {"id": "x", "type": "sections", "file": "a.md", "files": ["a.md"]},
        {"id": "x", "type": "sections", "file": ""},
        {"id": "x", "type": "sections"},
        {"id": "x", "type": "sections", "files": [3]},
    ],
)
def test_file_patterns_reject_invalid_shapes(tmp_path: Path, check: dict[str, Any]) -> None:
    with pytest.raises(ConfigError):
        _expand_files(tmp_path, check)


def test_file_patterns_stay_inside_root_and_deduplicate(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "text")

    files = _expand_files(
        tmp_path,
        {"id": "x", "type": "sections", "files": ["*.md", "a.md"]},
    )

    assert files == [(tmp_path / "a.md").resolve()]
    with pytest.raises(ConfigError, match="project root"):
        _expand_files(
            tmp_path,
            {"id": "x", "type": "sections", "files": ["../*.md"]},
        )
    with pytest.raises(ConfigError, match="project root"):
        _expand_files(
            tmp_path,
            {"id": "x", "type": "sections", "file": str((tmp_path / "a.md").resolve())},
        )


def test_display_path_falls_back_for_external_paths(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    assert _display_path(tmp_path, outside).endswith("outside.md")


def test_empty_globs_can_be_allowed_for_file_checks(tmp_path: Path) -> None:
    checks = [
        (check_frontmatter, {"required": []}),
        (check_sections, {"required": []}),
        (check_contains, {"required": ["text"]}),
        (check_forbid, {"patterns": ["text"]}),
    ]

    for rule, extra in checks:
        result = rule(
            tmp_path,
            {"id": "empty", "type": rule.__name__, "files": ["*.md"], "allow_empty": True, **extra},
        )
        assert result.passed
        assert result.inspected == 0


def test_each_file_check_reports_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_bytes(b"\xff")
    checks = [
        (check_frontmatter, {"required": []}),
        (check_sections, {"required": []}),
        (check_contains, {"required": ["text"]}),
        (check_forbid, {"patterns": ["text"]}),
    ]

    for rule, extra in checks:
        result = rule(
            tmp_path,
            {"id": "utf8", "type": rule.__name__, "file": "bad.md", **extra},
        )
        assert "cannot read UTF-8" in result.findings[0].message


def test_frontmatter_handles_missing_unclosed_duplicate_and_optional(tmp_path: Path) -> None:
    _write(tmp_path, "missing.md", "# Agent\n")
    _write(tmp_path, "unclosed.md", "---\nname: Agent\n")
    _write(tmp_path, "duplicate.md", "---\nname: One\nname: Two\n---\n")

    result = check_frontmatter(
        tmp_path,
        {"id": "fm", "type": "frontmatter", "files": ["*.md"]},
    )

    messages = {finding.message for finding in result.findings}
    assert "missing YAML frontmatter" in messages
    assert "YAML frontmatter is not closed" in messages
    assert "duplicate frontmatter key: name" in messages
    optional = check_frontmatter(
        tmp_path,
        {
            "id": "optional",
            "type": "frontmatter",
            "file": "missing.md",
            "require_frontmatter": False,
        },
    )
    assert optional.passed


def test_frontmatter_validates_boolean_option(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="boolean"):
        check_frontmatter(
            tmp_path,
            {
                "id": "fm",
                "type": "frontmatter",
                "files": ["*.md"],
                "require_frontmatter": "yes",
            },
        )


def test_frontmatter_empty_allowlist_rejects_every_key(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "---\nname: Demo\n---\n")

    result = check_frontmatter(
        tmp_path,
        {"id": "fm", "type": "frontmatter", "file": "agent.md", "allowed": []},
    )

    assert [finding.message for finding in result.findings] == [
        "frontmatter key is not allowed: name"
    ]


def test_sections_reject_invalid_required_regex(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="required_regex"):
        check_sections(
            tmp_path,
            {
                "id": "sections",
                "type": "sections",
                "files": ["*.md"],
                "required_regex": ["["],
            },
        )


def test_contains_casefolds_and_reports_bad_scope(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "## Constraints\nHELLO\n")
    passing = check_contains(
        tmp_path,
        {
            "id": "contains",
            "type": "contains",
            "file": "agent.md",
            "required": ["hello"],
            "case_sensitive": False,
        },
    )
    missing_scope = check_contains(
        tmp_path,
        {
            "id": "contains",
            "type": "contains",
            "file": "agent.md",
            "required": ["hello"],
            "under_section": "Missing",
        },
    )

    assert passing.passed
    assert "scope section not found" in missing_scope.findings[0].message
    with pytest.raises(ConfigError, match="under_section"):
        check_contains(
            tmp_path,
            {
                "id": "contains",
                "type": "contains",
                "file": "agent.md",
                "required": ["hello"],
                "under_section": 3,
            },
        )
    with pytest.raises(ConfigError, match="case_sensitive"):
        check_contains(
            tmp_path,
            {
                "id": "contains",
                "type": "contains",
                "file": "agent.md",
                "required": ["hello"],
                "case_sensitive": "no",
            },
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("case_sensitive", "no", "case_sensitive"),
        ("fence_language", 3, "fence_language"),
        ("message", 3, "message"),
    ],
)
def test_forbid_validates_options(tmp_path: Path, field: str, value: object, message: str) -> None:
    _write(tmp_path, "agent.md", "text")
    check = {"id": "forbid", "type": "forbid", "file": "agent.md", "patterns": ["x"]}
    check[field] = value

    with pytest.raises(ConfigError, match=message):
        check_forbid(tmp_path, check)


def test_forbid_supports_casefold_custom_message_and_missing_scope(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "BAD\nbad\n")
    result = check_forbid(
        tmp_path,
        {
            "id": "forbid",
            "type": "forbid",
            "file": "agent.md",
            "patterns": ["bad"],
            "case_sensitive": False,
            "message": "blocked",
        },
    )

    assert [finding.message for finding in result.findings] == ["blocked", "blocked"]
    assert [finding.line for finding in result.findings] == [1, 2]
    missing_scope = check_forbid(
        tmp_path,
        {
            "id": "forbid",
            "type": "forbid",
            "file": "agent.md",
            "patterns": ["bad"],
            "under_section": "Examples",
        },
    )
    assert "scope section not found" in missing_scope.findings[0].message


def test_load_jsonl_accepts_comments_and_preserves_line(tmp_path: Path) -> None:
    _write(tmp_path, "cases.jsonl", '\n# note\n{"input":"x"}\n')

    _, cases = _load_jsonl(tmp_path, {"id": "cases", "cases": "cases.jsonl"})

    assert cases == [{"input": "x", "_line": 3}]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("# only comments\n", "empty"),
        ("{broken}\n", "invalid JSON"),
        ('["not", "object"]\n', "must contain an object"),
    ],
)
def test_load_jsonl_rejects_bad_content(tmp_path: Path, content: str, message: str) -> None:
    _write(tmp_path, "cases.jsonl", content)

    with pytest.raises(ConfigError, match=message):
        _load_jsonl(tmp_path, {"id": "cases", "cases": "cases.jsonl"})


def test_load_jsonl_rejects_missing_escaped_and_invalid_utf8(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        _load_jsonl(tmp_path, {"id": "cases", "cases": "missing.jsonl"})
    with pytest.raises(ConfigError, match="project root"):
        _load_jsonl(tmp_path, {"id": "cases", "cases": "../cases.jsonl"})

    (tmp_path / "bad.jsonl").write_bytes(b"\xff")
    with pytest.raises(ConfigError, match="cannot read"):
        _load_jsonl(tmp_path, {"id": "cases", "cases": "bad.jsonl"})


def test_route_handles_no_match_short_words_phrases_and_ties() -> None:
    routes = {
        "Short": ["app"],
        "Phrase": ["money back"],
        "Tie": ["money-back"],
        "Billing": ["charge"],
    }

    assert _route("happy customer", routes)[0] == []
    assert _route("the app failed", routes)[0] == ["Short"]
    assert _route("I need my money_back", routes)[0] == ["Phrase", "Tie"]
    assert _route("the battery discharged", routes)[0] == []
    assert _route("the charge is wrong", routes)[0] == ["Billing"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("keyword_separator", 3, "keyword_separator"),
        ("keyword_separator", "[", "invalid keyword_separator"),
    ],
)
def test_routing_validates_separator(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        check_routing(tmp_path, _routing_check(**{field: value}))


def test_routing_handles_missing_multiple_and_unreadable_sources(tmp_path: Path) -> None:
    missing = check_routing(tmp_path, _routing_check())
    assert "matched no files" in missing.findings[0].message

    _write(tmp_path, "one.md", "## Routing\n")
    _write(tmp_path, "two.md", "## Routing\n")
    with pytest.raises(ConfigError, match="exactly one"):
        check_routing(tmp_path, _routing_check(file=None, files=["*.md"]))

    (tmp_path / "agent.md").write_bytes(b"\xff")
    unreadable = check_routing(tmp_path, _routing_check())
    assert "cannot read UTF-8" in unreadable.findings[0].message


def test_routing_reports_missing_section_table_and_routes(tmp_path: Path) -> None:
    _write(tmp_path, "agent.md", "# Agent\n")
    missing_section = check_routing(tmp_path, _routing_check())
    assert "routing section not found" in missing_section.findings[0].message

    _write(tmp_path, "agent.md", "## Routing\n| Other | Value |\n| --- | --- |\n")
    missing_table = check_routing(tmp_path, _routing_check())
    assert "no routing table" in missing_table.findings[0].message

    _write_routing_source(tmp_path, "| | foo |")
    no_routes = check_routing(tmp_path, _routing_check())
    assert "contains no routes" in no_routes.findings[0].message


def test_routing_exercises_no_match_forbidden_and_tie_policies(tmp_path: Path) -> None:
    _write_routing_source(tmp_path)
    _write_cases(
        tmp_path,
        [
            {"id": "none", "input": "unknown", "expected": "A"},
            {"id": "forbidden", "input": "foo", "expected": "A", "forbidden": ["B"]},
            {"id": "ambiguous", "input": "foo", "expected": "A"},
            {"id": "acceptable", "input": "foo", "expected": "A", "acceptable": ["B"]},
            {"id": "allowed", "input": "foo", "expected": "A", "allow_ties": True},
            {"id": "single", "input": "bar", "expected": "A", "acceptable": ["B"]},
        ],
    )

    result = check_routing(tmp_path, _routing_check())

    messages = [finding.message for finding in result.findings]
    assert len(messages) == 3
    assert any("no route matched" in message for message in messages)
    assert any("forbidden route won" in message for message in messages)
    assert any("ambiguous winners" in message for message in messages)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ({"input": 3, "expected": "A"}, "input and expected"),
        ({"input": "foo", "expected": "A", "acceptable": "B"}, "acceptable"),
        ({"input": "foo", "expected": "A", "forbidden": "B"}, "forbidden"),
        ({"input": "foo", "expected": "A", "allow_ties": "yes"}, "allow_ties"),
    ],
)
def test_routing_validates_case_shapes(tmp_path: Path, case: dict[str, Any], message: str) -> None:
    _write_routing_source(tmp_path)
    _write_cases(tmp_path, [case])

    with pytest.raises(ConfigError, match=message):
        check_routing(tmp_path, _routing_check())


def test_parse_precedence_labels_skips_unmatched_lines() -> None:
    import re

    labels = _parse_precedence_labels(
        "intro\n1. no bold\n2. **Matched**\n", re.compile(r"\*\*(.+?)\*\*")
    )
    assert labels == ["Matched"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("label_pattern", 3, "label_pattern"),
        ("label_pattern", "[", "invalid label_pattern"),
    ],
)
def test_precedence_validates_label_pattern(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        check_precedence(tmp_path, _precedence_check(**{field: value}))


def test_precedence_handles_missing_multiple_unreadable_and_missing_section(tmp_path: Path) -> None:
    missing = check_precedence(tmp_path, _precedence_check())
    assert "matched no files" in missing.findings[0].message

    _write(tmp_path, "one.md", "text")
    _write(tmp_path, "two.md", "text")
    with pytest.raises(ConfigError, match="exactly one"):
        check_precedence(tmp_path, _precedence_check(file=None, files=["*.md"]))

    (tmp_path / "agent.md").write_bytes(b"\xff")
    unreadable = check_precedence(tmp_path, _precedence_check())
    assert "cannot read UTF-8" in unreadable.findings[0].message

    _write(tmp_path, "agent.md", "# Agent\n")
    missing_section = check_precedence(tmp_path, _precedence_check())
    assert "precedence section not found" in missing_section.findings[0].message


def test_precedence_reports_missing_and_exact_list_drift(tmp_path: Path) -> None:
    _write_precedence_source(tmp_path, "1. **Specific**\n2. **Extra**")

    result = check_precedence(tmp_path, _precedence_check(exact=True))

    messages = [finding.message for finding in result.findings]
    assert any("is missing" in message for message in messages)
    assert any("exactly match" in message for message in messages)


def test_precedence_supports_custom_label_pattern(tmp_path: Path) -> None:
    _write_precedence_source(tmp_path, "1. `Specific`\n2. `General`")
    result = check_precedence(
        tmp_path,
        _precedence_check(label_pattern=r"`(.+?)`"),
    )
    assert result.passed


def _prepare_precedence_cases(tmp_path: Path, case: dict[str, Any] | None = None) -> None:
    _write_precedence_source(tmp_path)
    _write_cases(tmp_path, [case or {"input": "specific", "expected": "Specific"}])


@pytest.mark.parametrize(
    ("modes", "message"),
    [
        (None, "modes are required"),
        ([3], "inline table"),
        ([{"name": 3, "patterns": ["x"]}], "string name"),
        ([{"name": "Specific", "patterns": [3]}], "string name"),
        ([{"name": "Specific", "patterns": ["["]}], "invalid trigger regex"),
        ([{"name": "Specific", "patterns": ["specific"]}], "no trigger patterns"),
    ],
)
def test_precedence_validates_modes(tmp_path: Path, modes: object, message: str) -> None:
    _prepare_precedence_cases(tmp_path)
    overrides: dict[str, Any] = {"cases": "cases.jsonl"}
    if modes is not None:
        overrides["modes"] = modes

    with pytest.raises(ConfigError, match=message):
        check_precedence(tmp_path, _precedence_check(**overrides))


def test_precedence_validates_fallback_and_case_shape(tmp_path: Path) -> None:
    modes = [
        {"name": "Specific", "patterns": ["specific"]},
        {"name": "General", "patterns": ["general"]},
    ]
    _prepare_precedence_cases(tmp_path)
    with pytest.raises(ConfigError, match="fallback"):
        check_precedence(
            tmp_path,
            _precedence_check(cases="cases.jsonl", modes=modes, fallback=3),
        )

    _write_cases(tmp_path, [{"input": 3, "expected": "Specific"}])
    with pytest.raises(ConfigError, match="input and expected"):
        check_precedence(
            tmp_path,
            _precedence_check(cases="cases.jsonl", modes=modes),
        )


def test_precedence_cases_use_fallback_and_report_wrong_resolution(tmp_path: Path) -> None:
    modes = [
        {"name": "Specific", "patterns": ["specific"]},
        {"name": "General", "patterns": ["general"]},
    ]
    _write_precedence_source(tmp_path)
    _write_cases(
        tmp_path,
        [
            {"id": "fallback", "input": "unknown", "expected": "General"},
            {"id": "wrong", "input": "unknown", "expected": "Specific"},
        ],
    )

    result = check_precedence(
        tmp_path,
        _precedence_check(cases="cases.jsonl", modes=modes, fallback="General"),
    )

    assert len(result.findings) == 1
    assert "resolved to 'General'" in result.findings[0].message
