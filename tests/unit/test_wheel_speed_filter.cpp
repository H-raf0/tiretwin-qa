#include <cmath>
#include <limits>
#include <string>

#include <gtest/gtest.h>

#include "test_helpers.hpp"
#include "tiretwin/wheel_speed_filter.hpp"

namespace tiretwin {
namespace {

using testing::steps;
using testing::straightSample;

/// Feeds the same sample `count` times and returns the last result.
FilteredSample feed(WheelSpeedFilter& filter, const Sample& sample, int count) {
  FilteredSample last;
  for (int i = 0; i < count; ++i) {
    last = filter.update(sample);
  }
  return last;
}

TEST(WheelSpeedFilter, FirstSampleInitialisesTheFilterWithoutTransient) {
  WheelSpeedFilter filter;
  const Sample s = straightSample(90.0);
  const FilteredSample out = filter.update(s);
  EXPECT_TRUE(out.available);
  for (std::size_t i = 0; i < kWheelCount; ++i) {
    EXPECT_DOUBLE_EQ(out.wheel_speed_rad_s[i], s.wheel_speed_rad_s[i]);
  }
}

TEST(WheelSpeedFilter, LowPassFollowsAStepWithTheConfiguredTimeConstant) {
  Config config;
  WheelSpeedFilter filter(config);
  filter.update(straightSample(50.0));

  const Sample target = straightSample(100.0);
  const double start = straightSample(50.0).wheel_speed_rad_s[0];
  const double end = target.wheel_speed_rad_s[0];

  // After one time constant a first-order filter has covered ~63 % of the step
  // (the discrete filter at 50 Hz gives 60 %), after five it has converged.
  const FilteredSample after_tau = feed(filter, target, steps(config.lowpass_tau_s));
  const double progress = (after_tau.wheel_speed_rad_s[0] - start) / (end - start);
  EXPECT_NEAR(progress, 0.6, 0.05);

  const FilteredSample settled = feed(filter, target, steps(5 * config.lowpass_tau_s));
  EXPECT_NEAR(settled.wheel_speed_rad_s[0], end, 0.01 * (end - start));
}

TEST(WheelSpeedFilter, BecomesUsableOnlyAfterTheSettlingTime) {
  Config config;
  WheelSpeedFilter filter(config);
  const Sample s = straightSample(90.0);
  const int settle = steps(config.settle_time_s);

  for (int i = 0; i < settle; ++i) {
    EXPECT_FALSE(filter.update(s).usable) << "step " << i;
  }
  EXPECT_TRUE(filter.update(s).usable);
}

// --- Rejection of non-representative driving phases -------------------------
struct RejectionCase {
  std::string name;
  double speed_kmh;
  double steering_deg;
  bool brake;
};

class WheelSpeedFilterRejection : public ::testing::TestWithParam<RejectionCase> {};

TEST_P(WheelSpeedFilterRejection, SampleIsAvailableButNotUsableThenRecovers) {
  Config config;
  WheelSpeedFilter filter(config);
  const Sample good = straightSample(90.0);
  ASSERT_TRUE(feed(filter, good, steps(config.settle_time_s) + 1).usable);

  Sample bad = straightSample(GetParam().speed_kmh);
  bad.steering_angle_deg = GetParam().steering_deg;
  bad.brake_active = GetParam().brake;
  const FilteredSample rejected = filter.update(bad);
  EXPECT_TRUE(rejected.available);
  EXPECT_FALSE(rejected.usable);

  // Back to a clean situation: a full settling time is required again.
  EXPECT_FALSE(feed(filter, good, steps(config.settle_time_s)).usable);
  EXPECT_TRUE(filter.update(good).usable);
}

INSTANTIATE_TEST_SUITE_P(
    Conditions, WheelSpeedFilterRejection,
    ::testing::Values(RejectionCase{"LowSpeed", 19.0, 0.0, false},
                      RejectionCase{"Standstill", 0.0, 0.0, false},
                      RejectionCase{"TightLeftCorner", 90.0, 10.5, false},
                      RejectionCase{"TightRightCorner", 90.0, -10.5, false},
                      RejectionCase{"Braking", 90.0, 0.0, true}),
    [](const auto& p) { return p.param.name; });

TEST(WheelSpeedFilter, LimitValuesAreStillAccepted) {
  Config config;
  WheelSpeedFilter filter(config);
  Sample s = straightSample(config.min_speed_kmh);
  s.steering_angle_deg = config.max_steering_deg;
  EXPECT_TRUE(feed(filter, s, steps(config.settle_time_s) + 1).usable);
}

// --- Input monitoring -------------------------------------------------------
TEST(WheelSpeedFilter, StaleInputsAreReportedUnavailable) {
  Config config;
  WheelSpeedFilter filter(config);
  Sample s = straightSample(90.0);

  s.signal_age_s = config.signal_timeout_s;  // exactly at the limit: still valid
  EXPECT_TRUE(filter.update(s).available);

  s.signal_age_s = config.signal_timeout_s + 0.01;
  const FilteredSample out = filter.update(s);
  EXPECT_FALSE(out.available);
  EXPECT_FALSE(out.usable);
}

TEST(WheelSpeedFilter, NonFiniteInputsAreReportedUnavailable) {
  WheelSpeedFilter filter;
  Sample nan_wheel = straightSample(90.0);
  nan_wheel.wheel_speed_rad_s[2] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(filter.update(nan_wheel).available);

  Sample inf_speed = straightSample(90.0);
  inf_speed.vehicle_speed_kmh = std::numeric_limits<double>::infinity();
  EXPECT_FALSE(filter.update(inf_speed).available);
}

TEST(WheelSpeedFilter, RestartsFromFreshDataAfterAnOutage) {
  Config config;
  WheelSpeedFilter filter(config);
  feed(filter, straightSample(50.0), steps(config.settle_time_s) + 1);

  Sample stale = straightSample(50.0);
  stale.signal_age_s = 1.0;
  filter.update(stale);

  // The vehicle accelerated during the outage: no memory of the old speed must remain.
  const Sample fresh = straightSample(120.0);
  const FilteredSample out = filter.update(fresh);
  EXPECT_TRUE(out.available);
  EXPECT_FALSE(out.usable);
  EXPECT_DOUBLE_EQ(out.wheel_speed_rad_s[0], fresh.wheel_speed_rad_s[0]);
}

}  // namespace
}  // namespace tiretwin
