#include "osqp_adapter.hpp"

#include <osqp.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <memory>
#include <sstream>

namespace csl::mpc01 {
namespace {

using Clock = std::chrono::steady_clock;
using CscHandle = std::unique_ptr<OSQPCscMatrix, decltype(&OSQPCscMatrix_free)>;
using SolverHandle = std::unique_ptr<OSQPSolver, decltype(&osqp_cleanup)>;

std::uint64_t elapsed_ns(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

bool dimensions_fit(const SparseQp& qp) {
    const auto maximum = static_cast<std::size_t>(std::numeric_limits<OSQPInt>::max());
    return qp.hessian.rows <= maximum &&
           qp.constraints.rows + qp.variable_lower.size() <= maximum &&
           qp.hessian.values.size() <= maximum &&
           qp.constraints.values.size() + qp.variable_lower.size() <= maximum;
}

struct OwnedCsc {
    std::vector<OSQPFloat> values;
    std::vector<OSQPInt> rows;
    std::vector<OSQPInt> columns;
};

OwnedCsc copy_csc(const CscMatrix& matrix) {
    OwnedCsc copy;
    copy.values.assign(matrix.values.begin(), matrix.values.end());
    copy.rows.reserve(matrix.row_indices.size());
    copy.columns.reserve(matrix.column_offsets.size());
    for (auto value : matrix.row_indices) copy.rows.push_back(static_cast<OSQPInt>(value));
    for (auto value : matrix.column_offsets) copy.columns.push_back(static_cast<OSQPInt>(value));
    return copy;
}

OwnedCsc with_variable_bounds(const SparseQp& qp, Vector& lower, Vector& upper) {
    OwnedCsc combined;
    const auto variable_count = qp.variable_lower.size();
    const auto dynamics_rows = qp.constraints.rows;
    combined.columns.reserve(qp.constraints.column_offsets.size());
    combined.rows.reserve(qp.constraints.row_indices.size() + variable_count);
    combined.values.reserve(qp.constraints.values.size() + variable_count);
    combined.columns.push_back(0);
    for (std::size_t column = 0; column < variable_count; ++column) {
        for (auto entry = qp.constraints.column_offsets[column];
             entry < qp.constraints.column_offsets[column + 1]; ++entry) {
            combined.rows.push_back(static_cast<OSQPInt>(qp.constraints.row_indices[entry]));
            combined.values.push_back(static_cast<OSQPFloat>(qp.constraints.values[entry]));
        }
        combined.rows.push_back(static_cast<OSQPInt>(dynamics_rows + column));
        combined.values.push_back(1.0);
        combined.columns.push_back(static_cast<OSQPInt>(combined.values.size()));
    }
    lower = qp.row_lower;
    lower.insert(lower.end(), qp.variable_lower.begin(), qp.variable_lower.end());
    upper = qp.row_upper;
    upper.insert(upper.end(), qp.variable_upper.begin(), qp.variable_upper.end());
    for (auto& bound : lower) {
        if (!std::isfinite(bound)) bound = -static_cast<double>(OSQP_INFTY);
    }
    for (auto& bound : upper) {
        if (!std::isfinite(bound)) bound = static_cast<double>(OSQP_INFTY);
    }
    return combined;
}

void read_trajectory(const MpcCase& problem, const Vector& primal,
                     NativeAttempt& attempt) {
    const auto nx = problem.state_dimension();
    const auto nu = problem.control_dimension();
    const auto horizon = problem.horizon();
    const auto state_count = (horizon + 1) * nx;
    if (primal.size() != state_count + horizon * nu) return;
    Trajectory trajectory;
    trajectory.states.resize(horizon + 1, Vector(nx));
    trajectory.controls.resize(horizon, Vector(nu));
    for (std::size_t t = 0; t <= horizon; ++t) {
        std::copy_n(primal.begin() + static_cast<std::ptrdiff_t>(t * nx), nx,
                    trajectory.states[t].begin());
    }
    for (std::size_t t = 0; t < horizon; ++t) {
        const auto offset = state_count + t * nu;
        std::copy_n(primal.begin() + static_cast<std::ptrdiff_t>(offset), nu,
                    trajectory.controls[t].begin());
    }
    attempt.witness = std::move(trajectory);
    attempt.original_objective = original_terminal_objective(problem, attempt.witness->states.back());
}

void classify_status(OSQPInt status, NativeAttempt& attempt) {
    attempt.termination = Termination::completed;
    switch (status) {
        case OSQP_SOLVED:
            attempt.outcome = MathematicalOutcome::optimal;
            break;
        case OSQP_PRIMAL_INFEASIBLE:
            attempt.outcome = MathematicalOutcome::infeasible;
            break;
        case OSQP_DUAL_INFEASIBLE:
            attempt.outcome = MathematicalOutcome::unbounded;
            break;
        case OSQP_PRIMAL_INFEASIBLE_INACCURATE:
        case OSQP_DUAL_INFEASIBLE_INACCURATE:
            attempt.outcome = MathematicalOutcome::undetermined;
            break;
        case OSQP_TIME_LIMIT_REACHED:
            attempt.outcome = MathematicalOutcome::undetermined;
            attempt.termination = Termination::timed_out;
            break;
        case OSQP_SOLVED_INACCURATE:
        case OSQP_MAX_ITER_REACHED:
        case OSQP_NON_CVX:
        case OSQP_SIGINT:
        case OSQP_UNSOLVED:
        default:
            attempt.outcome = MathematicalOutcome::undetermined;
            break;
    }
}

} // namespace

NativeAttempt solve_osqp(const MpcCase& problem, const SparseQp& qp,
                         const NativeAttempt* warm_start) {
    NativeAttempt result;
    result.method = "osqp-sparse-qp";
    result.warm_start_requested = warm_start != nullptr;
    if (const auto error = validate(problem)) {
        result.termination = Termination::refused;
        result.native_status = "invalid-case";
        result.diagnostics = error->path + ": " + error->message;
        return result;
    }
    if (!dimensions_fit(qp)) {
        result.termination = Termination::refused;
        result.native_status = "dimension-overflow";
        result.diagnostics = "mapped sparse QP dimensions exceed OSQPInt";
        return result;
    }

    const auto setup_start = Clock::now();
    auto p_data = copy_csc(qp.hessian);
    Vector row_lower;
    Vector row_upper;
    auto a_data = with_variable_bounds(qp, row_lower, row_upper);
    CscHandle p(OSQPCscMatrix_new(static_cast<OSQPInt>(qp.hessian.rows),
                                  static_cast<OSQPInt>(qp.hessian.columns),
                                  static_cast<OSQPInt>(p_data.values.size()), p_data.values.data(),
                                  p_data.rows.data(), p_data.columns.data()),
                &OSQPCscMatrix_free);
    CscHandle a(OSQPCscMatrix_new(static_cast<OSQPInt>(row_lower.size()),
                                  static_cast<OSQPInt>(qp.constraints.columns),
                                  static_cast<OSQPInt>(a_data.values.size()), a_data.values.data(),
                                  a_data.rows.data(), a_data.columns.data()),
                &OSQPCscMatrix_free);
    if (!p || !a) {
        result.termination = Termination::failed;
        result.native_status = "csc-allocation-failed";
        return result;
    }

    OSQPSettings settings;
    osqp_set_default_settings(&settings);
    settings.verbose = 0;
    settings.warm_starting = 1;
    settings.max_iter = 200000;
    settings.eps_abs = 1e-7;
    settings.eps_rel = 1e-7;

    OSQPSolver* raw_solver = nullptr;
    const auto setup_error = osqp_setup(
        &raw_solver, p.get(), const_cast<OSQPFloat*>(qp.linear.data()), a.get(),
        row_lower.data(), row_upper.data(), static_cast<OSQPInt>(row_lower.size()),
        static_cast<OSQPInt>(qp.hessian.columns), &settings);
    const auto setup_end = Clock::now();
    result.setup_ns = elapsed_ns(setup_start, setup_end);
    result.factorization_in_setup = true;
    SolverHandle solver(raw_solver, &osqp_cleanup);
    if (setup_error != 0 || !solver) {
        result.termination = Termination::failed;
        result.native_status = "setup-error-" + std::to_string(setup_error);
        result.diagnostics = osqp_error_message(setup_error);
        return result;
    }

    if (warm_start && warm_start->solver_primal.size() == qp.linear.size() &&
        warm_start->solver_dual.size() == row_lower.size()) {
        const auto start = Clock::now();
        const auto warm_error = osqp_warm_start(solver.get(), warm_start->solver_primal.data(),
                                                warm_start->solver_dual.data());
        const auto end = Clock::now();
        result.warm_start_ns = elapsed_ns(start, end);
        result.warm_start_seed_applied = warm_error == 0;
        if (warm_error != 0) {
            result.diagnostics = "warm-start-error-" + std::to_string(warm_error);
        }
    } else {
        osqp_cold_start(solver.get());
    }

    const auto solve_start = Clock::now();
    const auto solve_error = osqp_solve(solver.get());
    const auto solve_end = Clock::now();
    result.solve_ns = elapsed_ns(solve_start, solve_end);
    result.factorization_in_solve = true;
    if (solve_error != 0) {
        result.termination = Termination::failed;
        result.native_status = "solve-error-" + std::to_string(solve_error);
        result.diagnostics = osqp_error_message(solve_error);
        return result;
    }
    if (!solver->info) {
        result.termination = Termination::failed;
        result.native_status = "missing-info";
        return result;
    }
    result.native_status = solver->info->status;
    if (solver->info->iter >= 0)
        result.solver_iterations = static_cast<std::uint64_t>(solver->info->iter);
    classify_status(solver->info->status_val, result);
    result.solver_objective = solver->info->obj_val + qp.objective_offset;

    const auto extraction_start = Clock::now();
    const auto variable_count = qp.linear.size();
    if (solver->solution && solver->solution->x) {
        result.solver_primal.assign(solver->solution->x, solver->solution->x + variable_count);
        read_trajectory(problem, result.solver_primal, result);
    }
    if (solver->solution && solver->solution->y) {
        result.solver_dual.assign(solver->solution->y,
                                  solver->solution->y + row_lower.size());
    }
    const auto extraction_end = Clock::now();
    result.extraction_ns = elapsed_ns(extraction_start, extraction_end);
    if (result.witness) {
        const auto state_offset = problem.horizon() * problem.state_dimension();
        (void)state_offset;
    }
    return result;
}

} // namespace csl::mpc01
