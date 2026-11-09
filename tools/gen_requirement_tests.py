#!/usr/bin/env python3
"""Generates the GoogleTest parameter tables from requirements.yaml.

Every entry of a requirement's `verification` list becomes one row of a C++
table; tests/functional/test_requirements.cpp instantiates one parameterised
test per row. Adding a verification to the YAML therefore adds a test without
touching C++ code, and a requirement that points to an unknown scenario or an
unknown check breaks the build instead of being silently ignored.

    python tools/gen_requirement_tests.py requirements.yaml build/generated/requirement_cases.inc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "data"))

from generate_scenarios import SCENARIOS  # noqa: E402

WHEELS = {
    "FL": "tiretwin::Wheel::FrontLeft",
    "FR": "tiretwin::Wheel::FrontRight",
    "RL": "tiretwin::Wheel::RearLeft",
    "RR": "tiretwin::Wheel::RearRight",
}


def _num(value) -> str:
    return repr(float(value))


def _wheel(value) -> str:
    if value not in WHEELS:
        raise ValueError(f"unknown wheel '{value}' (expected one of {', '.join(WHEELS)})")
    return WHEELS[value]


# check name -> (C++ struct, table name, fields after {requirement, scenario})
CHECKS = {
    "detection": ("DetectionCase", "kDetectionCases",
                  [("wheel", _wheel), ("loss_start_s", _num), ("loss_full_s", _num), ("within_s", _num)]),
    "no_warning": ("NoWarningCase", "kNoWarningCases", []),
    "unavailable": ("UnavailableCase", "kUnavailableCases",
                    [("outage_start_s", _num), ("outage_end_s", _num), ("timeout_s", _num)]),
    "back_to_back": ("BackToBackCase", "kBackToBackCases", [("tolerance", _num)]),
    "step_time": ("StepTimeCase", "kStepTimeCases", [("max_ms", _num)]),
    "known_limitation": ("KnownLimitationCase", "kKnownLimitationCases", []),
    "reset": ("ResetCase", "kResetCases", [("wheel", _wheel), ("reset_s", _num)]),
}  # fmt: skip


def load_requirements(path: Path) -> list[dict]:
    """Loads and validates the requirement list."""
    with open(path, encoding="utf-8") as f:
        requirements = yaml.safe_load(f)["requirements"]

    seen = set()
    for req in requirements:
        for key in ("id", "title", "text", "status", "verification"):
            if key not in req:
                raise ValueError(f"{req.get('id', '<no id>')}: missing field '{key}'")
        if req["id"] in seen:
            raise ValueError(f"duplicate requirement id {req['id']}")
        seen.add(req["id"])
    return requirements


def generate(requirements: list[dict]) -> str:
    rows: dict[str, list[str]] = {check: [] for check in CHECKS}

    for req in requirements:
        for entry in req["verification"]:
            where = f"{req['id']} / {entry}"
            check = entry.get("check")
            if check not in CHECKS:
                raise ValueError(f"{where}: unknown check (expected one of {', '.join(CHECKS)})")
            fields = CHECKS[check][2]

            unknown = set(entry) - {"check", "scenario"} - {name for name, _ in fields}
            if unknown:
                raise ValueError(f"{where}: unexpected field(s) {sorted(unknown)}")

            scenario = entry.get("scenario")
            scenarios = list(SCENARIOS) if scenario == "all" else [scenario]
            for name in scenarios:
                if name not in SCENARIOS:
                    raise ValueError(f"{where}: unknown scenario '{name}'")
                try:
                    values = [convert(entry[field]) for field, convert in fields]
                except KeyError as missing:
                    raise ValueError(f"{where}: missing field {missing}") from None
                rows[check].append(", ".join([f'"{req["id"]}"', f'"{name}"', *values]))

    lines = [
        "// AUTO-GENERATED from requirements.yaml by tools/gen_requirement_tests.py.",
        "// Do not edit: change requirements.yaml and rebuild.",
        "",
    ]
    for check, (struct, table, _) in CHECKS.items():
        lines.append(f"const std::vector<{struct}> {table} = {{")
        lines.extend(f"    {{{row}}}," for row in rows[check])
        lines.append("};")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("requirements", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    try:
        content = generate(load_requirements(args.requirements))
    except ValueError as error:
        print(f"{args.requirements}: error: {error}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
