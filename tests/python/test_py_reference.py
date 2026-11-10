"""Sanity tests of the Python reference on its own.

The back-to-back tests prove that C++ and Python agree; these few tests check
that what they agree on is the intended behaviour, independently of the C++.
"""

import py_reference as ref

OMEGA_90_KMH = 90.0 / 3.6 / 0.316


def _drive(detector, seconds, factors=(1.0, 1.0, 1.0, 1.0), **kwargs):
    sample = ref.Sample(
        wheel_speed_rad_s=tuple(OMEGA_90_KMH * f for f in factors),
        vehicle_speed_kmh=90.0,
        steering_angle_deg=0.0,
        **kwargs,
    )
    out = None
    for _ in range(round(seconds * 50)):
        out = detector.step(sample)
    return out


def test_calibrates_then_monitors_without_warning():
    detector = ref.UnderInflationDetector()
    assert _drive(detector, 30.0).status == ref.CALIBRATING
    out = _drive(detector, 60.0)
    assert (out.status, out.warning_mask) == (ref.MONITORING, 0)


def test_flags_the_wheel_that_turns_faster():
    detector = ref.UnderInflationDetector()
    _drive(detector, 32.0)
    out = _drive(detector, 30.0, factors=(1.0, 1.0, 1.0, 1.003))
    assert (out.status, out.warning_mask) == (ref.WARNING, 1 << ref.RR)
    assert abs(out.deviation_pct[ref.RR] - 0.15) < 0.005


def test_stale_inputs_give_unavailable_and_reset_restarts_calibration():
    detector = ref.UnderInflationDetector()
    _drive(detector, 32.0)
    assert _drive(detector, 1.0, signal_age_s=0.5).status == ref.UNAVAILABLE
    assert _drive(detector, 0.02).status == ref.MONITORING
    assert _drive(detector, 0.02, reset_request=True).status == ref.CALIBRATING
