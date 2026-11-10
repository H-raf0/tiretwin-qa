#!/usr/bin/env python3
"""Builds the requirement <-> test <-> result traceability matrix.

Inputs : requirements.yaml and the JUnit XML reports written by the test runs
         (GoogleTest `--gtest_output=xml:` and/or `pytest --junitxml`).
Outputs: a Markdown and/or a standalone HTML report.

A test is linked to a requirement by the `requirement` property it records
(`RecordProperty("requirement", "REQ-001")` in GoogleTest). With --strict the
tool is a quality gate: it exits with 1 if a requirement has no test, has a
failed test, or if its declared status disagrees with the results.

    python tools/traceability.py --requirements requirements.yaml \
        --junit build/reports/*.xml --md traceability.md --html traceability.html --strict
"""

from __future__ import annotations

import argparse
import datetime
import glob
import html
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PASS, FAIL, XFAIL, SKIPPED = "PASS", "FAIL", "XFAIL", "SKIPPED"
NOT_COVERED, LIMITATION, INCOMPLETE = "NOT COVERED", "KNOWN LIMITATION", "INCOMPLETE"

LABELS = {
    PASS: "Réussi",
    FAIL: "Échec",
    XFAIL: "Échec attendu",
    SKIPPED: "Non exécuté",
    NOT_COVERED: "Non couverte",
    LIMITATION: "Limitation connue",
    INCOMPLETE: "Incomplète",
}
ICONS = {PASS: "✅", FAIL: "❌", XFAIL: "⚠️", SKIPPED: "⏭️", NOT_COVERED: "❌", LIMITATION: "⚠️", INCOMPLETE: "❌"}
# Properties that are links or flags, not measurements worth displaying.
_HIDDEN_PROPERTIES = {"requirement", "scenario", "known_limitation"}


@dataclass
class TestResult:
    name: str
    result: str
    time_s: float
    properties: dict[str, str]

    @property
    def requirement(self) -> str | None:
        return self.properties.get("requirement")

    @property
    def measures(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in self.properties.items() if k not in _HIDDEN_PROPERTIES)


@dataclass
class Requirement:
    id: str
    title: str
    status: str
    tests: list[TestResult] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        results = {t.result for t in self.tests}
        if not results:
            return NOT_COVERED
        if FAIL in results:
            return FAIL
        if XFAIL in results:
            return LIMITATION
        if SKIPPED in results:
            return INCOMPLETE
        return PASS

    @property
    def consistent(self) -> bool:
        """The declared status must match what the tests show."""
        expected = LIMITATION if self.status == "known_limitation" else PASS
        return self.verdict == expected


def parse_junit(path: Path) -> list[TestResult]:
    """Reads the test cases of a JUnit XML file (GoogleTest and pytest dialects)."""
    results = []
    for case in ET.parse(path).getroot().iter("testcase"):
        # Properties: child elements (pytest, GoogleTest >= 1.15) ...
        properties = {p.get("name"): p.get("value", "") for p in case.iter("property")}
        # ... or plain XML attributes (older GoogleTest).
        standard = {"name", "classname", "status", "result", "time", "timestamp", "file", "line",
                    "value_param", "type_param"}  # fmt: skip
        properties.update({k: v for k, v in case.attrib.items() if k not in standard})

        if case.find("failure") is not None or case.find("error") is not None:
            result = FAIL
        elif case.find("skipped") is not None or case.get("result") == "skipped" or case.get("status") == "notrun":
            result = XFAIL if properties.get("known_limitation") == "true" else SKIPPED
        else:
            result = PASS

        classname = case.get("classname", "")
        name = f"{classname}.{case.get('name')}" if classname else case.get("name")
        results.append(TestResult(name, result, float(case.get("time", 0.0)), properties))
    return results


