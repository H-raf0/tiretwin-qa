// Functional validation tests: one parameterised test per `verification` entry
// of requirements.yaml (see tools/gen_requirement_tests.py).
//
// Each test replays a complete CAN scenario through the detector, exactly as
// the vehicle would feed it, and checks the requirement on the output trace.
// The requirement id is recorded in the JUnit report so that
// tools/traceability.py can build the requirement <-> test <-> result matrix.

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <ostream>
#include <string>
#include <utility>
#include <vector>

#include <gtest/gtest.h>

#include "csv_io.hpp"
#include "tiretwin/underinflation_detector.hpp"

namespace {

using tiretwin::Config;
using tiretwin::Output;
using tiretwin::Status;
using tiretwin::UnderInflationDetector;
using tiretwin::Wheel;
using tiretwin::wheelBit;
using tiretwin::io::TimedSample;

constexpr double kPeriodS = 0.02;
constexpr double kEpsilonS = 1e-6;  // tolerance when comparing time stamps

// --- Test case descriptions (filled by the generated tables) ----------------
struct DetectionCase {
  std::string requirement, scenario;
  Wheel wheel;
  double loss_start_s, loss_full_s, within_s;
};
struct NoWarningCase {
  std::string requirement, scenario;
};
struct UnavailableCase {
  std::string requirement, scenario;
  double outage_start_s, outage_end_s, timeout_s;
};
struct BackToBackCase {
  std::string requirement, scenario;
  double tolerance;
};
struct StepTimeCase {
  std::string requirement, scenario;
  double max_ms;
};
struct KnownLimitationCase {
  std::string requirement, scenario;
};
struct ResetCase {
  std::string requirement, scenario;
  Wheel wheel;
  double reset_s;
};

#include "requirement_cases.inc"

/// Readable parameter in failure messages instead of a byte dump.
template <typename Case, typename = decltype(std::declval<Case>().requirement)>
std::ostream& operator<<(std::ostream& os, const Case& c) {
  return os << c.requirement << " on scenario " << c.scenario;
}

/// Fixed-format number for the properties shown in the traceability matrix.
std::string formatted(const char* format, double value) {
  char buffer[32];
  std::snprintf(buffer, sizeof(buffer), format, value);
  return buffer;
}

/// Test name suffix, e.g. "REQ_001_loss20_fl" (GoogleTest only accepts [A-Za-z0-9_]).
template <typename Case>
std::string caseName(const ::testing::TestParamInfo<Case>& p) {
  std::string name = p.param.requirement + "_" + p.param.scenario;
  std::replace(name.begin(), name.end(), '-', '_');
  return name;
}

// --- Scenario replay --------------------------------------------------------
std::string scenarioPath(const std::string& scenario, const std::string& extension) {
  const char* override_dir = std::getenv("TIRETWIN_SCENARIO_DIR");
  const std::string dir = override_dir != nullptr ? override_dir : TIRETWIN_SCENARIO_DIR;
  return dir + "/" + scenario + extension;
}

const std::vector<TimedSample>& inputsOf(const std::string& scenario) {
  static std::map<std::string, std::vector<TimedSample>> cache;
  auto it = cache.find(scenario);
  if (it == cache.end()) {
    it = cache.emplace(scenario, tiretwin::io::readInputCsv(scenarioPath(scenario, ".csv"))).first;
  }
  return it->second;
}

std::vector<Output> runDetector(const std::vector<TimedSample>& inputs,
                                const Config& config = Config{}) {
  UnderInflationDetector detector(config);
  std::vector<Output> outputs;
  outputs.reserve(inputs.size());
  for (const TimedSample& in : inputs) {
    outputs.push_back(detector.step(in.sample));
  }
  return outputs;
}

/// Common fixture: replays the scenario and tags the test with its requirement.
template <typename Case>
class ScenarioTest : public ::testing::TestWithParam<Case> {
 protected:
  void SetUp() override {
    const Case& c = this->GetParam();
    ::testing::Test::RecordProperty("requirement", c.requirement);
    ::testing::Test::RecordProperty("scenario", c.scenario);
    inputs_ = &inputsOf(c.scenario);
    ASSERT_FALSE(inputs_->empty());
    outputs_ = runDetector(*inputs_);
  }

  std::size_t size() const { return outputs_.size(); }
  double time(std::size_t i) const { return (*inputs_)[i].t_s; }
  const Output& out(std::size_t i) const { return outputs_[i]; }

  /// Time of the first sample with any warning, or a negative value if there is none.
  double firstWarningTime() const {
    for (std::size_t i = 0; i < size(); ++i) {
      if (out(i).warning_mask != 0) return time(i);
    }
    return -1.0;
  }

