from copilot_agent_contracts.markdown import (
    extract_section,
    fences,
    markdown_tables,
    parse_frontmatter,
)


def test_parse_frontmatter_extracts_top_level_keys_and_duplicates() -> None:
    text = """---
description: First
name: Demo
name: Duplicate
hooks:
  Stop: []
---
Body
"""

    parsed = parse_frontmatter(text)

    assert parsed.exists
    assert parsed.closed
    assert parsed.keys == {"description": 2, "name": 3, "hooks": 5}
    assert parsed.duplicate_keys == ("name",)
    assert parsed.end_line == 7


def test_parse_frontmatter_handles_missing_and_unclosed_blocks() -> None:
    assert not parse_frontmatter("# Heading\n").exists
    unclosed = parse_frontmatter("---\ndescription: Test\n")
    assert unclosed.exists
    assert not unclosed.closed


def test_extract_section_stops_at_equal_or_higher_heading() -> None:
    text = """# Agent
## Constraints
Keep this.
### Detail
Keep this too.
## Approach
Not this.
"""

    section = extract_section(text, "Constraints")

    assert section is not None
    assert "Keep this too." in section.text
    assert "Not this." not in section.text
    assert section.start_line == 3


def test_markdown_tables_parse_escaped_pipes() -> None:
    text = """| Route | Keywords |
| --- | --- |
| Billing | refund, charge |
| Technical | error \\| crash |
"""

    tables = markdown_tables(text)

    assert len(tables) == 1
    assert tables[0].rows[1]["Keywords"] == "error | crash"


def test_fences_preserve_language_body_and_line() -> None:
    text = """# Examples

```json
{"decision":"pending"}
```
"""

    blocks = fences(text)

    assert len(blocks) == 1
    assert blocks[0].language == "json"
    assert '"pending"' in blocks[0].body
    assert blocks[0].line == 4
