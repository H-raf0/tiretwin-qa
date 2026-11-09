// tiretwin_cli: runs the under-inflation detector on a replayed CAN trace.
//
//   tiretwin_cli <input.csv> <output.csv>
//
// The input CSV comes from tools/can_replay.py; the output CSV has the same
// format as tools/py_reference.py, so both can be diffed (back-to-back).

#include <cstdio>
#include <exception>
#include <vector>

#include "csv_io.hpp"
#include "tiretwin/underinflation_detector.hpp"

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s <input.csv> <output.csv>\n", argv[0]);
    return 2;
  }

  try {
    const auto samples = tiretwin::io::readInputCsv(argv[1]);

    tiretwin::UnderInflationDetector detector;
    std::vector<tiretwin::io::TimedOutput> outputs;
    outputs.reserve(samples.size());
    for (const auto& s : samples) {
      outputs.push_back({s.t_s, detector.step(s.sample)});
    }
    tiretwin::io::writeOutputCsv(argv[2], outputs);

    const unsigned mask = outputs.empty() ? 0U : outputs.back().output.warning_mask;
    std::printf("%zu samples processed, final warning mask: 0x%X (FL=1 FR=2 RL=4 RR=8)\n",
                outputs.size(), mask);
  } catch (const std::exception& error) {
    std::fprintf(stderr, "error: %s\n", error.what());
    return 1;
  }
  return 0;
}