  const std::vector<TimedSample>* inputs_ = nullptr;
  std::vector<Output> outputs_;
};

// --- check: detection -------------------------------------------------------
using Detection = ScenarioTest<DetectionCase>;

TEST_P(Detection, FaultyWheelIsFlaggedWithinTheDeadline) {
  const DetectionCase& c = GetParam();
  const double detected_s = firstWarningTime();

  ASSERT_GE(detected_s, 0.0) << "the pressure loss was never detected";
  EXPECT_GE(detected_s, c.loss_start_s) << "warning raised before the pressure loss";
  EXPECT_LE(detected_s, c.loss_full_s + c.within_s) << "detection too late";
  RecordProperty("detection_delay_s", formatted("%.2f", detected_s - c.loss_full_s));

  for (std::size_t i = 0; i < size(); ++i) {
    if (out(i).warning_mask == 0) continue;
    ASSERT_EQ(out(i).warning_mask, wheelBit(c.wheel)) << "wrong wheel flagged at t=" << time(i);
    ASSERT_EQ(out(i).status, Status::Warning) << "at t=" << time(i);
  }
}

INSTANTIATE_TEST_SUITE_P(Requirements, Detection, ::testing::ValuesIn(kDetectionCases),
                         caseName<DetectionCase>);

// --- check: no_warning ------------------------------------------------------
using NoWarning = ScenarioTest<NoWarningCase>;

TEST_P(NoWarning, NoWarningOverTheWholeScenario) {
  std::size_t usable = 0;
  for (std::size_t i = 0; i < size(); ++i) {
    ASSERT_EQ(out(i).warning_mask, 0) << "false warning at t=" << time(i);
    ASSERT_NE(out(i).status, Status::Warning) << "at t=" << time(i);
    usable += out(i).usable ? 1U : 0U;
  }
  // Guard against a vacuous pass: the detector must really have been monitoring.
  EXPECT_EQ(out(size() - 1).status, Status::Monitoring);
  EXPECT_GT(usable, size() / 4) << "the scenario hardly exercised the estimator";
  RecordProperty("usable_ratio",
                 formatted("%.2f", static_cast<double>(usable) / static_cast<double>(size())));
}

INSTANTIATE_TEST_SUITE_P(Requirements, NoWarning, ::testing::ValuesIn(kNoWarningCases),
                         caseName<NoWarningCase>);

// --- check: unavailable -----------------------------------------------------
using Unavailable = ScenarioTest<UnavailableCase>;

TEST_P(Unavailable, OutageIsSignalledAndSurvived) {
  const UnavailableCase& c = GetParam();
  // The outage must be signalled once the last data is older than the timeout,
  // and not before: the last sample that may still be valid is one period earlier.
  const double must_be_unavailable_from = c.outage_start_s + c.timeout_s;
  const double may_be_available_until = must_be_unavailable_from - 2 * kPeriodS;

  for (std::size_t i = 0; i < size(); ++i) {
    const double t = time(i);
    ASSERT_EQ(out(i).warning_mask, 0) << "false warning at t=" << t;

    if (t <= may_be_available_until + kEpsilonS || t >= c.outage_end_s + kPeriodS - kEpsilonS) {
      ASSERT_NE(out(i).status, Status::Unavailable) << "unexpectedly unavailable at t=" << t;
    } else if (t >= must_be_unavailable_from - kEpsilonS && t < c.outage_end_s - kEpsilonS) {
      ASSERT_EQ(out(i).status, Status::Unavailable) << "outage not signalled at t=" << t;
      ASSERT_FALSE(out(i).usable) << "stale data used at t=" << t;
    }
  }
  EXPECT_EQ(out(size() - 1).status, Status::Monitoring) << "monitoring did not resume";
}

INSTANTIATE_TEST_SUITE_P(Requirements, Unavailable, ::testing::ValuesIn(kUnavailableCases),
                         caseName<UnavailableCase>);

// --- check: back_to_back ----------------------------------------------------
using BackToBack = ScenarioTest<BackToBackCase>;

TEST_P(BackToBack, CppMatchesThePythonReference) {
  const BackToBackCase& c = GetParam();
  const auto reference = tiretwin::io::readOutputCsv(scenarioPath(c.scenario, ".ref.csv"));
  ASSERT_EQ(reference.size(), size());

  double max_error = 0.0;
  for (std::size_t i = 0; i < size(); ++i) {
    const Output& ref = reference[i].output;
    // ASSERT (not EXPECT): report the first divergence, not 90 000 lines of them.
    ASSERT_EQ(static_cast<int>(out(i).status), static_cast<int>(ref.status)) << "at t=" << time(i);
    ASSERT_EQ(out(i).warning_mask, ref.warning_mask) << "at t=" << time(i);
    ASSERT_EQ(out(i).usable, ref.usable) << "at t=" << time(i);
    for (std::size_t w = 0; w < tiretwin::kWheelCount; ++w) {
      const double error = std::fabs(out(i).deviation_pct[w] - ref.deviation_pct[w]);
      ASSERT_LE(error, c.tolerance) << "wheel " << w << " at t=" << time(i);
      max_error = std::max(max_error, error);
    }
  }
  RecordProperty("max_abs_error_pct", formatted("%.1e", max_error));
}

INSTANTIATE_TEST_SUITE_P(Requirements, BackToBack, ::testing::ValuesIn(kBackToBackCases),
                         caseName<BackToBackCase>);

// --- check: step_time -------------------------------------------------------
using StepTime = ScenarioTest<StepTimeCase>;

TEST_P(StepTime, StepFitsInTheComputationBudget) {
  using Clock = std::chrono::steady_clock;
  UnderInflationDetector detector;
  std::vector<double> durations_ms;
  durations_ms.reserve(inputs_->size());

  for (const TimedSample& in : *inputs_) {
    const auto start = Clock::now();
    const Output result = detector.step(in.sample);
    const auto stop = Clock::now();
    durations_ms.push_back(std::chrono::duration<double, std::milli>(stop - start).count());
    ASSERT_LE(static_cast<int>(result.status), 3);  // keeps the call observable
  }

  double total_ms = 0.0;
  for (const double d : durations_ms) total_ms += d;
  const double mean_ms = total_ms / static_cast<double>(durations_ms.size());

  // The 99th percentile is used instead of the maximum: on a desktop OS a single
  // step can be stretched by a context switch that has nothing to do with the code.
  std::sort(durations_ms.begin(), durations_ms.end());
  const double p99_ms = durations_ms[durations_ms.size() * 99 / 100];

  EXPECT_LT(mean_ms, GetParam().max_ms);
  EXPECT_LT(p99_ms, GetParam().max_ms);
  RecordProperty("mean_step_us", formatted("%.3f", mean_ms * 1000.0));
  RecordProperty("p99_step_us", formatted("%.3f", p99_ms * 1000.0));
}

INSTANTIATE_TEST_SUITE_P(Requirements, StepTime, ::testing::ValuesIn(kStepTimeCases),
                         caseName<StepTimeCase>);

// --- check: known_limitation ------------------------------------------------
using KnownLimitation = ScenarioTest<KnownLimitationCase>;

// "Expected failure": the requirement is written as the desired behaviour, the
// algorithm is known not to meet it. The test is reported as skipped (shown as
// a known limitation in the traceability matrix) while the behaviour is missing,
// and FAILS if it starts passing, so that the requirement status gets updated.
TEST_P(KnownLimitation, DesiredBehaviourIsNotMetYet) {
  if (firstWarningTime() >= 0.0) {
    FAIL() << "unexpected pass: the pressure loss is now detected. "
              "Change the requirement status to 'implemented' in requirements.yaml.";
  }
  RecordProperty("known_limitation", "true");
  GTEST_SKIP() << "Known limitation: the pressure loss is not detected (expected failure).";
}

INSTANTIATE_TEST_SUITE_P(Requirements, KnownLimitation,
                         ::testing::ValuesIn(kKnownLimitationCases),
                         caseName<KnownLimitationCase>);

// --- check: reset -----------------------------------------------------------
using Reset = ScenarioTest<ResetCase>;

TEST_P(Reset, ResetClearsTheWarningAndRelearnsTheReference) {
  const ResetCase& c = GetParam();
  bool warned_before_reset = false;
  bool recalibrated = false;

  for (std::size_t i = 0; i < size(); ++i) {
    const double t = time(i);
    if (t < c.reset_s - kEpsilonS) {
      warned_before_reset = out(i).warning_mask == wheelBit(c.wheel);
    } else if (t >= c.reset_s + 2 * kPeriodS) {
      ASSERT_EQ(out(i).warning_mask, 0) << "warning after the reset at t=" << t;
      if (!recalibrated) {
        if (out(i).status == Status::Monitoring) {
          recalibrated = true;
        } else {
          ASSERT_EQ(out(i).status, Status::Calibrating) << "at t=" << t;
        }
      } else {
        ASSERT_EQ(out(i).status, Status::Monitoring) << "at t=" << t;
      }
    }
  }
  EXPECT_TRUE(warned_before_reset) << "precondition: a warning must be active before the reset";
  EXPECT_TRUE(recalibrated) << "the new calibration never completed";
}

INSTANTIATE_TEST_SUITE_P(Requirements, Reset, ::testing::ValuesIn(kResetCases),
                         caseName<ResetCase>);

// --- Sensitivity checks ("tests of the tests") ------------------------------
// A scenario that passes proves nothing if it could not have failed. These
// tests remove one protection of the algorithm and check that the scenario
// then does produce the fault it is supposed to guard against.

TEST(Sensitivity, CornerScenarioTriggersAFalseWarningWithoutSteeringRejection) {
  Config config;
  config.max_steering_deg = 1.0e9;  // never reject a corner
  const auto outputs = runDetector(inputsOf("corner_brake"), config);
  EXPECT_NE(outputs.back().warning_mask, 0);
}

TEST(Sensitivity, TyreChangeScenarioTriggersAFalseWarningWithoutReset) {
  std::vector<TimedSample> inputs = inputsOf("tyre_change_reset");
  for (TimedSample& in : inputs) {
    in.sample.reset_request = false;  // the driver forgot to press the button
  }
  const auto outputs = runDetector(inputs);
  // The stale reference turns the new (larger) front-left tyre into an
  // apparent deflation of its neighbour.
  EXPECT_NE(outputs.back().warning_mask & wheelBit(Wheel::FrontRight), 0);
}

}  // namespace
