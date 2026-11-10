"""Tests of the requirements.yaml -> GoogleTest case generator."""

from pathlib import Path

import pytest

import gen_requirement_tests as codegen
from generate_scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[2]


def _req(**verification):
    return [{"id": "REQ-X", "title": "t", "text": "t", "status": "implemented", "verification": [verification]}]


def test_every_requirement_of_the_project_gets_at_least_one_test():
    requirements = codegen.load_requirements(ROOT / "requirements.yaml")
    generated = codegen.generate(requirements)
    assert len(requirements) == 8
    for req in requirements:
        assert f'"{req["id"]}"' in generated


def test_detection_entry_becomes_a_typed_cpp_row():
    generated = codegen.generate(
        _req(check="detection", scenario="loss20_fl", wheel="FL", loss_start_s=80, loss_full_s=85, within_s=120)
    )
    assert '{"REQ-X", "loss20_fl", tiretwin::Wheel::FrontLeft, 80.0, 85.0, 120.0},' in generated


def test_scenario_all_expands_to_every_scenario():
    generated = codegen.generate(_req(check="back_to_back", scenario="all", tolerance=1e-6))
    assert generated.count('"REQ-X"') == len(SCENARIOS)


@pytest.mark.parametrize(
    "verification, message",
    [
        ({"check": "telepathy", "scenario": "loss20_fl"}, "unknown check"),
        ({"check": "no_warning", "scenario": "does_not_exist"}, "unknown scenario"),
        ({"check": "detection", "scenario": "loss20_fl", "wheel": "FL"}, "missing field"),
        ({"check": "no_warning", "scenario": "loss20_fl", "within_s": 3}, "unexpected field"),
        ({"check": "reset", "scenario": "loss20_fl", "wheel": "XX", "reset_s": 1}, "unknown wheel"),
    ],
)
def test_invalid_verification_is_rejected(verification, message):
    with pytest.raises(ValueError, match=message):
        codegen.generate(_req(**verification))


def test_duplicate_requirement_id_is_rejected(tmp_path):
    path = tmp_path / "requirements.yaml"
    entry = "{id: REQ-1, title: t, text: t, status: implemented, verification: []}"
    path.write_text(f"requirements:\n  - {entry}\n  - {entry}\n")
    with pytest.raises(ValueError, match="duplicate"):
        codegen.load_requirements(path)
