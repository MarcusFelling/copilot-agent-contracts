"""Implement the built-in static contract checks."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from copilot_agent_contracts.config import ConfigError, require_string, string_list
from copilot_agent_contracts.markdown import (
    clean_markdown_label,
    extract_section,
    fences,
    headings,
    line_for_offset,
    markdown_tables,
    parse_frontmatter,
)
from copilot_agent_contracts.model import CheckResult, Finding

Rule = Callable[[Path, dict[str, Any]], CheckResult]


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _file_patterns(check: dict[str, Any]) -> list[str]:
    single = check.get("file")
    multiple = check.get("files")
    if single is not None and multiple is not None:
        raise ConfigError(f"check {check['id']!r}: use file or files, not both")
    if single is not None:
        if not isinstance(single, str) or not single:
            raise ConfigError(f"check {check['id']!r}: file must be a non-empty string")
        return [single]
    if (
        not isinstance(multiple, list)
        or not multiple
        or any(not isinstance(item, str) or not item for item in multiple)
    ):
        raise ConfigError(f"check {check['id']!r}: files must be a non-empty array of strings")
    return list(multiple)


def _expand_files(root: Path, check: dict[str, Any]) -> list[Path]:
    files: dict[str, Path] = {}
    resolved_root = root.resolve()
    for pattern in _file_patterns(check):
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise ConfigError(
                f"check {check['id']!r}: file patterns must stay within the project root"
            )
        for path in root.glob(pattern):
            if path.is_file():
                resolved = path.resolve()
                try:
                    resolved.relative_to(resolved_root)
                except ValueError as exc:
                    raise ConfigError(
                        f"check {check['id']!r}: matched file resolves outside the project root: "
                        f"{pattern}"
                    ) from exc
                files[str(resolved).casefold()] = resolved
    return sorted(files.values(), key=lambda path: _display_path(root, path).casefold())


def _no_files_result(root: Path, check: dict[str, Any]) -> CheckResult:
    patterns = ", ".join(_file_patterns(check))
    finding = Finding(
        check_id=check["id"],
        path=".",
        message=f"file pattern matched no files: {patterns}",
    )
    return CheckResult(check["id"], check["type"], 0, (finding,))


def _read_text(root: Path, path: Path, check_id: str) -> tuple[str | None, Finding | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeError) as exc:
        return None, Finding(
            check_id,
            _display_path(root, path),
            f"cannot read UTF-8 text: {exc}",
        )


def check_frontmatter(root: Path, check: dict[str, Any]) -> CheckResult:
    """Check required, allowed, and forbidden top-level YAML keys."""
    required = string_list(check, "required")
    allowed = set(string_list(check, "allowed"))
    has_allowlist = "allowed" in check
    forbidden = set(string_list(check, "forbidden"))
    require_frontmatter = check.get("require_frontmatter", True)
    if not isinstance(require_frontmatter, bool):
        raise ConfigError(f"check {check['id']!r}: require_frontmatter must be a boolean")

    files = _expand_files(root, check)
    if not files and not check.get("allow_empty", False):
        return _no_files_result(root, check)

    findings: list[Finding] = []
    for path in files:
        display = _display_path(root, path)
        text, read_error = _read_text(root, path, check["id"])
        if read_error:
            findings.append(read_error)
            continue
        assert text is not None
        frontmatter = parse_frontmatter(text)
        if not frontmatter.exists:
            if require_frontmatter:
                findings.append(Finding(check["id"], display, "missing YAML frontmatter", 1))
            continue
        if not frontmatter.closed:
            findings.append(Finding(check["id"], display, "YAML frontmatter is not closed", 1))
            continue

        for key in frontmatter.duplicate_keys:
            findings.append(
                Finding(
                    check["id"],
                    display,
                    f"duplicate frontmatter key: {key}",
                    frontmatter.keys[key],
                )
            )
        for key in required:
            if key not in frontmatter.keys:
                findings.append(
                    Finding(check["id"], display, f"missing required frontmatter key: {key}", 1)
                )
        if has_allowlist:
            for key, line in frontmatter.keys.items():
                if key not in allowed:
                    findings.append(
                        Finding(
                            check["id"],
                            display,
                            f"frontmatter key is not allowed: {key}",
                            line,
                        )
                    )
        for key in forbidden:
            if key in frontmatter.keys:
                findings.append(
                    Finding(
                        check["id"],
                        display,
                        f"forbidden frontmatter key: {key}",
                        frontmatter.keys[key],
                    )
                )

    return CheckResult(check["id"], check["type"], len(files), tuple(findings))


def check_sections(root: Path, check: dict[str, Any]) -> CheckResult:
    """Check required Markdown headings."""
    required = string_list(check, "required")
    required_regex = string_list(check, "required_regex")
    try:
        compiled = [re.compile(pattern, re.IGNORECASE) for pattern in required_regex]
    except re.error as exc:
        raise ConfigError(f"check {check['id']!r}: invalid required_regex: {exc}") from exc

    files = _expand_files(root, check)
    if not files and not check.get("allow_empty", False):
        return _no_files_result(root, check)

    findings: list[Finding] = []
    for path in files:
        display = _display_path(root, path)
        text, read_error = _read_text(root, path, check["id"])
        if read_error:
            findings.append(read_error)
            continue
        assert text is not None
        labels = [heading.label for heading in headings(text)]
        normalized = {clean_markdown_label(label) for label in labels}
        for label in required:
            if clean_markdown_label(label) not in normalized:
                findings.append(Finding(check["id"], display, f"missing required section: {label}"))
        for pattern, regex in zip(required_regex, compiled, strict=True):
            if not any(regex.search(label) for label in labels):
                findings.append(
                    Finding(
                        check["id"],
                        display,
                        f"no section heading matches required pattern: {pattern}",
                    )
                )

    return CheckResult(check["id"], check["type"], len(files), tuple(findings))


def _scope_text(
    root: Path, path: Path, check: dict[str, Any], text: str
) -> tuple[str | None, int, Finding | None]:
    section = check.get("under_section")
    if section is None:
        return text, 1, None
    if not isinstance(section, str) or not section:
        raise ConfigError(f"check {check['id']!r}: under_section must be a string")
    span = extract_section(text, section)
    if span is None:
        return (
            None,
            1,
            Finding(
                check["id"],
                _display_path(root, path),
                f"scope section not found: {section}",
            ),
        )
    return span.text, span.start_line, None


def check_contains(root: Path, check: dict[str, Any]) -> CheckResult:
    """Check required literal text, optionally within one section."""
    required = string_list(check, "required", required=True)
    case_sensitive = check.get("case_sensitive", True)
    if not isinstance(case_sensitive, bool):
        raise ConfigError(f"check {check['id']!r}: case_sensitive must be a boolean")

    files = _expand_files(root, check)
    if not files and not check.get("allow_empty", False):
        return _no_files_result(root, check)

    findings: list[Finding] = []
    for path in files:
        display = _display_path(root, path)
        text, read_error = _read_text(root, path, check["id"])
        if read_error:
            findings.append(read_error)
            continue
        assert text is not None
        scoped, _, scope_error = _scope_text(root, path, check, text)
        if scope_error:
            findings.append(scope_error)
            continue
        assert scoped is not None
        haystack = scoped if case_sensitive else scoped.casefold()
        for required_text in required:
            needle = required_text if case_sensitive else required_text.casefold()
            if needle not in haystack:
                findings.append(
                    Finding(
                        check["id"],
                        display,
                        f"missing required text: {required_text}",
                    )
                )

    return CheckResult(check["id"], check["type"], len(files), tuple(findings))


def check_forbid(root: Path, check: dict[str, Any]) -> CheckResult:
    """Reject regex matches in files, sections, or selected fenced blocks."""
    patterns = string_list(check, "patterns", required=True)
    case_sensitive = check.get("case_sensitive", True)
    if not isinstance(case_sensitive, bool):
        raise ConfigError(f"check {check['id']!r}: case_sensitive must be a boolean")
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = [(pattern, re.compile(pattern, flags)) for pattern in patterns]
    except re.error as exc:
        raise ConfigError(f"check {check['id']!r}: invalid forbidden regex: {exc}") from exc

    fence_language = check.get("fence_language")
    if fence_language is not None and not isinstance(fence_language, str):
        raise ConfigError(f"check {check['id']!r}: fence_language must be a string")
    custom_message = check.get("message")
    if custom_message is not None and not isinstance(custom_message, str):
        raise ConfigError(f"check {check['id']!r}: message must be a string")

    files = _expand_files(root, check)
    if not files and not check.get("allow_empty", False):
        return _no_files_result(root, check)

    findings: list[Finding] = []
    for path in files:
        display = _display_path(root, path)
        text, read_error = _read_text(root, path, check["id"])
        if read_error:
            findings.append(read_error)
            continue
        assert text is not None
        scoped, scoped_line, scope_error = _scope_text(root, path, check, text)
        if scope_error:
            findings.append(scope_error)
            continue
        assert scoped is not None

        targets: list[tuple[str, int]]
        if fence_language is None:
            targets = [(scoped, scoped_line)]
        else:
            targets = [
                (fence.body, fence.line)
                for fence in fences(scoped, scoped_line)
                if fence.language.casefold() == fence_language.casefold()
            ]

        for target, start_line in targets:
            for pattern, regex in compiled:
                for match in regex.finditer(target):
                    message = custom_message or f"forbidden pattern matched: {pattern}"
                    findings.append(
                        Finding(
                            check["id"],
                            display,
                            message,
                            line_for_offset(target, match.start(), start_line),
                        )
                    )

    return CheckResult(check["id"], check["type"], len(files), tuple(findings))


def _load_jsonl(root: Path, check: dict[str, Any]) -> tuple[Path, list[dict[str, Any]]]:
    relative = require_string(check, "cases")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ConfigError(f"check {check['id']!r}: cases must stay within the project root")
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ConfigError(f"check {check['id']!r}: cases resolve outside the project root") from exc
    if not path.is_file():
        raise ConfigError(f"check {check['id']!r}: cases file not found: {relative}")

    cases: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"check {check['id']!r}: cannot read cases file: {exc}") from exc
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"check {check['id']!r}: invalid JSON at {relative}:{line_number}: {exc.msg}"
            ) from exc
        if not isinstance(case, dict):
            raise ConfigError(
                f"check {check['id']!r}: {relative}:{line_number} must contain an object"
            )
        case["_line"] = line_number
        cases.append(case)
    if not cases:
        raise ConfigError(f"check {check['id']!r}: cases file is empty: {relative}")
    return path, cases


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]", " ", text.casefold())).strip()


def _keyword_matches(keyword: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text) is not None


def _route(input_text: str, routes: dict[str, list[str]]) -> tuple[list[str], dict[str, int]]:
    normalized_input = _normalize_match_text(input_text)
    scores: dict[str, int] = {}
    for route, keywords in routes.items():
        scores[route] = sum(
            len(normalized)
            for keyword in keywords
            if (normalized := _normalize_match_text(keyword))
            and _keyword_matches(normalized, normalized_input)
        )
    maximum = max(scores.values(), default=0)
    if maximum == 0:
        return [], scores
    return [route for route, score in scores.items() if score == maximum], scores


def _clean_table_value(value: str) -> str:
    return re.sub(r"^[`*_]+|[`*_]+$", "", value.strip())


def check_routing(root: Path, check: dict[str, Any]) -> CheckResult:
    """Run golden inputs against a length-weighted Markdown routing table."""
    section_name = require_string(check, "section")
    route_column = require_string(check, "route_column")
    keywords_column = require_string(check, "keywords_column")
    separator = check.get("keyword_separator", r"[,/]")
    if not isinstance(separator, str):
        raise ConfigError(f"check {check['id']!r}: keyword_separator must be a string")
    try:
        separator_regex = re.compile(separator)
    except re.error as exc:
        raise ConfigError(f"check {check['id']!r}: invalid keyword_separator: {exc}") from exc

    files = _expand_files(root, check)
    if not files:
        return _no_files_result(root, check)
    if len(files) != 1:
        raise ConfigError(f"check {check['id']!r}: routing requires exactly one file")
    source = files[0]
    source_text, read_error = _read_text(root, source, check["id"])
    if read_error:
        return CheckResult(check["id"], check["type"], 1, (read_error,))
    assert source_text is not None
    section = extract_section(source_text, section_name)
    if section is None:
        finding = Finding(
            check["id"],
            _display_path(root, source),
            f"routing section not found: {section_name}",
        )
        return CheckResult(check["id"], check["type"], 0, (finding,))

    wanted_route = clean_markdown_label(route_column)
    wanted_keywords = clean_markdown_label(keywords_column)
    selected = None
    for table in markdown_tables(section.text, section.start_line):
        headers = {clean_markdown_label(header): header for header in table.headers}
        if wanted_route in headers and wanted_keywords in headers:
            selected = (table, headers[wanted_route], headers[wanted_keywords])
            break
    if selected is None:
        finding = Finding(
            check["id"],
            _display_path(root, source),
            f"no routing table contains columns {route_column!r} and {keywords_column!r}",
        )
        return CheckResult(check["id"], check["type"], 0, (finding,))

    table, route_header, keywords_header = selected
    routes: dict[str, list[str]] = {}
    for row in table.rows:
        route_name = _clean_table_value(row[route_header])
        keywords = [
            _clean_table_value(token)
            for token in separator_regex.split(row[keywords_header])
            if _clean_table_value(token)
        ]
        if route_name:
            routes.setdefault(route_name, []).extend(keywords)
    if not routes:
        finding = Finding(
            check["id"],
            _display_path(root, source),
            "routing table contains no routes",
            table.line,
        )
        return CheckResult(check["id"], check["type"], 0, (finding,))

    cases_path, cases = _load_jsonl(root, check)
    findings: list[Finding] = []
    for case in cases:
        case_id = str(case.get("id", "?"))
        input_text = case.get("input")
        expected = case.get("expected")
        acceptable = case.get("acceptable", [])
        forbidden = case.get("forbidden", [])
        allow_ties = case.get("allow_ties", False)
        if not isinstance(input_text, str) or not isinstance(expected, str):
            raise ConfigError(
                f"check {check['id']!r}: case {case_id!r} needs string input and expected fields"
            )
        if not isinstance(acceptable, list) or any(
            not isinstance(item, str) for item in acceptable
        ):
            raise ConfigError(
                f"check {check['id']!r}: case {case_id!r} acceptable must be an array of strings"
            )
        if not isinstance(forbidden, list) or any(not isinstance(item, str) for item in forbidden):
            raise ConfigError(
                f"check {check['id']!r}: case {case_id!r} forbidden must be an array of strings"
            )
        if not isinstance(allow_ties, bool):
            raise ConfigError(
                f"check {check['id']!r}: case {case_id!r} allow_ties must be a boolean"
            )
        winners, scores = _route(input_text, routes)
        allowed = {expected, *acceptable}
        reason = None
        if not winners:
            reason = "no route matched"
        elif set(winners) & set(forbidden):
            reason = f"forbidden route won: {sorted(set(winners) & set(forbidden))}"
        elif len(winners) == 1 and winners[0] not in allowed:
            reason = f"routed to {winners[0]!r}; expected one of {sorted(allowed)}"
        elif len(winners) > 1 and not (
            set(winners) <= allowed or (allow_ties and expected in winners)
        ):
            reason = f"ambiguous winners {winners}; expected one of {sorted(allowed)}"
        if reason:
            top_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:3]
            findings.append(
                Finding(
                    check["id"],
                    _display_path(root, cases_path),
                    f"case {case_id}: {reason}; top scores: {top_scores}",
                    case["_line"],
                )
            )

    return CheckResult(check["id"], check["type"], len(cases), tuple(findings))


def _parse_precedence_labels(text: str, pattern: re.Pattern[str]) -> list[str]:
    labels: list[str] = []
    for line in text.splitlines():
        if not re.match(r"^\s*\d+\.\s+", line):
            continue
        match = pattern.search(line)
        if match:
            labels.append(match.group(1).strip())
    return labels


def check_precedence(root: Path, check: dict[str, Any]) -> CheckResult:
    """Guard a documented order and test overlapping trigger patterns."""
    section_name = require_string(check, "section")
    expected_order = string_list(check, "order", required=True)
    label_pattern = check.get("label_pattern", r"\*\*(.+?)\*\*")
    if not isinstance(label_pattern, str):
        raise ConfigError(f"check {check['id']!r}: label_pattern must be a string")
    try:
        label_regex = re.compile(label_pattern)
    except re.error as exc:
        raise ConfigError(f"check {check['id']!r}: invalid label_pattern: {exc}") from exc

    files = _expand_files(root, check)
    if not files:
        return _no_files_result(root, check)
    if len(files) != 1:
        raise ConfigError(f"check {check['id']!r}: precedence requires exactly one file")
    source = files[0]
    source_text, read_error = _read_text(root, source, check["id"])
    if read_error:
        return CheckResult(check["id"], check["type"], 1, (read_error,))
    assert source_text is not None
    section = extract_section(source_text, section_name)
    if section is None:
        finding = Finding(
            check["id"],
            _display_path(root, source),
            f"precedence section not found: {section_name}",
        )
        return CheckResult(check["id"], check["type"], 0, (finding,))

    parsed_order = _parse_precedence_labels(section.text, label_regex)
    parsed_normalized = [clean_markdown_label(label) for label in parsed_order]
    expected_normalized = [clean_markdown_label(label) for label in expected_order]
    findings: list[Finding] = []
    missing = [
        label
        for label, normalized in zip(expected_order, expected_normalized, strict=True)
        if normalized not in parsed_normalized
    ]
    present_document_order = [label for label in parsed_normalized if label in expected_normalized]
    present_expected_order = [label for label in expected_normalized if label in parsed_normalized]
    if missing:
        findings.append(
            Finding(
                check["id"],
                _display_path(root, source),
                f"precedence list is missing: {missing}",
                section.start_line,
            )
        )
    if present_document_order != present_expected_order:
        findings.append(
            Finding(
                check["id"],
                _display_path(root, source),
                f"precedence order is {parsed_order}; expected {expected_order}",
                section.start_line,
            )
        )
    if check.get("exact", False) and parsed_normalized != expected_normalized:
        findings.append(
            Finding(
                check["id"],
                _display_path(root, source),
                "precedence list must exactly match the configured order",
                section.start_line,
            )
        )

    modes = check.get("modes", [])
    cases_value = check.get("cases")
    inspected = 1
    if cases_value is not None:
        if not isinstance(modes, list) or not modes:
            raise ConfigError(f"check {check['id']!r}: modes are required when cases are set")
        mode_patterns: dict[str, list[re.Pattern[str]]] = {}
        for mode in modes:
            if not isinstance(mode, dict):
                raise ConfigError(f"check {check['id']!r}: every mode must be an inline table")
            name = mode.get("name")
            patterns = mode.get("patterns")
            if (
                not isinstance(name, str)
                or not isinstance(patterns, list)
                or any(not isinstance(pattern, str) for pattern in patterns)
            ):
                raise ConfigError(
                    f"check {check['id']!r}: each mode needs a string name and patterns array"
                )
            try:
                mode_patterns[clean_markdown_label(name)] = [
                    re.compile(pattern, re.IGNORECASE) for pattern in patterns
                ]
            except re.error as exc:
                raise ConfigError(
                    f"check {check['id']!r}: invalid trigger regex for mode {name!r}: {exc}"
                ) from exc

        for mode in expected_normalized:
            if mode not in mode_patterns:
                raise ConfigError(
                    f"check {check['id']!r}: no trigger patterns configured for mode {mode!r}"
                )

        fallback = check.get("fallback")
        if fallback is not None and not isinstance(fallback, str):
            raise ConfigError(f"check {check['id']!r}: fallback must be a string")
        cases_path, cases = _load_jsonl(root, check)
        inspected = len(cases)
        for case in cases:
            case_id = str(case.get("id", "?"))
            input_text = case.get("input")
            expected = case.get("expected")
            if not isinstance(input_text, str) or not isinstance(expected, str):
                raise ConfigError(
                    f"check {check['id']!r}: case {case_id!r} needs string input "
                    "and expected fields"
                )
            resolved = fallback
            for mode in expected_normalized:
                patterns = mode_patterns[mode]
                if any(pattern.search(input_text) for pattern in patterns):
                    resolved = mode
                    break
            if clean_markdown_label(resolved or "") != clean_markdown_label(expected):
                findings.append(
                    Finding(
                        check["id"],
                        _display_path(root, cases_path),
                        f"case {case_id}: resolved to {resolved!r}; expected {expected!r}",
                        case["_line"],
                    )
                )

    return CheckResult(check["id"], check["type"], inspected, tuple(findings))


RULES: dict[str, Rule] = {
    "contains": check_contains,
    "forbid": check_forbid,
    "frontmatter": check_frontmatter,
    "precedence": check_precedence,
    "routing": check_routing,
    "sections": check_sections,
}
