#include "tiretwin/wheel_speed_filter.hpp"

#include <cmath>

namespace tiretwin {

namespace {

/// Wheel speeds below this are treated as "not rotating" (guards the divisions downstream).
constexpr double kMinWheelSpeedRadS = 1.0;

std::size_t toSamples(double duration_s, double period_s) {
  const double n = std::round(duration_s / period_s);
  return n < 1.0 ? std::size_t{1} : static_cast<std::size_t>(n);
}

bool allFinite(const Sample& s) {
  for (const double w : s.wheel_speed_rad_s) {
    if (!std::isfinite(w)) return false;
  }
  return std::isfinite(s.vehicle_speed_kmh) && std::isfinite(s.steering_angle_deg) &&
         std::isfinite(s.signal_age_s);
}

}  // namespace

WheelSpeedFilter::WheelSpeedFilter(const Config& config)
    : alpha_(config.sample_period_s / (config.lowpass_tau_s + config.sample_period_s)),
      signal_timeout_s_(config.signal_timeout_s),
      min_speed_kmh_(config.min_speed_kmh),
      max_steering_deg_(config.max_steering_deg),
      settle_samples_(toSamples(config.settle_time_s, config.sample_period_s)),
      settle_remaining_(settle_samples_) {}

FilteredSample WheelSpeedFilter::update(const Sample& sample) {
  FilteredSample out;

  out.available = allFinite(sample) && sample.signal_age_s <= signal_timeout_s_;
  if (!out.available) {
    // Stale or corrupt inputs: drop the filter memory so that it restarts from
    // fresh data, and require a full settling time once the signals are back.
    initialised_ = false;
    settle_remaining_ = settle_samples_;
    return out;
  }

  if (!initialised_) {
    filtered_ = sample.wheel_speed_rad_s;
    initialised_ = true;
  } else {
    for (std::size_t i = 0; i < kWheelCount; ++i) {
      filtered_[i] += alpha_ * (sample.wheel_speed_rad_s[i] - filtered_[i]);
    }
  }
  out.wheel_speed_rad_s = filtered_;

  bool representative = sample.vehicle_speed_kmh >= min_speed_kmh_ &&
                        std::fabs(sample.steering_angle_deg) <= max_steering_deg_ &&
                        !sample.brake_active;
  for (const double w : filtered_) {
    representative = representative && (w > kMinWheelSpeedRadS);
  }

  if (!representative) {
    settle_remaining_ = settle_samples_;
  } else if (settle_remaining_ > 0) {
    --settle_remaining_;
  } else {
    out.usable = true;
  }
  return out;
}

}  // namespace tiretwin
