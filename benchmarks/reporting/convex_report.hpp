#pragma once
#include "report_runtime.hpp"
#include <csl/adapters/convex/highs.hpp>
namespace csl::reporting::convex {
struct Fixture {
    std::string id;
    optimization::ConvexProgramInput input;
    MathematicalOutcome expected;
    std::optional<Vector> point;
    std::vector<csl::Interval> coordinate_constraints;
    std::optional<double> objective, solver_objective;
    std::string derivation;
};
struct TrialRecord {
    std::optional<ConvexProgram> program;
    std::optional<ProgramResult> result;
    std::optional<ConvexSolveAttempt> attempt;
    std::optional<double> objective, solver_objective;
    std::string harness_status="exception",error,actual_version;
    std::vector<std::string> errors;
    Diagnostics diagnostics;
    std::array<reporting::Interval,6> timings{};
    std::uint64_t observation=0;
    bool passed() const {return harness_status=="returned" && errors.empty();}
};
const std::vector<Fixture>& catalogue();
TrialRecord run_trial(const Fixture&,std::stop_token,adapters::convex::HighsConvexOptions = {});
std::string catalogue_json();
std::string trial_json(const Fixture&,const TrialRecord&,std::size_t,std::size_t,const std::string&);
}
