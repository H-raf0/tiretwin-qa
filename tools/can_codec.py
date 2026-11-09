"""CAN layout of the simulated vehicle bus, shared by the generator and the replay tool.

Two periodic frames (20 ms), little-endian (Intel) signals:

    0x100 WHEEL_SPEEDS   DLC 8   4 x uint16, 0.005 rad/s/bit   order FL, FR, RL, RR
    0x101 VEHICLE_STATE  DLC 5   uint16 speed    0.01 km/h/bit
                                 int16  steering 0.1 deg/bit (positive = left turn)
                                 uint8  flags    bit0 = brake, bit1 = TPMS reset request
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

WHEEL_SPEEDS_ID = 0x100
VEHICLE_STATE_ID = 0x101

WHEEL_SPEED_SCALE = 0.005  # rad/s per bit
VEHICLE_SPEED_SCALE = 0.01  # km/h per bit
STEERING_SCALE = 0.1  # deg per bit

FLAG_BRAKE = 0x01
FLAG_RESET = 0x02

_WHEEL_STRUCT = struct.Struct("<4H")
_STATE_STRUCT = struct.Struct("<HhB")


@dataclass(frozen=True)
class VehicleState:
    speed_kmh: float
    steering_deg: float
    brake: bool
    reset: bool


def _saturate(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def encode_wheel_speeds(speeds_rad_s) -> bytes:
    raw = [_saturate(round(w / WHEEL_SPEED_SCALE), 0, 0xFFFF) for w in speeds_rad_s]
    return _WHEEL_STRUCT.pack(*raw)


def decode_wheel_speeds(data: bytes) -> tuple[float, float, float, float]:
    return tuple(raw * WHEEL_SPEED_SCALE for raw in _WHEEL_STRUCT.unpack(bytes(data)))


def encode_vehicle_state(state: VehicleState) -> bytes:
    flags = (FLAG_BRAKE if state.brake else 0) | (FLAG_RESET if state.reset else 0)
    return _STATE_STRUCT.pack(
        _saturate(round(state.speed_kmh / VEHICLE_SPEED_SCALE), 0, 0xFFFF),
        _saturate(round(state.steering_deg / STEERING_SCALE), -0x8000, 0x7FFF),
        flags,
    )


def decode_vehicle_state(data: bytes) -> VehicleState:
    speed, steering, flags = _STATE_STRUCT.unpack(bytes(data))
    return VehicleState(
        speed_kmh=speed * VEHICLE_SPEED_SCALE,
        steering_deg=steering * STEERING_SCALE,
        brake=bool(flags & FLAG_BRAKE),
        reset=bool(flags & FLAG_RESET),
    )


def candump_line(timestamp_s: float, channel: str, can_id: int, data: bytes) -> str:
    """One line of a `candump -l` log file, e.g. `(1700000000.020000) vcan0 100#A00F...`."""
    return f"({timestamp_s:.6f}) {channel} {can_id:03X}#{data.hex().upper()}"
