#!/usr/bin/env python3
"""Builds the complete test dataset in one go (called by CMake).

For every scenario of data/generate_scenarios.py:

    <name>.log      simulated CAN trace (candump format)
    <name>.csv      algorithm inputs, replayed from the trace with python-can
    <name>.ref.csv  expected outputs, computed by the Python reference

    python tools/build_dataset.py --out build/scenarios
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "data"))

import can_replay  # noqa: E402
import generate_scenarios  # noqa: E402
import py_reference  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="dataset directory")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    for name, scenario in generate_scenarios.SCENARIOS.items():
        log_path = args.out / f"{name}.log"
        csv_path = args.out / f"{name}.csv"
        ref_path = args.out / f"{name}.ref.csv"

        frames = generate_scenarios.write_log(scenario, log_path)
        rows = can_replay.convert(log_path, csv_path)
        mask = py_reference.run(csv_path, ref_path)
        print(f"{name:20s} {frames:7d} frames -> {rows:6d} samples, reference mask 0x{mask:X}")

    print(f"dataset ready in {args.out} ({time.perf_counter() - start:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
