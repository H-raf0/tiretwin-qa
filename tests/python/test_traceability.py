"""Tests of the traceability tool: a quality gate must itself be tested,
in particular its ability to say "no"."""

import textwrap

import pytest

import traceability as tr

REQUIREMENTS = """
requirements:
  - {id: REQ-A, title: Detects, status: implemented}
  - {id: REQ-B, title: Limitation, status: known_limitation}
"""


def _write(tmp_path, junit_body, requirements=REQUIREMENTS):
    req = tmp_path / "requirements.yaml"
    req.write_text(requirements, encoding="utf-8")
    junit = tmp_path / "report.xml"
    junit.write_text(f"<testsuites><testsuite>{textwrap.dedent(junit_body)}</testsuite></testsuites>", encoding="utf-8")
    return req, junit


def _case(name, requirement=None, inner="", extra=""):
    prop = f'<properties><property name="requirement" value="{requirement}"/>{extra}</properties>' if requirement else ""
    return f'<testcase classname="Suite" name="{name}" time="0.5">{prop}{inner}</testcase>'


XFAIL = _case("b", "REQ-B", "<skipped/>", '<property name="known_limitation" value="true"/>')


def _run(tmp_path, junit_body, strict=True):
    req, junit = _write(tmp_path, junit_body)
    args = ["--requirements", str(req), "--junit", str(junit), "--md", str(tmp_path / "m.md"),
            "--html", str(tmp_path / "m.html")]  # fmt: skip
    return tr.main(args + (["--strict"] if strict else []))


def test_all_requirements_verified_passes_the_gate(tmp_path):
    assert _run(tmp_path, _case("a", "REQ-A") + XFAIL + _case("unit")) == 0

    markdown = (tmp_path / "m.md").read_text(encoding="utf-8")
    assert "| REQ-A | Detects | 1/1 | ✅ Réussi |" in markdown
    assert "| REQ-B | Limitation | 0/1 | ⚠️ Limitation connue |" in markdown
    assert "`Suite.a`" in markdown
    assert "<td>REQ-A</td>" in (tmp_path / "m.html").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "junit_body, expected_gap",
    [
        (_case("a", "REQ-A", "<failure/>") + XFAIL, "REQ-A: FAIL"),
        (XFAIL, "REQ-A: NOT COVERED"),
        (_case("a", "REQ-A", "<skipped/>") + XFAIL, "REQ-A: INCOMPLETE"),
        # A known limitation whose test passes must be re-qualified, not ignored.
        (_case("a", "REQ-A") + _case("b", "REQ-B"), "REQ-B: status 'known_limitation'"),
        # ... and an implemented requirement cannot hide behind an expected failure.
        (_case("a", "REQ-A", "<skipped/>", '<property name="known_limitation" value="true"/>') + XFAIL,
         "REQ-A: status 'implemented'"),
        (_case("a", "REQ-A") + XFAIL + _case("typo", "REQ-Z"), "unknown requirement REQ-Z"),
    ],
    ids=["failed-test", "no-test", "skipped-test", "limitation-now-passing", "undeclared-limitation", "orphan-link"],
)  # fmt: skip
def test_gaps_fail_the_strict_gate(tmp_path, capsys, junit_body, expected_gap):
    assert _run(tmp_path, junit_body) == 1
    assert expected_gap in capsys.readouterr().err
    assert "## Écarts" in (tmp_path / "m.md").read_text(encoding="utf-8")


def test_without_strict_the_report_is_written_and_the_exit_code_is_zero(tmp_path):
    assert _run(tmp_path, _case("a", "REQ-A", "<failure/>"), strict=False) == 0
    assert "❌ Échec" in (tmp_path / "m.md").read_text(encoding="utf-8")


def test_requirement_given_as_xml_attribute_is_understood(tmp_path):
    """Older GoogleTest versions write RecordProperty() values as attributes."""
    body = '<testcase classname="S" name="a" status="run" result="completed" time="0" requirement="REQ-A"/>'
    assert _run(tmp_path, body + XFAIL) == 0


def test_missing_report_is_an_error_not_an_empty_matrix(tmp_path):
    req, _ = _write(tmp_path, "")
    assert tr.main(["--requirements", str(req), "--junit", str(tmp_path / "nope.xml")]) == 2
