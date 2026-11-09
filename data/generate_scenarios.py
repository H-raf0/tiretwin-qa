#!/usr/bin/env python3
"""Generates the simulated CAN traces (candump .log) used as test stimuli.

Each scenario is a small driving simulation: a speed / steering / brake profile
fed to a kinematic vehicle model whose four tyres have their own rolling radius.
The generator is deterministic (fixed seed per scenario): the same command
always produces the same bytes, so the traces are rebuilt instead of versioned.

    python data/generate_scenarios.py --out build/scenarios
    python data/generate_scenarios.py --list
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import can_codec  # noqa: E402

PERIOD_S = 0.02  # both frames are sent every 20 ms
STATE_FRAME_DELAY_S = 0.001  # VEHICLE_STATE follows WHEEL_SPEEDS on the bus
EPOCH_S = 1_700_000_000.0  # arbitrary fixed start date of every trace
CHANNEL = "vcan0"

# --- Vehicle and tyre model -------------------------------------------------
WHEELBASE_M = 2.7
TRACK_M = 1.55
STEERING_RATIO = 16.0
NOMINAL_RADIUS_M = 0.316  # 205/55 R16
# Rolling radius sensitivity to pressure: -20 % pressure => -0.30 % radius.
RADIUS_LOSS_PER_PRESSURE_LOSS = 0.015
# Effects that the detector does NOT model, so that the simulation is not a
# mirror image of the algorithm:
LOAD_TRANSFER_PER_MS2 = 0.0004  # outer tyres are squashed in corners (radius change per m/s2)
BRAKE_PULL_FRONT = 0.004  # uneven brake torque: left wheels slip more while braking
BRAKE_PULL_REAR = 0.002
# Sensors
WHEEL_SPEED_NOISE_RAD_S = 0.05
VEHICLE_SPEED_NOISE_KMH = 0.05
STEERING_NOISE_DEG = 0.05
STEERING_SLEW_DEG_S = 40.0

WHEELS = ("FL", "FR", "RL", "RR")


@dataclass(frozen=True)
class Phase:
    """A driving segment: the speed ramps linearly to `speed_kmh` over `duration_s`."""

    duration_s: float
    speed_kmh: float
    steering_deg: float = 0.0
    brake: bool = False


@dataclass(frozen=True)
class PressureLoss:
    wheel: str
    start_s: float
    full_s: float  # the loss ramps linearly between start_s and full_s
    fraction: float  # 0.20 = -20 % of the nominal pressure
    repaired_s: float = math.inf  # tyre replaced / re-inflated at this time


@dataclass(frozen=True)
class TyreChange:
    time_s: float
    radius_offsets: tuple[float, float, float, float]  # new manufacturing offsets


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    phases: tuple[Phase, ...]
    seed: int
    losses: tuple[PressureLoss, ...] = ()
    bus_off: tuple[tuple[float, float], ...] = ()  # [start, end) without any frame
    lost_wheel_frames: tuple[float, ...] = ()  # single WHEEL_SPEEDS frames dropped
    tyre_change: TyreChange | None = None
    reset_pulses: tuple[tuple[float, float], ...] = ()
    duration_s: float = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "duration_s", sum(p.duration_s for p in self.phases))


# --- Scenario catalogue -----------------------------------------------------
def _pull_away(speed_kmh: float = 90.0) -> tuple[Phase, ...]:
    return (Phase(15, speed_kmh),)


def _nominal_block(cruise_kmh: float, fast_kmh: float) -> tuple[Phase, ...]:
    """300 s of mixed driving: straights, gentle curves, a roundabout, braking, a stop."""
    return (
        Phase(15, cruise_kmh),
        Phase(60, cruise_kmh),
        Phase(20, cruise_kmh, steering_deg=3.0),
        Phase(20, fast_kmh),
        Phase(40, fast_kmh, steering_deg=-2.5),
        Phase(30, fast_kmh),
        Phase(8, 50, brake=True),
        Phase(15, 50, steering_deg=45.0),
        Phase(10, 50, steering_deg=-60.0),
        Phase(12, cruise_kmh),
        Phase(30, cruise_kmh),
        Phase(10, 0, brake=True),
        Phase(10, 0),
        Phase(20, 70),
    )


def _loss_scenario(wheel: str, seed: int) -> Scenario:
    return Scenario(
        name=f"loss20_{wheel.lower()}",
        description=f"Straight driving, {wheel} loses 20 % of its pressure between t=80 s and t=85 s",
        phases=_pull_away() + (Phase(135, 90), Phase(10, 110), Phase(80, 110)),
        seed=seed,
        losses=(PressureLoss(wheel, 80.0, 85.0, 0.20),),
    )


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        Scenario(
            name="nominal_30min",
            description="30 min of mixed driving with four correctly inflated tyres",
            phases=_nominal_block(90, 110)
            + _nominal_block(80, 130)
            + _nominal_block(90, 110)
            + _nominal_block(70, 100)
            + _nominal_block(90, 130)
            + _nominal_block(80, 110),
            seed=1,
        ),
        _loss_scenario("FL", seed=11),
        _loss_scenario("FR", seed=12),
        _loss_scenario("RL", seed=13),
        _loss_scenario("RR", seed=14),
        Scenario(
            name="corner_brake",
            description="Correct tyres; long tight corners and a long braking phase",
            phases=_pull_away()
            + (
                Phase(50, 90),  # calibration on a straight
                Phase(8, 40, brake=True),
                Phase(40, 40, steering_deg=90.0),  # sustained tight left turn
                Phase(10, 40),
                Phase(40, 40, steering_deg=-90.0),  # sustained tight right turn
                Phase(12, 110),
                Phase(20, 110),
                Phase(30, 50, brake=True),  # long downhill braking
                Phase(15, 90),
                Phase(60, 90),
            ),
            seed=21,
        ),
        Scenario(
            name="can_dropout",
            description="Correct tyres; one lost frame at t=60 s, bus silent from t=100 s to t=103 s",
            phases=_pull_away() + (Phase(135, 90),),
            seed=31,
            bus_off=((100.0, 103.0),),
            lost_wheel_frames=(60.0,),
        ),
        Scenario(
            name="all_four_minus20",
            description="All four tyres lose 20 % of their pressure together (t=80 s to t=85 s)",
            phases=_pull_away() + (Phase(225, 90),),
            seed=41,
            losses=tuple(PressureLoss(w, 80.0, 85.0, 0.20) for w in WHEELS),
        ),
        Scenario(
            name="tyre_change_reset",
            description=(
                "FL loses 20 % at t=80 s; vehicle stops, FL is replaced by a new tyre at "
                "t=180 s, the driver presses reset at t=195 s, then drives on"
            ),
            phases=_pull_away()
            + (
                Phase(135, 90),
                Phase(10, 0, brake=True),
                Phase(40, 0),
                Phase(15, 90),
                Phase(145, 90),
            ),
            seed=51,
            losses=(PressureLoss("FL", 80.0, 85.0, 0.20, repaired_s=180.0),),
            # The new front-left tyre is unworn: +0.30 % radius compared with the old one.
            tyre_change=TyreChange(180.0, (0.0030, 0.0004, -0.0006, 0.0003)),
            reset_pulses=((195.0, 196.0),),
        ),
    )
}


# --- Simulation -------------------------------------------------------------
def _pressure_loss(scenario: Scenario, wheel: str, t: float) -> float:
    total = 0.0
    for loss in scenario.losses:
        if loss.wheel != wheel or t < loss.start_s or t >= loss.repaired_s:
            continue
        progress = min(1.0, (t - loss.start_s) / (loss.full_s - loss.start_s))
        total += loss.fraction * progress
    return total


def simulate(scenario: Scenario):
    """Yields (timestamp_s, can_id, payload) for every frame of the scenario."""
    rng = random.Random(scenario.seed)
    # Tyres are never perfectly identical (wear, manufacturing): +/- 0.1 % radius.
    offsets = [rng.uniform(-0.001, 0.001) for _ in WHEELS]

    steps = round(scenario.duration_s / PERIOD_S)
    phase_index = 0
    phase_start_s = 0.0
    phase_start_speed = 0.0
    steering = 0.0

    for k in range(steps):
        t = k * PERIOD_S
        while t >= phase_start_s + scenario.phases[phase_index].duration_s:
            phase_start_speed = scenario.phases[phase_index].speed_kmh
            phase_start_s += scenario.phases[phase_index].duration_s
            phase_index += 1
        phase = scenario.phases[phase_index]

        progress = (t - phase_start_s) / phase.duration_s
        speed_kmh = phase_start_speed + (phase.speed_kmh - phase_start_speed) * progress
        v = speed_kmh / 3.6
        moving = v > 0.1

        # Steering: phase target + lane-keeping corrections, rate limited.
        target = phase.steering_deg
        if moving:
            target += 0.4 * math.sin(2 * math.pi * 0.07 * t) + 0.2 * math.sin(2 * math.pi * 0.23 * t + 1.0)
        max_step = STEERING_SLEW_DEG_S * PERIOD_S
        steering += max(-max_step, min(max_step, target - steering))

        curvature = math.tan(math.radians(steering) / STEERING_RATIO) / WHEELBASE_M
        lateral_acc = v * v * curvature  # > 0 in a left turn

        if scenario.tyre_change and t >= scenario.tyre_change.time_s:
            offsets = list(scenario.tyre_change.radius_offsets)

        wheel_speeds = []
        for i, wheel in enumerate(WHEELS):
            side = -1.0 if wheel.endswith("L") else 1.0  # left wheels are inside a left turn
            wheel_v = v * (1.0 + side * 0.5 * TRACK_M * curvature)
            radius = (
                NOMINAL_RADIUS_M
                * (1.0 + offsets[i])
                * (1.0 - RADIUS_LOSS_PER_PRESSURE_LOSS * _pressure_loss(scenario, wheel, t))
                * (1.0 - LOAD_TRANSFER_PER_MS2 * lateral_acc * side)
            )
            omega = wheel_v / radius
            if phase.brake and wheel.endswith("L"):
                omega *= 1.0 - (BRAKE_PULL_FRONT if wheel.startswith("F") else BRAKE_PULL_REAR)
            if moving:
                omega += rng.gauss(0.0, WHEEL_SPEED_NOISE_RAD_S)
            wheel_speeds.append(max(0.0, omega))

        state = can_codec.VehicleState(
            speed_kmh=max(0.0, speed_kmh + (rng.gauss(0.0, VEHICLE_SPEED_NOISE_KMH) if moving else 0.0)),
            steering_deg=steering + rng.gauss(0.0, STEERING_NOISE_DEG),
            brake=phase.brake,
            reset=any(start <= t < end for start, end in scenario.reset_pulses),
        )

        # Transmission faults are applied last so that they do not shift the random sequence.
        if any(start <= t < end for start, end in scenario.bus_off):
            continue
        if not any(abs(t - lost) < PERIOD_S / 2 for lost in scenario.lost_wheel_frames):
            yield EPOCH_S + t, can_codec.WHEEL_SPEEDS_ID, can_codec.encode_wheel_speeds(wheel_speeds)
        yield (
            EPOCH_S + t + STATE_FRAME_DELAY_S,
            can_codec.VEHICLE_STATE_ID,
            can_codec.encode_vehicle_state(state),
        )


def write_log(scenario: Scenario, path: Path) -> int:
    """Writes the scenario as a candump log. Returns the number of frames."""
    count = 0
    with open(path, "w", encoding="ascii", newline="\n") as log:
        for timestamp, can_id, payload in simulate(scenario):
            log.write(can_codec.candump_line(timestamp, CHANNEL, can_id, payload) + "\n")
            count += 1
    return count


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="output directory for the .log files")
    parser.add_argument("--only", nargs="*", metavar="NAME", help="generate only these scenarios")
    parser.add_argument("--list", action="store_true", help="list the scenarios and exit")
    args = parser.parse_args(argv)

    if args.list:
        for scenario in SCENARIOS.values():
            print(f"{scenario.name:20s} {scenario.duration_s:6.0f} s  {scenario.description}")
        return 0
    if args.out is None:
        parser.error("--out is required")

    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.only or SCENARIOS:
        frames = write_log(SCENARIOS[name], args.out / f"{name}.log")
        print(f"{name}.log: {frames} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
