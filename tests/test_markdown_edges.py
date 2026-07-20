from copilot_agent_contracts.markdown import (
    clean_markdown_label,
    extract_section,
    headings,
    line_for_offset,
    markdown_tables,
    parse_frontmatter,
    split_markdown_row,
)


def test_frontmatter_ignores_nested_and_malformed_lines() -> None:
    parsed = parse_frontmatter(
        """---
description: Test
  nested: value
not a key
---
"""
    )

    assert parsed.keys == {"description": 2}


def test_heading_helpers_normalize_and_find_last_section() -> None:
    text = "plain\n## **Output   Format** ##\nbody\n### Child\nchild body\n"

    parsed = headings(text)
    section = extract_section(text, "output format")

    assert len(parsed) == 2
    assert clean_markdown_label(parsed[0].label) == "output format"
    assert section is not None
    assert section.text.endswith("child body\n")
    assert extract_section(text, "missing") is None


def test_split_markdown_row_handles_open_edges_and_trailing_escape() -> None:
    assert split_markdown_row("a | b") == ["a", "b"]
    trailing_escape = "| a | b " + chr(92)
    assert split_markdown_row(trailing_escape) == ["a", "b " + chr(92)]


def test_markdown_tables_skip_invalid_shapes_and_stop_on_bad_row() -> None:
    text = """plain
| A | B |
| -- | --- |
| A | B |
| --- | --- |
| one |
| X | Y |
| :--- | ---: |
| x | y |
"""

    tables = markdown_tables(text, start_line=10)

    assert len(tables) == 2
    assert tables[0].rows == ()
    assert tables[0].line == 13
    assert tables[1].rows[0] == {"X": "x", "Y": "y"}


def test_line_for_offset_counts_from_supplied_start() -> None:
    assert line_for_offset("one\ntwo\nthree", 8, start_line=4) == 6
