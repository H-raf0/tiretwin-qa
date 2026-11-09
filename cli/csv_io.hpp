#pragma once

#include <string>
#include <vector>

#include "tiretwin/types.hpp"

namespace tiretwin::io {

/// One row of an input CSV produced by tools/can_replay.py.
struct TimedSample {
  double t_s = 0.0;
  Sample sample;
};

/// One row of an output CSV (written by tiretwin_cli and by tools/py_reference.py).
struct TimedOutput {
  double t_s = 0.0;
  Output output;
};

/// Columns: t_s,w_fl,w_fr,w_rl,w_rr,v_kmh,steer_deg,brake,reset,age_s
/// Throws std::runtime_error on a missing file or a malformed row.
std::vector<TimedSample> readInputCsv(const std::string& path);

/// Columns: t_s,status,warning_mask,usable,dev_fl_pct,dev_fr_pct,dev_rl_pct,dev_rr_pct
std::vector<TimedOutput> readOutputCsv(const std::string& path);

void writeOutputCsv(const std::string& path, const std::vector<TimedOutput>& rows);

}  // namespace tiretwin::io
