#!/usr/bin/env python3
"""Python reference implementation of the under-inflation detector.

This is the executable specification of the algorithm: short, readable, written
independently of the C++ code structure but with the same arithmetic. The
back-to-back tests (REQ-005) run both implementations on the same inputs and
require identical outputs, so any change must be made on both sides.

    python tools/py_reference.py input.csv output.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path

UNAVAILABLE, CALIBRATING, MONITORING, WARNING = 0, 1, 2, 3
FL, FR, RL, RR = 0, 1, 2, 3

OUTPUT_HEADER = [
    "t_s", "status", "warning_mask", "usable",
    "dev_fl_pct", "dev_fr_pct", "dev_rl_pct", "dev_rr_pct",
]  # fmt: skip

MIN_WHEEL_SPEED_RAD_S = 1.0


@dataclass
class Config:
    """Must stay identical to algo/include/tiretwin/config.hpp."""

    sample_period_s: float = 0.02
    signal_timeout_s: float = 0.2
    lowpass_tau_s: float = 0.1
    min_speed_kmh: float = 20.0
    max_steering_deg: float = 10.0
    settle_time_s: float = 1.0
    wheelbase_m: float = 2.7
    track_width_m: float = 1.55
    steering_ratio: float = 16.0
    calibration_time_s: float = 30.0
    window_s: float = 10.0
    threshold: float = 0.0010
    confirm_time_s: float = 10.0


@dataclass
class Sample:
    wheel_speed_rad_s: tuple
    vehicle_speed_kmh: float
    steering_angle_deg: float
    brake_active: bool = False
    reset_request: bool = False
    signal_age_s: float = 0.0


@dataclass
class Output:
    status: int
    warning_mask: int
    usable: bool
    deviation_pct: tuple


def _to_samples(duration_s: float, period_s: float) -> int:
    # Same rounding as std::round (half away from zero) for positive values.
    return max(1, math.floor(duration_s / period_s + 0.5))


class _Axle:
    def __init__(self, window_samples: int):
        self.calibration_sum = 0.0
        self.offset = 0.0
        self.window = [0.0] * window_samples
        self.head = 0
        self.count = 0
        self.window_sum = 0.0
        self.average = 0.0
        self.left_suspect = 0
        self.right_suspect = 0


class UnderInflationDetector:
    def __init__(self, config: Config | None = None):
        self.cfg = config or Config()
        c = self.cfg
        self._alpha = c.sample_period_s / (c.lowpass_tau_s + c.sample_period_s)
        self._settle_samples = _to_samples(c.settle_time_s, c.sample_period_s)
        self._calibration_samples = _to_samples(c.calibration_time_s, c.sample_period_s)
        self._window_samples = _to_samples(c.window_s, c.sample_period_s)
        self._confirm_samples = _to_samples(c.confirm_time_s, c.sample_period_s)
        # Input conditioning state
        self._filtered = [0.0] * 4
        self._initialised = False
        self._settle_remaining = self._settle_samples
        self.reset()

    def reset(self) -> None:
        self._axles = [_Axle(self._window_samples), _Axle(self._window_samples)]
        self._calibration_count = 0
        self._calibrated = False
        self._warning_mask = 0

    # -- input conditioning: returns (available, usable) ------------------------
    def _condition(self, s: Sample) -> tuple[bool, bool]:
        values = (*s.wheel_speed_rad_s, s.vehicle_speed_kmh, s.steering_angle_deg, s.signal_age_s)
        available = all(math.isfinite(v) for v in values) and s.signal_age_s <= self.cfg.signal_timeout_s
        if not available:
            self._initialised = False
            self._settle_remaining = self._settle_samples
            return False, False

        if not self._initialised:
            self._filtered = list(s.wheel_speed_rad_s)
            self._initialised = True
        else:
            for i in range(4):
                self._filtered[i] += self._alpha * (s.wheel_speed_rad_s[i] - self._filtered[i])

        representative = (
            s.vehicle_speed_kmh >= self.cfg.min_speed_kmh
            and abs(s.steering_angle_deg) <= self.cfg.max_steering_deg
            and not s.brake_active
            and all(w > MIN_WHEEL_SPEED_RAD_S for w in self._filtered)
        )
        if not representative:
            self._settle_remaining = self._settle_samples
            return True, False
        if self._settle_remaining > 0:
            self._settle_remaining -= 1
            return True, False
        return True, True

    # -- detection -------------------------------------------------------------
    def step(self, s: Sample) -> Output:
        available, usable = self._condition(s)
        if not available:
            return self._output(UNAVAILABLE, False)

        if s.reset_request:
            self.reset()

        if usable:
            w = self._filtered
            road_wheel_angle = s.steering_angle_deg * (math.pi / 180.0) / self.cfg.steering_ratio
            curvature = math.tan(road_wheel_angle) / self.cfg.wheelbase_m
            correction = 0.5 * self.cfg.track_width_m * curvature

            front = (w[FL] - w[FR]) / (w[FL] + w[FR]) + correction
            rear = (w[RL] - w[RR]) / (w[RL] + w[RR]) + correction

            if not self._calibrated:
                self._axles[0].calibration_sum += front
                self._axles[1].calibration_sum += rear
                self._calibration_count += 1
                if self._calibration_count >= self._calibration_samples:
                    for axle in self._axles:
                        axle.offset = axle.calibration_sum / float(self._calibration_count)
                    self._calibrated = True
            else:
                self._update_axle(self._axles[0], front, FL, FR)
                self._update_axle(self._axles[1], rear, RL, RR)

        if self._warning_mask:
            status = WARNING
        elif self._calibrated:
            status = MONITORING
        else:
            status = CALIBRATING
        return self._output(status, usable)

    def _update_axle(self, axle: _Axle, deviation: float, left: int, right: int) -> None:
        calibrated = deviation - axle.offset
        axle.window_sum += calibrated - axle.window[axle.head]
        axle.window[axle.head] = calibrated
        axle.head = (axle.head + 1) % self._window_samples
        if axle.count < self._window_samples:
            axle.count += 1
        if axle.count < self._window_samples:
            return

        axle.average = axle.window_sum / float(self._window_samples)
        if axle.average > self.cfg.threshold:
            axle.left_suspect += 1
            axle.right_suspect = 0
        elif axle.average < -self.cfg.threshold:
            axle.right_suspect += 1
            axle.left_suspect = 0
        else:
            axle.left_suspect = 0
            axle.right_suspect = 0

        if axle.left_suspect >= self._confirm_samples:
            self._warning_mask |= 1 << left
        if axle.right_suspect >= self._confirm_samples:
            self._warning_mask |= 1 << right

    def _output(self, status: int, usable: bool) -> Output:
        front, rear = self._axles[0].average, self._axles[1].average
        return Output(
            status=status,
            warning_mask=self._warning_mask,
            usable=usable,
            deviation_pct=(100.0 * front, -100.0 * front, 100.0 * rear, -100.0 * rear),
        )


def read_input_csv(path: Path):
    """Yields (t_s, Sample) from a CSV written by can_replay.py."""
    with open(path, newline="", encoding="ascii") as f:
        for row in csv.DictReader(f):
            yield float(row["t_s"]), Sample(
                wheel_speed_rad_s=(
                    float(row["w_fl"]), float(row["w_fr"]), float(row["w_rl"]), float(row["w_rr"]),
                ),  # fmt: skip
                vehicle_speed_kmh=float(row["v_kmh"]),
                steering_angle_deg=float(row["steer_deg"]),
                brake_active=row["brake"] != "0",
                reset_request=row["reset"] != "0",
                signal_age_s=float(row["age_s"]),
            )


def run(input_csv: Path, output_csv: Path) -> int:
    """Runs the reference on an input CSV. Returns the final warning mask."""
    detector = UnderInflationDetector()
    mask = 0
    with open(output_csv, "w", newline="", encoding="ascii") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(OUTPUT_HEADER)
        for t_s, sample in read_input_csv(input_csv):
            out = detector.step(sample)
            mask = out.warning_mask
            # repr() round-trips a double exactly: nothing is lost before the comparison.
            writer.writerow(
                [f"{t_s:.2f}", out.status, out.warning_mask, int(out.usable)]
                + [repr(d) for d in out.deviation_pct]
            )
    return mask


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="input CSV (from can_replay.py)")
    parser.add_argument("output", type=Path, help="output CSV")
    args = parser.parse_args(argv)
    mask = run(args.input, args.output)
    print(f"{args.output}: final warning mask 0x{mask:X} (FL=1 FR=2 RL=4 RR=8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
