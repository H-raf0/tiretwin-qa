"""Tests of the stimulus chain: CAN encoding -> candump log -> python-can replay -> CSV.

The C++ tests trust the CSV files they read; these tests are what justifies that trust.
"""

import csv
import re

import can
import pytest

import can_codec
import can_replay
import generate_scenarios as gen


def test_wheel_speeds_survive_encoding_within_one_lsb():
    speeds = (79.1234, 80.0, 0.0, 123.4567)
    decoded = can_codec.decode_wheel_speeds(can_codec.encode_wheel_speeds(speeds))
    assert decoded == pytest.approx(speeds, abs=can_codec.WHEEL_SPEED_SCALE / 2)


@pytest.mark.parametrize("steering_deg", [-540.0, -0.1, 0.0, 12.3, 540.0])
def test_vehicle_state_round_trip_keeps_sign_and_flags(steering_deg):
    state = can_codec.VehicleState(speed_kmh=88.88, steering_deg=steering_deg, brake=True, reset=False)
    decoded = can_codec.decode_vehicle_state(can_codec.encode_vehicle_state(state))
    assert decoded.speed_kmh == pytest.approx(88.88, abs=0.005)
    assert decoded.steering_deg == pytest.approx(steering_deg, abs=0.05)
    assert (decoded.brake, decoded.reset) == (True, False)


def test_out_of_range_values_saturate_instead_of_wrapping():
    assert can_codec.decode_wheel_speeds(can_codec.encode_wheel_speeds((1e6, -5.0, 0, 0)))[:2] == (
        pytest.approx(0xFFFF * can_codec.WHEEL_SPEED_SCALE),
        0.0,
    )


def test_generated_log_is_valid_candump_and_readable_by_python_can(tmp_path):
    log = tmp_path / "trace.log"
    frames = gen.write_log(gen.SCENARIOS["can_dropout"], log)

    lines = log.read_text().splitlines()
    assert len(lines) == frames
    assert all(re.fullmatch(r"\(\d+\.\d{6}\) vcan0 10[01]#[0-9A-F]+", line) for line in lines)

    messages = list(can.LogReader(str(log)))
    assert len(messages) == frames
    assert {m.arbitration_id for m in messages} == {can_codec.WHEEL_SPEEDS_ID, can_codec.VEHICLE_STATE_ID}
    assert all(m.dlc == (8 if m.arbitration_id == can_codec.WHEEL_SPEEDS_ID else 5) for m in messages)


def test_generation_is_deterministic(tmp_path):
    first, second = tmp_path / "a.log", tmp_path / "b.log"
    gen.write_log(gen.SCENARIOS["loss20_fl"], first)
    gen.write_log(gen.SCENARIOS["loss20_fl"], second)
    assert first.read_bytes() == second.read_bytes()


def _message(t, can_id, data):
    return can.Message(timestamp=t, arbitration_id=can_id, data=data, is_extended_id=False)


def _cycle(t, speed_rad_s=80.0):
    """The two frames of one 20 ms bus cycle."""
    state = can_codec.VehicleState(speed_kmh=90.0, steering_deg=0.0, brake=False, reset=False)
    return [
        _message(t, can_codec.WHEEL_SPEEDS_ID, can_codec.encode_wheel_speeds([speed_rad_s] * 4)),
        _message(t + 0.001, can_codec.VEHICLE_STATE_ID, can_codec.encode_vehicle_state(state)),
    ]


def test_replay_emits_one_row_per_period_with_fresh_data():
    messages = [m for k in range(5) for m in _cycle(100.0 + 0.02 * k, speed_rad_s=80.0 + k)]
    rows = list(can_replay.replay(messages))

    assert [row[0] for row in rows] == ["0.00", "0.02", "0.04", "0.06", "0.08"]
    assert [row[1] for row in rows] == ["80.000", "81.000", "82.000", "83.000", "84.000"]
    assert all(float(row[-1]) == pytest.approx(0.010) for row in rows)


def test_replay_holds_last_values_and_reports_their_age_during_a_bus_outage():
    # Two cycles, 0.5 s of silence, one cycle.
    messages = _cycle(100.00, 80.0) + _cycle(100.02, 81.0) + _cycle(100.52, 90.0)
    rows = list(can_replay.replay(messages))

    assert len(rows) == 27  # the task keeps running during the outage
    during_outage = rows[2:26]
    assert all(row[1] == "81.000" for row in during_outage), "last received value must be held"
    ages = [float(row[-1]) for row in during_outage]
    assert ages == sorted(ages) and ages[-1] == pytest.approx(0.49)
    assert rows[26][1] == "90.000" and float(rows[26][-1]) == pytest.approx(0.010)


def test_replay_reports_the_age_of_the_oldest_signal_when_one_frame_is_lost():
    messages = _cycle(100.00) + _cycle(100.02)[1:] + _cycle(100.04)  # WHEEL_SPEEDS lost once
    ages = [float(row[-1]) for row in can_replay.replay(messages)]
    assert ages == pytest.approx([0.010, 0.030, 0.010])


def test_convert_writes_the_csv_expected_by_the_cpp_reader(tmp_path):
    log, table = tmp_path / "trace.log", tmp_path / "trace.csv"
    scenario = gen.SCENARIOS["can_dropout"]
    gen.write_log(scenario, log)
    rows = can_replay.convert(log, table)

    assert rows == round(scenario.duration_s / gen.PERIOD_S)
    with open(table, newline="") as f:
        content = list(csv.reader(f))
    assert content[0] == can_replay.HEADER
    assert all(len(row) == len(can_replay.HEADER) for row in content)
    assert b"\r" not in table.read_bytes()
