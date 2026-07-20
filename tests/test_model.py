from copilot_agent_contracts.model import CheckResult, Finding, Report


def test_findings_serialize_optional_line() -> None:
    without_line = Finding("check", "agent.md", "missing")
    with_line = Finding("check", "agent.md", "forbidden", 7)

    assert without_line.to_dict() == {
        "check": "check",
        "path": "agent.md",
        "message": "missing",
    }
    assert with_line.to_dict()["line"] == 7


def test_failed_result_and_report_serialize() -> None:
    finding = Finding("check", "agent.md", "missing", 2)
    result = CheckResult("check", "sections", 1, (finding,))
    report = Report("contracts.toml", ".", (result,))

    assert not result.passed
    assert not report.passed
    assert report.findings == (finding,)
    assert report.to_dict()["summary"] == {
        "checks": 1,
        "passed": 0,
        "failed": 1,
        "findings": 1,
    }
    assert result.to_dict()["findings"] == [finding.to_dict()]
