#pragma once

namespace tiretwin {

/// Calibration parameters. Defaults are the values validated by the test suite;
/// tools/py_reference.py must carry exactly the same numbers (REQ-005).
struct Config {
  double sample_period_s = 0.02;  ///< algorithm task period (50 Hz)

  // --- Input conditioning (WheelSpeedFilter) ---
  double signal_timeout_s = 0.2;    ///< older inputs => Status::Unavailable
  double lowpass_tau_s = 0.1;       ///< first-order low-pass on wheel speeds
  double min_speed_kmh = 20.0;      ///< below: wheel speed sensors too noisy
  double max_steering_deg = 10.0;   ///< above: tight corner, sample rejected
  double settle_time_s = 1.0;       ///< hold-off after a rejected phase

  // --- Vehicle geometry (kinematic compensation of gentle curves) ---
  double wheelbase_m = 2.7;
  double track_width_m = 1.55;
  double steering_ratio = 16.0;  ///< steering-wheel angle / road-wheel angle

  // --- Detection (UnderInflationDetector) ---
  double calibration_time_s = 30.0;  ///< usable driving time needed to learn the reference
  double window_s = 10.0;            ///< moving-average length (usable time)
  double threshold = 0.0010;         ///< relative deviation raising suspicion (0.10 %)
  double confirm_time_s = 10.0;      ///< suspicion must persist this long (usable time)
};

}  // namespace tiretwin
