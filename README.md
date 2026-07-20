# Copilot Agent Contracts

Golden-case contract tests for GitHub Copilot custom agents.

When a Copilot custom agent routes work across sub-agents or picks a mode by precedence, the routing table and the precedence list *are* the behavior. Copilot Agent Contracts lets you pin that behavior with golden cases: you write example inputs and the route or mode each one should resolve to, and the tool asserts the documented table and order still produce those answers. Every check is deterministic, versioned in a TOML file, and runs locally with no model call, token, credential, or service connection.

The routing and precedence checks are the reason this exists. Four structural guards (`frontmatter`, `sections`, `contains`, `forbid`) come along so one config can also hold the file to a shape, but those overlap with general instruction linters. If you want broad file-quality linting (broken paths, drift, secrets, token budgets), reach for a dedicated linter such as [agnix](https://github.com/agent-sh/agnix) or [agentlint](https://github.com/Mr-afroverse/agentlint). This tool is the piece they leave out: gating CI on golden routing and precedence cases.

## How this differs from a linter

A linter inspects the file for its own quality. A contract test asserts an outcome you chose in advance.

- A linter can warn that two routes have overlapping keywords. It cannot tell you that `"the app crashed and I want a refund"` must resolve to `Billing`, not `Technical`.
- A linter can flag a precedence list that looks suspicious. It cannot tell you that a broken-and-refund message must resolve to `Refund` because `Refund` outranks `Troubleshoot`.

You supply those answers as golden cases. When someone edits the table or reorders the list, the failing case names the exact input, the route it took, and the route it should have taken.

## Scope

The package reads Markdown, YAML frontmatter keys, Markdown tables, fenced blocks, and JSONL cases. It reports deterministic findings with file and line locations where available.

It does **not** invoke GitHub Copilot, test model responses, connect to an MCP server, execute tools, or prove that an agent behaves as written at runtime. The routing and precedence scorers evaluate the documented table and order, not Copilot's own selection logic. Use runtime evaluations for questions about model behavior. These checks cover the static contract stored in your repository.

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

## Golden-case contract tests

These two checks are the core of the tool. Each reads a documented structure from the agent file and runs your JSONL golden cases against it.

### `routing`

Reads routes and keywords from a Markdown table, then evaluates JSONL golden cases with a deterministic keyword scorer. Longer matching phrases receive more weight, so a specific phrase can outrank a shorter keyword in another route. This scorer tests the written table and your cases; it does not simulate Copilot routing.

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

When a case fails, the finding names the input, the winning route or routes, the expected route, and the top keyword scores, so you can see why the table disagreed with your golden answer.

### `precedence`

Checks a numbered Markdown list against a configured order. By default, the list may contain other labels. Set `exact = true` to require an exact match.

Optional golden cases apply configured regular expressions in the documented order. The first matching mode wins, so overlapping triggers resolve to the higher-precedence mode. A message that both reports a failure and asks for a refund resolves to `Refund` when `Refund` precedes `Troubleshoot`.

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

## Supporting structural checks

These four checks hold the agent and prompt files to a shape. They overlap with general instruction linters, so use them when you want one config to cover structure alongside your golden cases; use a dedicated linter when you need broad file-quality coverage.

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
