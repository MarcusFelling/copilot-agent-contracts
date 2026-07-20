# Copilot Agent Contracts

Static contract tests for GitHub Copilot custom agents and prompt files.

Agent instructions are executable specifications, but ordinary linters cannot tell you whether a routing table still covers its golden cases, a safety sentence disappeared, or a documented precedence order changed. Copilot Agent Contracts checks those properties from a versioned TOML file. It runs locally with no model call, token, credential, or service connection.

## Scope

The package reads Markdown, YAML frontmatter keys, Markdown tables, fenced blocks, and JSONL cases. It reports deterministic findings with file and line locations where available.

It does **not** invoke GitHub Copilot, test model responses, connect to an MCP server, execute tools, or prove that an agent behaves as written. Use runtime evaluations for those questions. These checks cover the static contract stored in your repository.

## Install from a checkout

Python 3.11 or newer is required.

```shell
python -m pip install -e .
```

For development tools:

```shell
python -m pip install -e ".[dev]"
```

## Quick start

Create a starter configuration:

```shell
copilot-agent-contracts init
```

Edit `agent-contracts.toml`, then run:

```shell
copilot-agent-contracts check
```

The repository includes a fictional customer-support agent that exercises every rule:

```shell
copilot-agent-contracts check --config examples/customer-support/agent-contracts.toml --verbose
```

A passing run exits with code `0`. Contract violations exit with code `1`. Invalid configuration exits with code `2`.

## Configuration

A configuration uses version `1`. The project root resolves relative to the TOML file unless `check --root` overrides it.

```toml
version = 1

[project]
root = "."

[[checks]]
id = "agent-frontmatter"
type = "frontmatter"
files = [".github/agents/*.agent.md"]
required = ["description"]
allowed = ["name", "description", "tools", "model"]

[[checks]]
id = "agent-sections"
type = "sections"
files = [".github/agents/*.agent.md"]
required = ["Constraints", "Approach", "Output Format"]
```

Each check needs a unique `id`, a supported `type`, and either `file` or `files`. Paths and glob patterns resolve from the project root. A pattern that matches no files fails unless the check sets `allow_empty = true`.

### `frontmatter`

Checks top-level YAML frontmatter keys without interpreting YAML values.

| Field | Purpose |
| --- | --- |
| `required` | Keys that must exist |
| `allowed` | Complete allowlist when supplied |
| `forbidden` | Keys that must not exist |
| `require_frontmatter` | Require a frontmatter block, defaults to `true` |

The check also rejects an unclosed block and duplicate top-level keys.

### `sections`

Checks Markdown ATX headings such as `## Constraints`.

| Field | Purpose |
| --- | --- |
| `required` | Heading labels that must exist |
| `required_regex` | Regular expressions that at least one heading must match |

Literal heading comparisons ignore case and Markdown emphasis characters.

### `contains`

Checks required literal text.

| Field | Purpose |
| --- | --- |
| `required` | Non-empty list of required strings |
| `under_section` | Restrict the scan to one Markdown section |
| `case_sensitive` | Control matching, defaults to `true` |

### `forbid`

Reports every match for one or more regular expressions.

| Field | Purpose |
| --- | --- |
| `patterns` | Non-empty list of Python regular expressions |
| `under_section` | Restrict the scan to one Markdown section |
| `fence_language` | Scan only matching triple-backtick blocks, such as `json` |
| `case_sensitive` | Control matching, defaults to `true` |
| `message` | Replace the default finding message |

### `routing`

Reads routes and keywords from a Markdown table, then evaluates JSONL golden cases with a deterministic keyword scorer. Longer matching phrases receive more weight. This scorer tests the written table and cases; it does not simulate Copilot routing.

```toml
[[checks]]
id = "domain-routing"
type = "routing"
file = ".github/agents/customer-support.agent.md"
section = "Routing"
route_column = "Route"
keywords_column = "Keywords"
cases = "contracts/routing.jsonl"
keyword_separator = "[,/]"
```

Each non-comment JSONL line needs `input` and `expected`. Optional fields are `id`, `acceptable`, `forbidden`, and `allow_ties`.

```json
{"id":"refund","input":"Can I get my money back?","expected":"Billing","forbidden":["Technical"]}
```

### `precedence`

Checks a numbered Markdown list against a configured order. By default, the list may contain other labels. Set `exact = true` to require an exact match.

Optional golden cases apply configured regular expressions in the documented order. The first matching mode wins.

```toml
[[checks]]
id = "mode-precedence"
type = "precedence"
file = ".github/agents/customer-support.agent.md"
section = "Mode precedence"
order = ["Refund", "Troubleshoot", "General"]
exact = true
cases = "contracts/modes.jsonl"
fallback = "General"
modes = [
  { name = "Refund", patterns = ["\\brefund\\b", "money\\s+back"] },
  { name = "Troubleshoot", patterns = ["\\b(error|broken)\\b"] },
  { name = "General", patterns = ["(?s).*"] },
]
```

The default list parser reads labels wrapped in bold Markdown, such as `1. **Refund**`. Set `label_pattern` to change the capture expression.

## Output formats

Text output is the default. Use `--format json` for machine-readable results or `--format github` for GitHub Actions error annotations.

```shell
copilot-agent-contracts check --format json
copilot-agent-contracts check --format github
```

A workflow step can install the package and annotate changed contracts:

```yaml
- name: Check agent contracts
  run: copilot-agent-contracts check --format github
```

## Python API

```python
from pathlib import Path

from copilot_agent_contracts import run_contracts
from copilot_agent_contracts.config import load_config

config = load_config(Path("agent-contracts.toml"))
report = run_contracts(config)

if not report.passed:
    for finding in report.findings:
        print(finding)
```

`Finding`, `CheckResult`, and `Report` are immutable dataclasses. Each type has a `to_dict()` method.

## Development

```shell
ruff check .
ruff format --check .
pytest --cov --cov-report=term-missing
python -m build
```

The runtime package uses only the Python standard library. Tests run on Python 3.11, 3.12, and 3.13 in GitHub Actions.

## Security and privacy

The checker reads files under the configured root and writes results to standard output. It does not make network requests. Treat JSON output and CI annotations as repository content because a matched line can appear in a finding message.
