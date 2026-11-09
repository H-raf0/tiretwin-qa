#!/usr/bin/env python3
"""Replays a candump log and produces the input table of the algorithm (CSV).

The embedded algorithm is a periodic 20 ms task: at each activation it reads the
last value received for every signal. This tool reproduces that behaviour
(zero-order hold) and adds the age of the oldest signal, which is what lets the
algorithm detect a silent bus (REQ-004).

    python tools/can_replay.py trace.log trace.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import can

sys.path.insert(0, str(Path(__file__).resolve().parent))

import can_codec  # noqa: E402

PERIOD_S = 0.02
# The task samples in the middle of the bus cycle, away from the frame instants,
# so that reception jitter cannot move a frame from one activation to the next.
SAMPLING_OFFSET_S = PERIOD_S / 2

HEADER = ["t_s", "w_fl", "w_fr", "w_rl", "w_rr", "v_kmh", "steer_deg", "brake", "reset", "age_s"]


def replay(messages, period_s: float = PERIOD_S):
    """Yields one CSV row per task activation from an iterable of can.Message.

    The first activation happens once both frames have been received at least once.
    """
    wheels = None
    state = None
    wheels_rx_s = state_rx_s = 0.0
    t0 = None
    tick = 0

    def row(now_s: float):
        return [
            f"{tick * period_s:.2f}",
            *(f"{w:.3f}" for w in wheels),
            f"{state.speed_kmh:.2f}",
            f"{state.steering_deg:.1f}",
            int(state.brake),
            int(state.reset),
            f"{now_s - min(wheels_rx_s, state_rx_s):.3f}",
        ]

    for msg in messages:
        if t0 is None:
            t0 = msg.timestamp
        # Run every activation that is due before this frame arrives.
        while wheels is not None and state is not None:
            now_s = t0 + tick * period_s + SAMPLING_OFFSET_S
            if now_s >= msg.timestamp:
                break
            yield row(now_s)
            tick += 1
        if wheels is None or state is None:
            # Still waiting for the first complete data set: skip these activations.
            while t0 + tick * period_s + SAMPLING_OFFSET_S <= msg.timestamp:
                tick += 1

        if msg.arbitration_id == can_codec.WHEEL_SPEEDS_ID:
            wheels = can_codec.decode_wheel_speeds(msg.data)
            wheels_rx_s = msg.timestamp
        elif msg.arbitration_id == can_codec.VEHICLE_STATE_ID:
            state = can_codec.decode_vehicle_state(msg.data)
            state_rx_s = msg.timestamp

    if wheels is not None and state is not None:
        yield row(t0 + tick * period_s + SAMPLING_OFFSET_S)


def convert(log_path: Path, csv_path: Path) -> int:
    """Converts a candump .log into the algorithm input CSV. Returns the row count."""
    rows = 0
    reader = can.LogReader(str(log_path))
    try:
        with open(csv_path, "w", encoding="ascii", newline="") as out:
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(HEADER)
            for row in replay(reader):
                writer.writerow(row)
                rows += 1
    finally:
        reader.stop()
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("log", type=Path, help="candump log file (.log)")
    parser.add_argument("csv", type=Path, help="output CSV")
    args = parser.parse_args(argv)
    rows = convert(args.log, args.csv)
    print(f"{args.csv}: {rows} samples")
    return 0


if __name__ == "__main__":
    sys.exit(main())
