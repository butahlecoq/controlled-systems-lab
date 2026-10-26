#include "fixtures.hpp"
#include "hpipm_adapter.hpp"
#include "osqp_adapter.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <span>
#include <stdexcept>
#include <string>
#include <variant>

namespace {

using namespace csl::mpc01;
using json = nlohmann::json;
using Clock = std::chrono::steady_clock;

std::uint64_t elapsed_ns(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

struct NumericCheck {
    double dynamics{};
    double state_bounds{};
    double control_bounds{};
};

double box_violation(std::span<const double> value, const std::optional<Box>& box) {
    if (!box) return 0.0;
    double violation = 0.0;
    for (std::size_t i = 0; i < value.size(); ++i) {
        if (std::isfinite(box->lower[i])) violation = std::max(violation, box->lower[i] - value[i]);
        if (std::isfinite(box->upper[i])) violation = std::max(violation, value[i] - box->upper[i]);
    }
    return std::max(0.0, violation);
}

NumericCheck check_trajectory(const MpcCase& problem, const Trajectory& trajectory) {
    NumericCheck check;
    if (trajectory.states.size() != problem.horizon() + 1 ||
        trajectory.controls.size() != problem.horizon()) {
        return {std::numeric_limits<double>::infinity(),
                std::numeric_limits<double>::infinity(),
                std::numeric_limits<double>::infinity()};
    }
    for (const auto& state : trajectory.states) {
        if (!std::all_of(state.begin(), state.end(), [](double value) { return std::isfinite(value); })) {
            return {std::numeric_limits<double>::infinity(),
                    std::numeric_limits<double>::infinity(),
                    std::numeric_limits<double>::infinity()};
        }
    }
    for (const auto& control : trajectory.controls) {
        if (!std::all_of(control.begin(), control.end(), [](double value) { return std::isfinite(value); })) {
            return {std::numeric_limits<double>::infinity(),
                    std::numeric_limits<double>::infinity(),
                    std::numeric_limits<double>::infinity()};
        }
    }
    check.state_bounds = box_violation(trajectory.states.front(),
        Box{problem.initial_state, problem.initial_state});
    for (std::size_t t = 0; t <= problem.horizon(); ++t) {
        check.state_bounds = std::max(check.state_bounds,
            box_violation(trajectory.states[t], problem.stages[t].state));
        if (t < problem.horizon()) {
            check.control_bounds = std::max(check.control_bounds,
                box_violation(trajectory.controls[t], problem.stages[t].control));
        }
    }
    for (std::size_t t = 0; t < problem.horizon(); ++t) {
        const auto& dynamics = problem.dynamics[t];
        for (std::size_t i = 0; i < problem.state_dimension(); ++i) {
            double predicted = dynamics.affine[i];
            for (std::size_t j = 0; j < problem.state_dimension(); ++j) {
                predicted += dynamics.a[i][j] * trajectory.states[t][j];
            }
            for (std::size_t j = 0; j < problem.control_dimension(); ++j) {
                predicted += dynamics.b[i][j] * trajectory.controls[t][j];
            }
            const double residual = std::abs(trajectory.states[t + 1][i] - predicted);
            check.dynamics = std::isfinite(residual)
                ? std::max(check.dynamics, residual)
                : std::numeric_limits<double>::infinity();
        }
    }
    return check;
}

std::string termination_name(Termination value) {
    switch (value) {
        case Termination::completed: return "completed";
        case Termination::refused: return "refused";
        case Termination::unsupported: return "unsupported";
        case Termination::failed: return "failed";
        case Termination::timed_out: return "timed_out";
        case Termination::resource_limited: return "resource_limited";
        case Termination::cancelled: return "cancelled";
        case Termination::incomplete: return "incomplete";
    }
    return "incomplete";
}

std::string outcome_name(MathematicalOutcome value) {
    switch (value) {
        case MathematicalOutcome::optimal: return "optimal";
        case MathematicalOutcome::feasible: return "feasible";
        case MathematicalOutcome::infeasible: return "infeasible";
        case MathematicalOutcome::unbounded: return "unbounded";
        case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "undetermined";
}

json serialize_attempt(const MpcCase& problem, const NativeAttempt& attempt,
                       const std::string& start_mode) {
    json row = {{"schema", "csl.mpc01-native-attempt/1"},
                {"case_id", problem.id},
                {"case_version", problem.version},
                {"input_sha256", problem.canonical_input_sha256},
                {"method", attempt.method},
                {"start_mode", start_mode},
                {"termination", termination_name(attempt.termination)},
                {"mathematical_outcome", outcome_name(attempt.outcome)},
                {"native_status", attempt.native_status},
                {"timings_ns", {{"formulation", attempt.formulation_ns},
                                {"setup", attempt.setup_ns},
                                {"warm_start", attempt.warm_start_ns},
                                {"solve", attempt.solve_ns},
                                {"extraction", attempt.extraction_ns}}},
                {"factorization_in_setup", attempt.factorization_in_setup},
                {"factorization_in_solve", attempt.factorization_in_solve},
                {"diagnostics", attempt.diagnostics}};
    row["solver_objective"] = attempt.solver_objective
        ? json(*attempt.solver_objective) : json(nullptr);
    row["original_objective"] = attempt.original_objective
        ? json(*attempt.original_objective) : json(nullptr);
    if (attempt.witness) {
        const auto check = check_trajectory(problem, *attempt.witness);
        row["trajectory"] = {{"states", attempt.witness->states},
                             {"controls", attempt.witness->controls}};
        row["original_data_diagnostics"] = {
            {"checker", "binary64-residual-diagnostic/1"},
            {"evidence_status", "inconclusive"},
            {"max_dynamics_residual", check.dynamics},
            {"max_state_bound_violation", check.state_bounds},
            {"max_control_bound_violation", check.control_bounds}};
    }
    return row;
}

MpcCase take_fixture(FixtureLoad result) {
    if (const auto* error = std::get_if<std::string>(&result)) throw std::runtime_error(*error);
    return std::get<MpcCase>(std::move(result));
}

void run_case(const MpcCase& problem, bool hpipm_first) {
    const auto run_osqp = [&] {
        const auto map_start = Clock::now();
        const auto mapped = make_osqp_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped)) {
            throw std::runtime_error("OSQP map " + error->path + ": " + error->message);
        }
        auto cold = solve_osqp(problem, std::get<SparseQp>(mapped));
        cold.formulation_ns = elapsed_ns(map_start, map_end);
        std::cout << serialize_attempt(problem, cold, "cold").dump() << '\n';
        const auto warm_map_start = Clock::now();
        const auto warm_mapped = make_osqp_problem(problem);
        const auto warm_map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&warm_mapped)) {
            throw std::runtime_error("OSQP warm map " + error->path + ": " + error->message);
        }
        auto warm = solve_osqp(problem, std::get<SparseQp>(warm_mapped),
                               cold.witness ? &cold : nullptr);
        warm.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        std::cout << serialize_attempt(problem, warm,
            cold.witness ? "warm_previous_witness" : "cold_fallback_no_witness").dump() << '\n';
    };
    const auto run_hpipm = [&] {
        const auto map_start = Clock::now();
        const auto mapped = make_hpipm_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped)) {
            throw std::runtime_error("HPIPM map " + error->path + ": " + error->message);
        }
        auto cold = solve_hpipm(problem, std::get<OcpQp>(mapped));
        cold.formulation_ns = elapsed_ns(map_start, map_end);
        std::cout << serialize_attempt(problem, cold, "cold").dump() << '\n';
        const auto warm_map_start = Clock::now();
        const auto warm_mapped = make_hpipm_problem(problem);
        const auto warm_map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&warm_mapped)) {
            throw std::runtime_error("HPIPM warm map " + error->path + ": " + error->message);
        }
        auto warm = solve_hpipm(problem, std::get<OcpQp>(warm_mapped),
                                cold.witness ? &cold : nullptr);
        warm.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        std::cout << serialize_attempt(problem, warm,
            cold.witness ? "warm_previous_witness" : "cold_fallback_no_witness").dump() << '\n';
    };
    if (hpipm_first) {
        run_hpipm();
        run_osqp();
    } else {
        run_osqp();
        run_hpipm();
    }
}

} // namespace

int main(int argc, char** argv) {
    try {
        const bool hpipm_first = argc == 4 && std::string(argv[3]) == "--reverse";
        if (argc != 3 && !hpipm_first) {
            std::cerr << "usage: csl_mpc01_report <double-integrator-generality.json> <b04-reference-v1/canonical-case.json> [--reverse]\n";
            return 2;
        }
        run_case(make_ts01(), hpipm_first);
        run_case(make_ts02(), hpipm_first);
        run_case(take_fixture(load_double_integrator_421(argv[1])), hpipm_first);
        run_case(take_fixture(load_b04_reference_v1(argv[2])), hpipm_first);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "MPC-01 run failed: " << error.what() << '\n';
        return 1;
    }
}
