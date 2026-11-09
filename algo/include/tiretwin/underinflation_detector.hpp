#pragma once

#include <array>
#include <cstddef>
#include <vector>

#include "tiretwin/config.hpp"
#include "tiretwin/types.hpp"
#include "tiretwin/wheel_speed_filter.hpp"

namespace tiretwin {

/// Indirect tyre pressure monitoring (iTPMS, "radius analysis").
///
/// An under-inflated tyre has a smaller rolling radius, so for the same vehicle
/// speed it spins faster. For each axle the detector tracks the relative speed
/// difference between the left and the right wheel:
///
///     d = (w_left - w_right) / (w_left + w_right)
///
/// corrected for the kinematic effect of gentle curves, calibrated against the
/// value learnt for the current tyre set, then averaged on a sliding window.
/// A wheel is flagged when the averaged deviation stays beyond the threshold
/// for the confirmation time. The warning is latched until reset().
///
/// Memory is allocated once in the constructor; step() never allocates.
class UnderInflationDetector {
 public:
  explicit UnderInflationDetector(const Config& config = Config{});

  /// Process one sample. Must be called at Config::sample_period_s.
  Output step(const Sample& sample);

  /// Forget the learnt reference and any warning (tyre change / re-inflation).
  void reset();

  const Config& config() const noexcept { return config_; }

 private:
  /// State of one axle (index 0 = front, 1 = rear).
  struct Axle {
    double calibration_sum = 0.0;
    double offset = 0.0;
    std::vector<double> window;  ///< circular buffer of calibrated deviations
    std::size_t head = 0;
    std::size_t count = 0;
    double window_sum = 0.0;
    double average = 0.0;  ///< valid once the window is full, 0 before
    std::size_t left_suspect = 0;
    std::size_t right_suspect = 0;
  };

  void updateAxle(Axle& axle, double deviation, Wheel left, Wheel right);
  Output makeOutput(Status status, bool usable) const;

  Config config_;
  WheelSpeedFilter filter_;
  std::size_t calibration_samples_;
  std::size_t window_samples_;
  std::size_t confirm_samples_;

  std::array<Axle, 2> axles_;
  std::size_t calibration_count_ = 0;
  bool calibrated_ = false;
  std::uint8_t warning_mask_ = 0;
};

}  // namespace tiretwin
