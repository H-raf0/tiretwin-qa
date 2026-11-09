#include "csv_io.hpp"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <stdexcept>

namespace tiretwin::io {

namespace {

constexpr const char* kInputHeader = "t_s,w_fl,w_fr,w_rl,w_rr,v_kmh,steer_deg,brake,reset,age_s";
constexpr const char* kOutputHeader =
    "t_s,status,warning_mask,usable,dev_fl_pct,dev_fr_pct,dev_rl_pct,dev_rr_pct";

/// Reads a numeric CSV with a known header into rows of exactly `columns` doubles.
std::vector<std::vector<double>> readNumericCsv(const std::string& path, const char* header,
                                                std::size_t columns) {
  std::ifstream file(path);
  if (!file) {
    throw std::runtime_error("cannot open " + path);
  }

  std::string line;
  std::getline(file, line);
  if (!line.empty() && line.back() == '\r') line.pop_back();
  if (line != header) {
    throw std::runtime_error(path + ": unexpected header '" + line + "'");
  }

  std::vector<std::vector<double>> rows;
  std::size_t line_number = 1;
  while (std::getline(file, line)) {
    ++line_number;
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line.empty()) continue;

    std::vector<double> row;
    row.reserve(columns);
    const char* cursor = line.c_str();
    while (true) {
      char* end = nullptr;
      const double value = std::strtod(cursor, &end);
      if (end == cursor) {
        throw std::runtime_error(path + ":" + std::to_string(line_number) + ": not a number");
      }
      row.push_back(value);
      if (*end != ',') {
        if (*end != '\0') {
          throw std::runtime_error(path + ":" + std::to_string(line_number) +
                                   ": unexpected character");
        }
        break;
      }
      cursor = end + 1;
    }
    if (row.size() != columns) {
      throw std::runtime_error(path + ":" + std::to_string(line_number) + ": expected " +
                               std::to_string(columns) + " columns");
    }
    rows.push_back(std::move(row));
  }
  return rows;
}

}  // namespace

std::vector<TimedSample> readInputCsv(const std::string& path) {
  const auto rows = readNumericCsv(path, kInputHeader, 10);
  std::vector<TimedSample> samples;
  samples.reserve(rows.size());
  for (const auto& r : rows) {
    TimedSample s;
    s.t_s = r[0];
    s.sample.wheel_speed_rad_s = {r[1], r[2], r[3], r[4]};
    s.sample.vehicle_speed_kmh = r[5];
    s.sample.steering_angle_deg = r[6];
    s.sample.brake_active = r[7] != 0.0;
    s.sample.reset_request = r[8] != 0.0;
    s.sample.signal_age_s = r[9];
    samples.push_back(s);
  }
  return samples;
}

std::vector<TimedOutput> readOutputCsv(const std::string& path) {
  const auto rows = readNumericCsv(path, kOutputHeader, 8);
  std::vector<TimedOutput> outputs;
  outputs.reserve(rows.size());
  for (const auto& r : rows) {
    TimedOutput o;
    o.t_s = r[0];
    o.output.status = static_cast<Status>(static_cast<int>(r[1]));
    o.output.warning_mask = static_cast<std::uint8_t>(r[2]);
    o.output.usable = r[3] != 0.0;
    o.output.deviation_pct = {r[4], r[5], r[6], r[7]};
    outputs.push_back(o);
  }
  return outputs;
}

void writeOutputCsv(const std::string& path, const std::vector<TimedOutput>& rows) {
  std::FILE* file = std::fopen(path.c_str(), "w");
  if (file == nullptr) {
    throw std::runtime_error("cannot write " + path);
  }
  std::fprintf(file, "%s\n", kOutputHeader);
  for (const auto& row : rows) {
    const Output& o = row.output;
    // %.17g round-trips a double exactly: no precision is lost for back-to-back comparison.
    std::fprintf(file, "%.2f,%d,%u,%d,%.17g,%.17g,%.17g,%.17g\n", row.t_s,
                 static_cast<int>(o.status), static_cast<unsigned>(o.warning_mask),
                 o.usable ? 1 : 0, o.deviation_pct[0], o.deviation_pct[1], o.deviation_pct[2],
                 o.deviation_pct[3]);
  }
  std::fclose(file);
}

}  // namespace tiretwin::io
