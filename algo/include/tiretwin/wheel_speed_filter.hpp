#pragma once

#include <array>
#include <cstddef>

#include "tiretwin/config.hpp"
#include "tiretwin/types.hpp"

namespace tiretwin {

/// Result of the input conditioning stage.
struct FilteredSample {
  std::array<double, kWheelCount> wheel_speed_rad_s{};  ///< low-pass filtered
  bool available = false;  ///< inputs are fresh and finite
  bool usable = false;     ///< driving situation is representative (straight-ish, no braking)
};

/// Conditions the raw inputs before estimation:
///  - monitors input freshness and validity (CAN timeout, non-finite values);
///  - low-pass filters the four wheel speeds;
///  - rejects the phases where wheel speeds do not reflect the rolling radius
///    (low speed, tight corner, braking) plus a settling time after each of them.
class WheelSpeedFilter {
 public:
  explicit WheelSpeedFilter(const Config& config = Config{});

  FilteredSample update(const Sample& sample);

  /// Back to the power-on state.
  void reset();

 private:
  double alpha_;
  double signal_timeout_s_;
  double min_speed_kmh_;
  double max_steering_deg_;
  std::size_t settle_samples_;

  std::array<double, kWheelCount> filtered_{};
  bool initialised_ = false;
  std::size_t settle_remaining_;
};

}  // namespace tiretwin
