#pragma once
#include <csl/optimization/lp_backend.hpp>
#include <array>
#include <chrono>
#include <cstdint>
#include <ostream>
#include <stop_token>

namespace csl::reporting {
using Clock = std::chrono::steady_clock;
struct Fixture {
    std::string id;
    LinearProgramInput input;
    MathematicalOutcome expected;
    std::optional<Vector> point;
    std::optional<double> objective;
    std::string derivation;
};
struct Interval {
    bool available = false;
    Clock::rep start = 0, end = 0;
    std::int64_t nanoseconds() const;
};
struct TrialRecord {
    std::optional<LinearProgram> program;
    std::optional<ProgramResult> result;
    std::optional<SolveAttempt> attempt;
    std::optional<double> objective;
    std::string harness_status = "exception", error, actual_version;
    std::vector<std::string> errors;
    Diagnostics diagnostics;
    std::array<Interval,6> timings{};
    std::uint64_t observation = 0;
    bool passed() const { return harness_status == "returned" && errors.empty(); }
};
const std::vector<Fixture>& catalogue();
TrialRecord run_trial(const Fixture&, std::stop_token);
std::string json_string(const std::string&);
std::string json_number(double);
std::string catalogue_json();
std::string trial_json(const Fixture&, const TrialRecord&, std::size_t round, std::size_t sequence, const std::string& purpose);
std::string build_info_json();
} // namespace csl::reporting