def build_matrix(requirements_path: Path, junit_paths: list[Path]):
    """Returns (requirements with their tests, untraced tests, orphan tests)."""
    with open(requirements_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)["requirements"]
    requirements = {r["id"]: Requirement(r["id"], r["title"], r.get("status", "implemented")) for r in data}

    untraced, orphans = [], []
    for path in junit_paths:
        for test in parse_junit(path):
            if test.requirement is None:
                untraced.append(test)
            elif test.requirement in requirements:
                requirements[test.requirement].tests.append(test)
            else:
                orphans.append(test)  # points to a requirement that does not exist
    return list(requirements.values()), untraced, orphans


def problems(requirements, orphans) -> list[str]:
    """Everything that makes the quality gate fail."""
    issues = []
    for req in requirements:
        if req.verdict in (FAIL, NOT_COVERED, INCOMPLETE):
            issues.append(f"{req.id}: {req.verdict}")
        elif not req.consistent:
            issues.append(f"{req.id}: status '{req.status}' in requirements.yaml but tests say {req.verdict}")
    issues += [f"{t.name}: linked to unknown requirement {t.requirement}" for t in orphans]
    return issues


def _summary(requirements, untraced) -> list[str]:
    counts = {v: sum(r.verdict == v for r in requirements) for v in (PASS, LIMITATION, FAIL, NOT_COVERED, INCOMPLETE)}
    lines = [
        f"{len(requirements)} exigences : {counts[PASS]} vérifiées, "
        f"{counts[LIMITATION]} limitation(s) connue(s), {counts[FAIL]} en échec, "
        f"{counts[NOT_COVERED] + counts[INCOMPLETE]} non couverte(s) ou incomplète(s).",
        f"{sum(len(r.tests) for r in requirements)} tests de validation liés à une exigence.",
    ]
    if untraced:
        failed = sum(t.result == FAIL for t in untraced)
        lines.append(
            f"{len(untraced)} autres tests (unitaires, outillage) : "
            f"{len(untraced) - failed} réussis, {failed} en échec."
        )
    return lines


def render_markdown(requirements, untraced, orphans, revision: str, date: str) -> str:
    out = ["# Matrice de traçabilité — TireTwin-QA", "", f"Révision `{revision}` — générée le {date}.", ""]
    out += [f"- {line}" for line in _summary(requirements, untraced)]
    out += ["", "## Synthèse par exigence", "", "| Exigence | Intitulé | Tests | Verdict |", "|---|---|---|---|"]
    for r in requirements:
        passed = sum(t.result == PASS for t in r.tests)
        out.append(f"| {r.id} | {r.title} | {passed}/{len(r.tests)} | {ICONS[r.verdict]} {LABELS[r.verdict]} |")

    out += ["", "## Détail exigence ↔ test ↔ résultat", "",
            "| Exigence | Test | Scénario | Résultat | Mesures |", "|---|---|---|---|---|"]  # fmt: skip
    for r in requirements:
        if not r.tests:
            out.append(f"| {r.id} | *aucun test* | | {ICONS[NOT_COVERED]} {LABELS[NOT_COVERED]} | |")
        for t in r.tests:
            out.append(
                f"| {r.id} | `{t.name}` | {t.properties.get('scenario', '')} "
                f"| {ICONS[t.result]} {LABELS[t.result]} | {t.measures} |"
            )

    issues = problems(requirements, orphans)
    if issues:
        out += ["", "## Écarts", ""] + [f"- {issue}" for issue in issues]
    return "\n".join(out) + "\n"


