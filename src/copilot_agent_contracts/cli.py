"""Command-line interface for Copilot Agent Contracts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from copilot_agent_contracts import __version__
from copilot_agent_contracts.config import ConfigError, load_config
from copilot_agent_contracts.engine import run_contracts
from copilot_agent_contracts.model import Finding, Report

DEFAULT_CONFIG = "agent-contracts.toml"
STARTER_CONFIG = """version = 1

[project]
root = "."

[[checks]]
id = "agent-frontmatter"
type = "frontmatter"
files = [".github/agents/*.agent.md"]
required = ["description"]
allowed = [
  "name",
  "description",
  "argument-hint",
  "tools",
  "model",
  "agents",
  "user-invocable",
  "disable-model-invocation",
  "handoffs",
  "hooks",
  "target",
  "mcp-servers",
]

[[checks]]
id = "agent-sections"
type = "sections"
files = [".github/agents/*.agent.md"]
required = ["Constraints", "Approach", "Output Format"]
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copilot-agent-contracts",
        description=(
            "Golden-case routing and precedence contract tests for GitHub Copilot custom agents."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    check = subcommands.add_parser("check", help="run configured contract checks")
    check.add_argument(
        "--config",
        type=Path,
        default=Path(DEFAULT_CONFIG),
        help=f"TOML configuration path (default: {DEFAULT_CONFIG})",
    )
    check.add_argument(
        "--root",
        type=Path,
        help="override project.root from the configuration",
    )
    check.add_argument(
        "--format",
        choices=("text", "json", "github"),
        default="text",
        help="output format (default: text)",
    )
    check.add_argument(
        "--verbose",
        action="store_true",
        help="include passing checks in text output",
    )
    check.set_defaults(handler=_run_check)

    init = subcommands.add_parser("init", help="write a starter contract configuration")
    init.add_argument(
        "--config",
        type=Path,
        default=Path(DEFAULT_CONFIG),
        help=f"destination path (default: {DEFAULT_CONFIG})",
    )
    init.add_argument("--force", action="store_true", help="replace an existing file")
    init.set_defaults(handler=_run_init)
    return parser


def _print_text(report: Report, *, verbose: bool) -> None:
    print("Copilot Agent Contracts")
    print(f"Config: {report.config_path}")
    print(f"Root:   {report.root}")
    print()
    for result in report.results:
        if result.passed and not verbose:
            continue
        status = "PASS" if result.passed else "FAIL"
        noun = "item" if result.inspected == 1 else "items"
        print(f"{status} {result.check_id} [{result.check_type}] ({result.inspected} {noun})")
        for finding in result.findings:
            location = finding.path
            if finding.line is not None:
                location += f":{finding.line}"
            print(f"  {location}: {finding.message}")

    checks = len(report.results)
    passed = sum(result.passed for result in report.results)
    failed = checks - passed
    print()
    print(f"Checks: {checks}  Passed: {passed}  Failed: {failed}  Findings: {len(report.findings)}")


def _escape_workflow(value: str, *, property_value: bool = False) -> str:
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def _github_annotation(finding: Finding) -> str:
    properties = [f"file={_escape_workflow(finding.path, property_value=True)}"]
    if finding.line is not None:
        properties.append(f"line={finding.line}")
    properties.append(f"title={_escape_workflow(finding.check_id, property_value=True)}")
    message = _escape_workflow(finding.message)
    return f"::error {','.join(properties)}::{message}"


def _print_github(report: Report) -> None:
    for finding in report.findings:
        print(_github_annotation(finding))
    conclusion = "passed" if report.passed else "failed"
    print(
        f"Copilot Agent Contracts {conclusion}: {len(report.results)} checks, "
        f"{len(report.findings)} findings"
    )


def _run_check(args: argparse.Namespace) -> int:
    config = load_config(args.config, args.root)
    report = run_contracts(config)
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    elif args.format == "github":
        _print_github(report)
    else:
        _print_text(report, verbose=args.verbose)
    return 0 if report.passed else 1


def _run_init(args: argparse.Namespace) -> int:
    destination: Path = args.config
    if destination.exists() and not args.force:
        raise ConfigError(f"refusing to replace existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(STARTER_CONFIG, encoding="utf-8", newline="\n")
    print(f"Wrote {destination}")
    print("Edit the starter checks, then run: copilot-agent-contracts check")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
