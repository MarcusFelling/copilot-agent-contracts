"""Small Markdown parsers used by the static checks."""

from __future__ import annotations

import re
from dataclasses import dataclass

FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z][\w-]*):(?:\s|$)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(
    r"^```(?P<language>[A-Za-z0-9_+.-]*)[^\n]*\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class Frontmatter:
    exists: bool
    closed: bool
    keys: dict[str, int]
    duplicate_keys: tuple[str, ...]
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    label: str
    line: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    start_line: int


@dataclass(frozen=True, slots=True)
class MarkdownTable:
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    line: int


@dataclass(frozen=True, slots=True)
class Fence:
    language: str
    body: str
    line: int


def parse_frontmatter(text: str) -> Frontmatter:
    """Extract top-level YAML keys without requiring a YAML dependency."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return Frontmatter(False, False, {}, ())

    keys: dict[str, int] = {}
    duplicates: list[str] = []
    for index, line in enumerate(lines[1:], 2):
        if line.strip() == "---":
            return Frontmatter(True, True, keys, tuple(duplicates), index)
        if line[:1].isspace():
            continue
        match = FRONTMATTER_KEY_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in keys and key not in duplicates:
            duplicates.append(key)
        keys.setdefault(key, index)

    return Frontmatter(True, False, keys, tuple(duplicates))


def clean_markdown_label(value: str) -> str:
    """Normalize a heading, table header, or bold list label."""
    value = re.sub(r"[`*_]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def headings(text: str) -> tuple[Heading, ...]:
    """Return ATX headings and source offsets."""
    result: list[Heading] = []
    offset = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        content = line.rstrip("\r\n")
        match = HEADING_RE.match(content)
        if match:
            result.append(
                Heading(
                    level=len(match.group(1)),
                    label=match.group(2).strip(),
                    line=line_number,
                    start=offset,
                    end=offset + len(line),
                )
            )
        offset += len(line)
    return tuple(result)


def extract_section(text: str, label: str) -> TextSpan | None:
    """Return a section body through the next heading of equal or higher rank."""
    wanted = clean_markdown_label(label)
    document_headings = headings(text)
    for index, heading in enumerate(document_headings):
        if clean_markdown_label(heading.label) != wanted:
            continue
        end = len(text)
        for candidate in document_headings[index + 1 :]:
            if candidate.level <= heading.level:
                end = candidate.start
                break
        return TextSpan(text[heading.end : end], heading.line + 1)
    return None


def split_markdown_row(line: str) -> list[str]:
    """Split a Markdown table row while preserving escaped pipe characters."""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith(r"\|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def markdown_tables(text: str, start_line: int = 1) -> tuple[MarkdownTable, ...]:
    """Parse simple GitHub-flavored Markdown tables."""
    lines = text.splitlines()
    tables: list[MarkdownTable] = []
    index = 0
    while index + 1 < len(lines):
        if "|" not in lines[index] or "|" not in lines[index + 1]:
            index += 1
            continue
        headers = split_markdown_row(lines[index])
        separator = split_markdown_row(lines[index + 1])
        if len(headers) != len(separator) or not _is_separator_row(separator):
            index += 1
            continue

        rows: list[dict[str, str]] = []
        row_index = index + 2
        while row_index < len(lines) and "|" in lines[row_index]:
            cells = split_markdown_row(lines[row_index])
            if len(cells) != len(headers):
                break
            rows.append(dict(zip(headers, cells, strict=True)))
            row_index += 1
        tables.append(MarkdownTable(tuple(headers), tuple(rows), start_line + index))
        index = row_index
    return tuple(tables)


def fences(text: str, start_line: int = 1) -> tuple[Fence, ...]:
    """Extract triple-backtick fenced blocks."""
    result: list[Fence] = []
    for match in FENCE_RE.finditer(text):
        line = start_line + text.count("\n", 0, match.start("body"))
        result.append(Fence(match.group("language"), match.group("body"), line))
    return tuple(result)


def line_for_offset(text: str, offset: int, start_line: int = 1) -> int:
    """Convert a string offset into a one-based source line."""
    return start_line + text.count("\n", 0, offset)
