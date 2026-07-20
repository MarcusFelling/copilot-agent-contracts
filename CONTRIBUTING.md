# Contributing

Copilot Agent Contracts accepts focused fixes, documentation changes, and rule proposals that preserve deterministic local execution.

## Set up

Use Python 3.11 or newer:

```shell
python -m pip install -e ".[dev]"
```

Run the same checks as CI before opening a pull request:

```shell
ruff check .
ruff format --check .
pytest --cov --cov-report=term-missing
python -m build
copilot-agent-contracts check --config examples/customer-support/agent-contracts.toml
```

## Rule changes

A new or changed rule needs:

1. A documented TOML contract.
2. Passing and failing unit cases.
3. A synthetic example when the behavior is easier to understand from a complete agent file.
4. A deterministic result with no model or network dependency.

Do not submit proprietary prompts, internal service names, customer data, credentials, or generated model responses copied from a private system.

## Reporting bugs

Open an issue with the smallest agent file, configuration, and command that reproduce the problem. Replace private content with a synthetic example before attaching it.
