#pragma once

#include <array>
#include <ostream>

#include "tiretwin/types.hpp"

namespace tiretwin {

/// Readable Status values in GoogleTest failure messages.
inline void PrintTo(Status status, std::ostream* os) {
  static const char* const kNames[] = {"Unavailable", "Calibrating", "Monitoring", "Warning"};
  *os << kNames[static_cast<int>(status)];
}

}  // namespace tiretwin

namespace tiretwin::testing {

inline constexpr double kWheelRadiusM = 0.316;

/// A clean straight-line sample at `speed_kmh`. `speed_factor[i]` scales the speed of
/// wheel i: 1.003 means "turns 0.3 % faster", i.e. a rolling radius 0.3 % smaller.
inline Sample straightSample(double speed_kmh,
                             const std::array<double, kWheelCount>& speed_factor = {1.0, 1.0, 1.0,
                                                                                    1.0}) {
  Sample s;
  const double omega = speed_kmh / 3.6 / kWheelRadiusM;
  for (std::size_t i = 0; i < kWheelCount; ++i) {
    s.wheel_speed_rad_s[i] = omega * speed_factor[i];
  }
  s.vehicle_speed_kmh = speed_kmh;
  return s;
}

/// Number of 20 ms steps in `seconds`.
constexpr int steps(double seconds) { return static_cast<int>(seconds * 50.0 + 0.5); }

}  // namespace tiretwin::testing