_CSS = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#1f2933}
h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid #d9dee4;padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:#f1f4f8}code{font-size:.8rem;word-break:break-all}
.badge{display:inline-block;padding:.1rem .5rem;border-radius:.6rem;font-weight:600;font-size:.8rem;white-space:nowrap}
.PASS{background:#d8f3dc;color:#1b5e20}.FAIL,.NOT,.INCOMPLETE{background:#fde0e0;color:#a31515}
.XFAIL,.KNOWN{background:#fff1c9;color:#7a5200}.SKIPPED{background:#e6e9ee;color:#47525e}
.meta{color:#5b6672}.issues{color:#a31515}
"""


def _badge(verdict: str) -> str:
    return f'<span class="badge {verdict.split()[0]}">{html.escape(LABELS[verdict])}</span>'


def render_html(requirements, untraced, orphans, revision: str, date: str) -> str:
    e = html.escape
    out = [
        "<!DOCTYPE html>", '<html lang="fr"><head><meta charset="utf-8">',
        "<title>Matrice de traçabilité — TireTwin-QA</title>", f"<style>{_CSS}</style></head><body>",
        "<h1>Matrice de traçabilité — TireTwin-QA</h1>",
        f'<p class="meta">Révision <code>{e(revision)}</code> — générée le {e(date)}.</p>', "<ul>",
    ]  # fmt: skip
    out += [f"<li>{e(line)}</li>" for line in _summary(requirements, untraced)]
    out += ["</ul>", "<h2>Synthèse par exigence</h2>",
            "<table><tr><th>Exigence</th><th>Intitulé</th><th>Tests</th><th>Verdict</th></tr>"]  # fmt: skip
    for r in requirements:
        passed = sum(t.result == PASS for t in r.tests)
        out.append(
            f"<tr><td>{e(r.id)}</td><td>{e(r.title)}</td>"
            f"<td>{passed}/{len(r.tests)}</td><td>{_badge(r.verdict)}</td></tr>"
        )
    out += ["</table>", "<h2>Détail exigence ↔ test ↔ résultat</h2>",
            "<table><tr><th>Exigence</th><th>Test</th><th>Scénario</th><th>Résultat</th><th>Mesures</th></tr>"]  # fmt: skip
    for r in requirements:
        if not r.tests:
            out.append(f"<tr><td>{e(r.id)}</td><td><em>aucun test</em></td><td></td><td>{_badge(NOT_COVERED)}</td><td></td></tr>")
        for i, t in enumerate(r.tests):
            first = f'<td rowspan="{len(r.tests)}">{e(r.id)}</td>' if i == 0 else ""
            out.append(
                f"<tr>{first}<td><code>{e(t.name)}</code></td><td>{e(t.properties.get('scenario', ''))}</td>"
                f"<td>{_badge(t.result)}</td><td>{e(t.measures)}</td></tr>"
            )
    out.append("</table>")
    issues = problems(requirements, orphans)
    if issues:
        out += ['<h2>Écarts</h2><ul class="issues">'] + [f"<li>{e(i)}</li>" for i in issues] + ["</ul>"]
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--junit", nargs="+", required=True, metavar="XML",
                        help="JUnit report(s); glob patterns are expanded")  # fmt: skip
    parser.add_argument("--md", type=Path, help="Markdown output")
    parser.add_argument("--html", type=Path, help="HTML output")
    parser.add_argument("--revision", default="local", help="software revision shown in the report")
    parser.add_argument("--strict", action="store_true", help="exit with 1 on any traceability gap")
    args = parser.parse_args(argv)

    junit_paths = sorted({Path(p) for pattern in args.junit for p in (glob.glob(pattern) or [pattern])})
    missing = [str(p) for p in junit_paths if not p.is_file()]
    if missing:
        print(f"error: JUnit report not found: {', '.join(missing)}", file=sys.stderr)
        return 2

    requirements, untraced, orphans = build_matrix(args.requirements, junit_paths)
    date = datetime.date.today().isoformat()
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(render_markdown(requirements, untraced, orphans, args.revision, date), encoding="utf-8", newline="\n")
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(requirements, untraced, orphans, args.revision, date), encoding="utf-8", newline="\n")

    for req in requirements:
        print(f"{req.id}  {req.verdict:17s} {len(req.tests)} test(s)  {req.title}".encode("ascii", "replace").decode())
    issues = problems(requirements, orphans)
    for issue in issues:
        print(f"GAP: {issue}", file=sys.stderr)
    return 1 if (args.strict and issues) else 0


if __name__ == "__main__":
    sys.exit(main())
