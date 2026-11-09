#include "tiretwin/underinflation_detector.hpp"

#include <algorithm>
#include <cmath>

namespace tiretwin {

namespace {

constexpr double kDegToRad = 3.14159265358979323846 / 180.0;

std::size_t toSamples(double duration_s, double period_s) {
  const double n = std::round(duration_s / period_s);
  return n < 1.0 ? std::size_t{1} : static_cast<std::size_t>(n);
}

}  // namespace

UnderInflationDetector::UnderInflationDetector(const Config& config)
    : config_(config),
      filter_(config),
      calibration_samples_(toSamples(config.calibration_time_s, config.sample_period_s)),
      window_samples_(toSamples(config.window_s, config.sample_period_s)),
      confirm_samples_(toSamples(config.confirm_time_s, config.sample_period_s)) {
  for (Axle& axle : axles_) {
    axle.window.assign(window_samples_, 0.0);
  }
}

void UnderInflationDetector::reset() {
  for (Axle& axle : axles_) {
    axle.calibration_sum = 0.0;
    axle.offset = 0.0;
    std::fill(axle.window.begin(), axle.window.end(), 0.0);
    axle.head = 0;
    axle.count = 0;
    axle.window_sum = 0.0;
    axle.average = 0.0;
    axle.left_suspect = 0;
    axle.right_suspect = 0;
  }
  calibration_count_ = 0;
  calibrated_ = false;
  warning_mask_ = 0;
}

Output UnderInflationDetector::step(const Sample& sample) {
  const FilteredSample filtered = filter_.update(sample);

  if (!filtered.available) {
    // Nothing is learnt and nothing is forgotten while the inputs are lost.
    return makeOutput(Status::Unavailable, false);
  }

  if (sample.reset_request) {
    reset();
  }

  if (filtered.usable) {
    const auto& w = filtered.wheel_speed_rad_s;

    // In a left turn (positive steering) the left wheels are on the inside and
    // turn slower: (wl - wr) / (wl + wr) = -(track / 2) * curvature.
    // Adding the term back removes the kinematic effect of gentle curves.
    const double road_wheel_angle = sample.steering_angle_deg * kDegToRad / config_.steering_ratio;
    const double curvature = std::tan(road_wheel_angle) / config_.wheelbase_m;
    const double correction = 0.5 * config_.track_width_m * curvature;

    const double front = (w[0] - w[1]) / (w[0] + w[1]) + correction;
    const double rear = (w[2] - w[3]) / (w[2] + w[3]) + correction;

    if (!calibrated_) {
      axles_[0].calibration_sum += front;
      axles_[1].calibration_sum += rear;
      ++calibration_count_;
      if (calibration_count_ >= calibration_samples_) {
        const double n = static_cast<double>(calibration_count_);
        axles_[0].offset = axles_[0].calibration_sum / n;
        axles_[1].offset = axles_[1].calibration_sum / n;
        calibrated_ = true;
      }
    } else {
      updateAxle(axles_[0], front, Wheel::FrontLeft, Wheel::FrontRight);
      updateAxle(axles_[1], rear, Wheel::RearLeft, Wheel::RearRight);
    }
  }

  Status status = Status::Calibrating;
  if (warning_mask_ != 0) {
    status = Status::Warning;
  } else if (calibrated_) {
    status = Status::Monitoring;
  }
  return makeOutput(status, filtered.usable);
}

void UnderInflationDetector::updateAxle(Axle& axle, double deviation, Wheel left, Wheel right) {
  const double calibrated = deviation - axle.offset;

  // Sliding sum over a circular buffer: O(1) per step whatever the window length.
  axle.window_sum += calibrated - axle.window[axle.head];
  axle.window[axle.head] = calibrated;
  axle.head = (axle.head + 1) % window_samples_;
  if (axle.count < window_samples_) {
    ++axle.count;
  }
  if (axle.count < window_samples_) {
    return;  // not enough data yet to decide anything
  }

  axle.average = axle.window_sum / static_cast<double>(window_samples_);

  if (axle.average > config_.threshold) {
    ++axle.left_suspect;
    axle.right_suspect = 0;
  } else if (axle.average < -config_.threshold) {
    ++axle.right_suspect;
    axle.left_suspect = 0;
  } else {
    axle.left_suspect = 0;
    axle.right_suspect = 0;
  }

  if (axle.left_suspect >= confirm_samples_) {
    warning_mask_ = static_cast<std::uint8_t>(warning_mask_ | wheelBit(left));
  }
  if (axle.right_suspect >= confirm_samples_) {
    warning_mask_ = static_cast<std::uint8_t>(warning_mask_ | wheelBit(right));
  }
}

Output UnderInflationDetector::makeOutput(Status status, bool usable) const {
  Output out;
  out.status = status;
  out.warning_mask = warning_mask_;
  out.usable = usable;
  out.deviation_pct = {100.0 * axles_[0].average, -100.0 * axles_[0].average,
                       100.0 * axles_[1].average, -100.0 * axles_[1].average};
  return out;
}

}  // namespace tiretwin
