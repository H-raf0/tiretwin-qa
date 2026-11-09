#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace tiretwin {

/// Wheel order used everywhere in the project (arrays, CAN payload, CSV columns).
enum class Wheel : std::size_t { FrontLeft = 0, FrontRight = 1, RearLeft = 2, RearRight = 3 };

inline constexpr std::size_t kWheelCount = 4;

/// Bit of a wheel inside Output::warning_mask.
constexpr std::uint8_t wheelBit(Wheel wheel) noexcept {
  return static_cast<std::uint8_t>(1U << static_cast<unsigned>(wheel));
}

/// One input sample, as delivered every cycle (20 ms) by the CAN reception layer.
struct Sample {
  std::array<double, kWheelCount> wheel_speed_rad_s{};  ///< FL, FR, RL, RR
  double vehicle_speed_kmh = 0.0;
  double steering_angle_deg = 0.0;  ///< steering-wheel angle, positive = left turn
  bool brake_active = false;
  bool reset_request = false;  ///< driver pressed "tyres re-inflated / changed"
  double signal_age_s = 0.0;   ///< age of the oldest signal above (time since last CAN frame)
};

/// The numeric values are part of the interface (CSV output, Python reference).
enum class Status : int {
  Unavailable = 0,  ///< inputs lost or invalid: no diagnosis possible
  Calibrating = 1,  ///< learning the reference of the current tyre set
  Monitoring = 2,   ///< calibrated, no anomaly
  Warning = 3       ///< at least one wheel confirmed under-inflated
};

struct Output {
  Status status = Status::Calibrating;
  std::uint8_t warning_mask = 0;  ///< one bit per wheel, see wheelBit()
  bool usable = false;            ///< true when this sample fed the estimator
  /// Windowed, calibrated speed deviation of each wheel versus its axle mean, in percent.
  /// Positive = the wheel turns faster than expected = smaller rolling radius.
  std::array<double, kWheelCount> deviation_pct{};
};

}  // namespace tiretwin
