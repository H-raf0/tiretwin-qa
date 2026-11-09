#include <array>
#include <cmath>
#include <string>

#include <gtest/gtest.h>

#include "test_helpers.hpp"
#include "tiretwin/underinflation_detector.hpp"

namespace tiretwin {
namespace {

using testing::steps;
using testing::straightSample;

using Factors = std::array<double, kWheelCount>;

// A 20 % pressure loss shrinks the rolling radius by about 0.3 %.
constexpr double kDeflated = 1.003;

/// Feeds the same sample for `seconds` and returns the last output.
Output drive(UnderInflationDetector& detector, const Sample& sample, double seconds) {
  Output last;
  for (int i = 0; i < steps(seconds); ++i) {
    last = detector.step(sample);
  }
  return last;
}

/// Drives long enough on a clean straight to finish the calibration.
Output calibrate(UnderInflationDetector& detector, const Factors& factors = {1.0, 1.0, 1.0, 1.0}) {
  const Config& c = detector.config();
  return drive(detector, straightSample(90.0, factors), c.settle_time_s + c.calibration_time_s + 0.1);
}

Factors factorsWith(Wheel wheel, double factor) {
  Factors f = {1.0, 1.0, 1.0, 1.0};
  f[static_cast<std::size_t>(wheel)] = factor;
  return f;
}

TEST(UnderInflationDetector, StartsInCalibrationThenMonitors) {
  UnderInflationDetector detector;
  const Config& c = detector.config();
  const Sample s = straightSample(90.0);

  const Output during = drive(detector, s, c.settle_time_s + c.calibration_time_s - 0.1);
  EXPECT_EQ(during.status, Status::Calibrating);

  const Output after = drive(detector, s, 0.2);
  EXPECT_EQ(after.status, Status::Monitoring);
  EXPECT_EQ(after.warning_mask, 0);
}

TEST(UnderInflationDetector, CalibrationOnlyCountsUsableDrivingTime) {
  UnderInflationDetector detector;
  const Config& c = detector.config();

  // Ten minutes in town below the minimum speed teach nothing.
  EXPECT_EQ(drive(detector, straightSample(15.0), 600.0).status, Status::Calibrating);
  EXPECT_EQ(drive(detector, straightSample(90.0), c.settle_time_s + c.calibration_time_s + 0.1).status,
            Status::Monitoring);
}

TEST(UnderInflationDetector, IdenticalWheelsNeverRaiseAWarning) {
  UnderInflationDetector detector;
  calibrate(detector);
  const Output out = drive(detector, straightSample(110.0), 600.0);
  EXPECT_EQ(out.status, Status::Monitoring);
  EXPECT_EQ(out.warning_mask, 0);
  for (const double d : out.deviation_pct) {
    EXPECT_NEAR(d, 0.0, 1e-9);
  }
}

// --- Detection and isolation of the faulty wheel ----------------------------
class DetectorPerWheel : public ::testing::TestWithParam<Wheel> {};

TEST_P(DetectorPerWheel, FlagsOnlyTheWheelThatTurnsFaster) {
  UnderInflationDetector detector;
  calibrate(detector);

  const Wheel wheel = GetParam();
  const Output out = drive(detector, straightSample(90.0, factorsWith(wheel, kDeflated)), 60.0);

  EXPECT_EQ(out.status, Status::Warning);
  EXPECT_EQ(out.warning_mask, wheelBit(wheel));
  // 0.3 % faster than its neighbour = 0.15 % above the axle mean.
  EXPECT_NEAR(out.deviation_pct[static_cast<std::size_t>(wheel)], 0.15, 0.005);
}

std::string wheelName(const ::testing::TestParamInfo<Wheel>& p) {
  static const char* const kNames[] = {"FrontLeft", "FrontRight", "RearLeft", "RearRight"};
  return kNames[static_cast<std::size_t>(p.param)];
}

INSTANTIATE_TEST_SUITE_P(AllWheels, DetectorPerWheel,
                         ::testing::Values(Wheel::FrontLeft, Wheel::FrontRight, Wheel::RearLeft,
                                           Wheel::RearRight),
                         wheelName);

TEST(UnderInflationDetector, WarningNeedsTheFullConfirmationTime) {
  UnderInflationDetector detector;
  const Config& c = detector.config();
  calibrate(detector);
  const Sample deflated = straightSample(90.0, factorsWith(Wheel::RearLeft, kDeflated));

  // The window must first fill up (window_s), then the deviation must persist (confirm_time_s).
  const Output early = drive(detector, deflated, c.window_s + c.confirm_time_s - 0.5);
  EXPECT_EQ(early.warning_mask, 0);
  EXPECT_EQ(early.status, Status::Monitoring);

  const Output confirmed = drive(detector, deflated, 1.0);
  EXPECT_EQ(confirmed.warning_mask, wheelBit(Wheel::RearLeft));
}

TEST(UnderInflationDetector, SmallDeviationStaysBelowTheThreshold) {
  UnderInflationDetector detector;
  calibrate(detector);
  // 10 % pressure loss ~ 0.15 % radius ~ 0.075 % deviation: below the 0.10 % threshold.
  const Output out = drive(detector, straightSample(90.0, factorsWith(Wheel::FrontLeft, 1.0015)), 300.0);
  EXPECT_EQ(out.warning_mask, 0);
  EXPECT_NEAR(out.deviation_pct[0], 0.075, 0.005);
}

TEST(UnderInflationDetector, CalibrationAbsorbsTheNaturalDifferencesBetweenTyres) {
  // A worn tyre next to a new one: 0.4 % radius difference, larger than a 20 % deflation.
  const Factors worn = {1.004, 1.0, 0.999, 1.0};
  UnderInflationDetector detector;
  calibrate(detector, worn);

  const Output out = drive(detector, straightSample(90.0, worn), 300.0);
  EXPECT_EQ(out.status, Status::Monitoring);
  EXPECT_NEAR(out.deviation_pct[0], 0.0, 1e-9);

  // A real loss on top of the learnt offset is still detected, on the right wheel.
  Factors worn_and_deflated = worn;
  worn_and_deflated[static_cast<std::size_t>(Wheel::FrontRight)] *= kDeflated;
  EXPECT_EQ(drive(detector, straightSample(90.0, worn_and_deflated), 60.0).warning_mask,
            wheelBit(Wheel::FrontRight));
}

TEST(UnderInflationDetector, RejectedPhasesNeitherFeedNorResetTheConfirmation) {
  UnderInflationDetector detector;
  calibrate(detector);
  const Sample deflated = straightSample(90.0, factorsWith(Wheel::FrontLeft, kDeflated));
  Sample braking = deflated;
  braking.brake_active = true;

  drive(detector, deflated, 15.0);  // window full, confirmation half-way
  const Output held = drive(detector, braking, 60.0);
  EXPECT_FALSE(held.usable);
  EXPECT_EQ(held.warning_mask, 0) << "a warning must not be raised while samples are rejected";

  // 1 s settling + the 5 remaining seconds of confirmation.
  EXPECT_EQ(drive(detector, deflated, 6.5).warning_mask, wheelBit(Wheel::FrontLeft));
}

TEST(UnderInflationDetector, KinematicEffectOfAGentleCurveIsCompensated) {
  UnderInflationDetector detector;
  const Config& c = detector.config();
  calibrate(detector);

  // Ideal left curve with 5 deg at the steering wheel: inner (left) wheels are slower.
  const double steering_deg = 5.0;
  const double curvature =
      std::tan(steering_deg * 3.14159265358979323846 / 180.0 / c.steering_ratio) / c.wheelbase_m;
  const double half = 0.5 * c.track_width_m * curvature;  // ~0.16 %: would trigger a warning
  ASSERT_GT(half, 1.5 * c.threshold);

  Sample curve = straightSample(90.0, {1.0 - half, 1.0 + half, 1.0 - half, 1.0 + half});
  curve.steering_angle_deg = steering_deg;
  const Output out = drive(detector, curve, 120.0);
  EXPECT_TRUE(out.usable);
  EXPECT_EQ(out.warning_mask, 0);
  EXPECT_NEAR(out.deviation_pct[1], 0.0, 1e-6);
}

// --- Warning life cycle -----------------------------------------------------
TEST(UnderInflationDetector, WarningIsLatchedUntilReset) {
  UnderInflationDetector detector;
  calibrate(detector);
  drive(detector, straightSample(90.0, factorsWith(Wheel::RearRight, kDeflated)), 60.0);

  // The deviation disappears (tyre re-inflated) but nobody confirmed it: keep warning.
  const Output latched = drive(detector, straightSample(90.0), 300.0);
  EXPECT_EQ(latched.status, Status::Warning);
  EXPECT_EQ(latched.warning_mask, wheelBit(Wheel::RearRight));
}

TEST(UnderInflationDetector, ResetRequestClearsTheWarningAndRestartsCalibration) {
  UnderInflationDetector detector;
  calibrate(detector);
  drive(detector, straightSample(90.0, factorsWith(Wheel::RearRight, kDeflated)), 60.0);

  Sample reset = straightSample(90.0);
  reset.reset_request = true;
  const Output out = detector.step(reset);
  EXPECT_EQ(out.status, Status::Calibrating);
  EXPECT_EQ(out.warning_mask, 0);
  for (const double d : out.deviation_pct) {
    EXPECT_EQ(d, 0.0);
  }

  // A new calibration is needed and then succeeds.
  EXPECT_EQ(drive(detector, straightSample(90.0), 5.0).status, Status::Calibrating);
  EXPECT_EQ(calibrate(detector).status, Status::Monitoring);
}

// Regression test for a defect found by the back-to-back tests (REQ-005): reset()
// cleared the window sum but not the window content, so the deviations measured
// before the reset leaked into the averages computed after it.
TEST(UnderInflationDetector, NothingMeasuredBeforeAResetLeaksIntoTheNewWindow) {
  UnderInflationDetector detector;
  calibrate(detector);
  drive(detector, straightSample(90.0, factorsWith(Wheel::FrontLeft, kDeflated)), 60.0);

  detector.reset();
  calibrate(detector);
  const Output out = drive(detector, straightSample(90.0), 60.0);
  EXPECT_EQ(out.status, Status::Monitoring);
  EXPECT_EQ(out.warning_mask, 0);
  for (const double d : out.deviation_pct) {
    // Not exactly 0: the tyre is "repaired" in one step here, and the tail of the
    // low-pass filter biases the new reference by 0.0005 %. The defect gave 0.15 %.
    EXPECT_NEAR(d, 0.0, 0.002);
  }
}

// --- Robustness -------------------------------------------------------------
TEST(UnderInflationDetector, InputOutageIsReportedAndDoesNotEraseTheDiagnosis) {
  UnderInflationDetector detector;
  calibrate(detector);
  drive(detector, straightSample(90.0, factorsWith(Wheel::FrontLeft, kDeflated)), 60.0);

  Sample stale = straightSample(90.0);
  stale.signal_age_s = 5.0;
  const Output lost = drive(detector, stale, 10.0);
  EXPECT_EQ(lost.status, Status::Unavailable);
  EXPECT_FALSE(lost.usable);

  // Signals are back: the latched warning and the calibration are still there.
  const Output back = detector.step(straightSample(90.0));
  EXPECT_EQ(back.status, Status::Warning);
  EXPECT_EQ(back.warning_mask, wheelBit(Wheel::FrontLeft));
}

TEST(UnderInflationDetector, ResetRequestCarriedByStaleDataIsIgnored) {
  UnderInflationDetector detector;
  calibrate(detector);

  Sample stale = straightSample(90.0);
  stale.signal_age_s = 5.0;
  stale.reset_request = true;  // frozen value of a dead bus: must not be trusted
  detector.step(stale);
  EXPECT_EQ(detector.step(straightSample(90.0)).status, Status::Monitoring);
}

TEST(UnderInflationDetector, StandstillAndZeroWheelSpeedsAreHarmless) {
  UnderInflationDetector detector;
  calibrate(detector);

  Sample stopped;  // everything at zero
  const Output out = drive(detector, stopped, 60.0);
  EXPECT_EQ(out.status, Status::Monitoring);
  for (const double d : out.deviation_pct) {
    EXPECT_TRUE(std::isfinite(d));
  }

  // One wheel speed sensor stuck at zero while driving: rejected, not divided by.
  Sample stuck = straightSample(90.0);
  stuck.wheel_speed_rad_s[1] = 0.0;
  const Output rejected = drive(detector, stuck, 60.0);
  EXPECT_FALSE(rejected.usable);
  EXPECT_EQ(rejected.warning_mask, 0);
}

}  // namespace
}  // namespace tiretwin
