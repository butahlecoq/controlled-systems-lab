#include "hpipm_adapter.hpp"

#include <hpipm_common.h>
#include <hpipm_d_ocp_qp.h>
#include <hpipm_d_ocp_qp_dim.h>
#include <hpipm_d_ocp_qp_ipm.h>
#include <hpipm_d_ocp_qp_sol.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <memory>
#include <vector>

namespace csl::mpc01 {
namespace {

using Clock = std::chrono::steady_clock;
using Memory = std::unique_ptr<void, decltype(&std::free)>;

std::uint64_t elapsed_ns(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

Matrix transpose_storage(const Matrix& matrix) {
    if (matrix.empty()) return {};
    Matrix result(matrix.front().size(), Vector(matrix.size()));
    for (std::size_t row = 0; row < matrix.size(); ++row) {
        for (std::size_t column = 0; column < matrix[row].size(); ++column) {
            result[column][row] = matrix[row][column];
        }
    }
    return result;
}

Vector column_major(const Matrix& matrix) {
    const auto transposed = transpose_storage(matrix);
    Vector result;
    for (const auto& row : transposed) result.insert(result.end(), row.begin(), row.end());
    return result;
}

Box initial_box(const MpcCase& problem) {
    Box result{problem.initial_state, problem.initial_state};
    if (problem.stages[0].state) {
        for (std::size_t i = 0; i < result.lower.size(); ++i) {
            result.lower[i] = std::max(result.lower[i], problem.stages[0].state->lower[i]);
            result.upper[i] = std::min(result.upper[i], problem.stages[0].state->upper[i]);
        }
    }
    return result;
}

void assign_box(const Box& box, Vector& lower, Vector& upper,
                Vector& lower_mask, Vector& upper_mask) {
    for (std::size_t i = 0; i < lower.size(); ++i) {
        const bool has_lower = std::isfinite(box.lower[i]);
        const bool has_upper = std::isfinite(box.upper[i]);
        lower[i] = has_lower ? box.lower[i] : 0.0;
        upper[i] = has_upper ? box.upper[i] : 0.0;
        lower_mask[i] = has_lower ? 1.0 : 0.0;
        upper_mask[i] = has_upper ? 1.0 : 0.0;
    }
}

void extract_trajectory(const MpcCase& problem, d_ocp_qp_sol& solution,
                        NativeAttempt& attempt) {
    const auto nx = problem.state_dimension();
    const auto nu = problem.control_dimension();
    const auto horizon = problem.horizon();
    Trajectory trajectory;
    trajectory.states.resize(horizon + 1, Vector(nx));
    trajectory.controls.resize(horizon, Vector(nu));
    for (std::size_t t = 0; t <= horizon; ++t) {
        d_ocp_qp_sol_get_x(static_cast<int>(t), &solution, trajectory.states[t].data());
    }
    for (std::size_t t = 0; t < horizon; ++t) {
        d_ocp_qp_sol_get_u(static_cast<int>(t), &solution, trajectory.controls[t].data());
    }
    attempt.solver_primal.reserve((horizon + 1) * nx + horizon * nu);
    for (const auto& state : trajectory.states) {
        attempt.solver_primal.insert(attempt.solver_primal.end(), state.begin(), state.end());
    }
    for (const auto& control : trajectory.controls) {
        attempt.solver_primal.insert(attempt.solver_primal.end(), control.begin(), control.end());
    }
    attempt.witness = std::move(trajectory);
    attempt.original_objective = original_terminal_objective(problem, attempt.witness->states.back());
}

} // namespace

NativeAttempt solve_hpipm(const MpcCase& problem, const OcpQp& qp,
                          const NativeAttempt* warm_start) {
    NativeAttempt result;
    result.method = "hpipm-structured-ocp-qp";
    result.warm_start_requested = warm_start != nullptr;
    if (const auto error = validate(problem)) {
        result.termination = Termination::refused;
        result.native_status = "invalid-case";
        result.diagnostics = error->path + ": " + error->message;
        return result;
    }
    const int horizon = static_cast<int>(problem.horizon());
    const int nx_value = static_cast<int>(problem.state_dimension());
    const int nu_value = static_cast<int>(problem.control_dimension());
    if (qp.stages.size() != problem.horizon() + 1) {
        result.termination = Termination::refused;
        result.native_status = "stage-count-mismatch";
        return result;
    }
    const auto setup_start = Clock::now();

    const auto dim_bytes = d_ocp_qp_dim_memsize(horizon);
    Memory dim_memory(std::malloc(dim_bytes), &std::free);
    if (!dim_memory) {
        result.termination = Termination::failed;
        result.native_status = "dimension-allocation-failed";
        return result;
    }
    d_ocp_qp_dim dimension;
    d_ocp_qp_dim_create(horizon, &dimension, dim_memory.get());
    std::vector<int> nx(problem.horizon() + 1, nx_value);
    std::vector<int> nu(problem.horizon() + 1, nu_value);
    nu.back() = 0;
    std::vector<int> nbx(problem.horizon() + 1, nx_value);
    std::vector<int> nbu(problem.horizon() + 1, nu_value);
    nbu.back() = 0;
    std::vector<int> ng(problem.horizon() + 1, 0);
    std::vector<int> ns(problem.horizon() + 1, 0);
    d_ocp_qp_dim_set_all(nx.data(), nu.data(), nbx.data(), nbu.data(), ng.data(), ns.data(), &dimension);

    const auto qp_bytes = d_ocp_qp_memsize(&dimension);
    Memory qp_memory(std::malloc(qp_bytes), &std::free);
    const auto solution_bytes = d_ocp_qp_sol_memsize(&dimension);
    Memory solution_memory(std::malloc(solution_bytes), &std::free);
    if (!qp_memory || !solution_memory) {
        result.termination = Termination::failed;
        result.native_status = "qp-allocation-failed";
        return result;
    }
    d_ocp_qp native_qp;
    d_ocp_qp_create(&dimension, &native_qp, qp_memory.get());
    d_ocp_qp_sol solution;
    d_ocp_qp_sol_create(&dimension, &solution, solution_memory.get());

    std::vector<int> state_indices(problem.state_dimension());
    std::vector<int> control_indices(problem.control_dimension());
    for (std::size_t i = 0; i < state_indices.size(); ++i) state_indices[i] = static_cast<int>(i);
    for (std::size_t i = 0; i < control_indices.size(); ++i) control_indices[i] = static_cast<int>(i);
    const auto x0_bounds = initial_box(problem);
    for (std::size_t t = 0; t <= problem.horizon(); ++t) {
        const auto& stage = qp.stages[t];
        const auto q = column_major(stage.q);
        d_ocp_qp_set_Q(static_cast<int>(t), const_cast<double*>(q.data()), &native_qp);
        d_ocp_qp_set_q(static_cast<int>(t), const_cast<double*>(stage.q_linear.data()), &native_qp);
        d_ocp_qp_set_idxbx(static_cast<int>(t), state_indices.data(), &native_qp);
        Vector lower_x(nx_value), upper_x(nx_value), lower_mask(nx_value), upper_mask(nx_value);
        if (t == 0) {
            assign_box(x0_bounds, lower_x, upper_x, lower_mask, upper_mask);
        } else if (problem.stages[t].state) {
            assign_box(*problem.stages[t].state, lower_x, upper_x, lower_mask, upper_mask);
        } else {
            lower_x.assign(nx_value, 0.0);
            upper_x.assign(nx_value, 0.0);
            lower_mask.assign(nx_value, 0.0);
            upper_mask.assign(nx_value, 0.0);
        }
        d_ocp_qp_set_lbx(static_cast<int>(t), lower_x.data(), &native_qp);
        d_ocp_qp_set_ubx(static_cast<int>(t), upper_x.data(), &native_qp);
        d_ocp_qp_set_lbx_mask(static_cast<int>(t), lower_mask.data(), &native_qp);
        d_ocp_qp_set_ubx_mask(static_cast<int>(t), upper_mask.data(), &native_qp);
        if (t < problem.horizon()) {
            const auto r = column_major(stage.r);
            const auto s = column_major(stage.s);
            d_ocp_qp_set_R(static_cast<int>(t), const_cast<double*>(r.data()), &native_qp);
            d_ocp_qp_set_S(static_cast<int>(t), const_cast<double*>(s.data()), &native_qp);
            d_ocp_qp_set_r(static_cast<int>(t), const_cast<double*>(stage.r_linear.data()), &native_qp);
            d_ocp_qp_set_idxbu(static_cast<int>(t), control_indices.data(), &native_qp);
            Vector lower_u(nu_value), upper_u(nu_value), lower_u_mask(nu_value), upper_u_mask(nu_value);
            if (problem.stages[t].control) {
                assign_box(*problem.stages[t].control, lower_u, upper_u,
                           lower_u_mask, upper_u_mask);
            } else {
                lower_u.assign(nu_value, 0.0);
                upper_u.assign(nu_value, 0.0);
                lower_u_mask.assign(nu_value, 0.0);
                upper_u_mask.assign(nu_value, 0.0);
            }
            d_ocp_qp_set_lbu(static_cast<int>(t), lower_u.data(), &native_qp);
            d_ocp_qp_set_ubu(static_cast<int>(t), upper_u.data(), &native_qp);
            d_ocp_qp_set_lbu_mask(static_cast<int>(t), lower_u_mask.data(), &native_qp);
            d_ocp_qp_set_ubu_mask(static_cast<int>(t), upper_u_mask.data(), &native_qp);
            const auto a = column_major(stage.dynamics->a);
            const auto b = column_major(stage.dynamics->b);
            d_ocp_qp_set_A(static_cast<int>(t), const_cast<double*>(a.data()), &native_qp);
            d_ocp_qp_set_B(static_cast<int>(t), const_cast<double*>(b.data()), &native_qp);
            d_ocp_qp_set_b(static_cast<int>(t), const_cast<double*>(stage.dynamics->affine.data()), &native_qp);
        }
    }

    const auto arg_bytes = d_ocp_qp_ipm_arg_memsize(&dimension);
    Memory arg_memory(std::malloc(arg_bytes), &std::free);
    if (!arg_memory) {
        result.termination = Termination::failed;
        result.native_status = "argument-allocation-failed";
        return result;
    }
    d_ocp_qp_ipm_arg arg;
    d_ocp_qp_ipm_arg_create(&dimension, &arg, arg_memory.get());
    d_ocp_qp_ipm_arg_set_default(BALANCE, &arg);
    int max_iter = 1000;
    int warm = warm_start ? 1 : 0;
    double tolerance = 1e-8;
    d_ocp_qp_ipm_arg_set_iter_max(&max_iter, &arg);
    d_ocp_qp_ipm_arg_set_tol_stat(&tolerance, &arg);
    d_ocp_qp_ipm_arg_set_tol_eq(&tolerance, &arg);
    d_ocp_qp_ipm_arg_set_tol_ineq(&tolerance, &arg);
    d_ocp_qp_ipm_arg_set_tol_comp(&tolerance, &arg);
    d_ocp_qp_ipm_arg_set_warm_start(&warm, &arg);
    const auto workspace_bytes = d_ocp_qp_ipm_ws_memsize(&dimension, &arg);
    Memory workspace_memory(std::malloc(workspace_bytes), &std::free);
    if (!workspace_memory) {
        result.termination = Termination::failed;
        result.native_status = "workspace-allocation-failed";
        return result;
    }
    d_ocp_qp_ipm_ws workspace;
    d_ocp_qp_ipm_ws_create(&dimension, &arg, &workspace, workspace_memory.get());
    const auto setup_end = Clock::now();
    result.setup_ns = elapsed_ns(setup_start, setup_end);
    result.factorization_in_solve = true;

    if (warm_start && warm_start->witness) {
        const auto start = Clock::now();
        for (std::size_t t = 0; t <= problem.horizon(); ++t) {
            auto state = warm_start->witness->states[t];
            d_ocp_qp_sol_set_x(static_cast<int>(t), state.data(), &solution);
            if (t < problem.horizon()) {
                auto control = warm_start->witness->controls[t];
                d_ocp_qp_sol_set_u(static_cast<int>(t), control.data(), &solution);
            }
        }
        const auto end = Clock::now();
        result.warm_start_ns = elapsed_ns(start, end);
        result.warm_start_seed_applied = true;
    } else {
        d_ocp_qp_sol_set_zero(&solution);
    }

    const auto solve_start = Clock::now();
    d_ocp_qp_ipm_solve(&native_qp, &solution, &arg, &workspace);
    const auto solve_end = Clock::now();
    result.solve_ns = elapsed_ns(solve_start, solve_end);
    int iterations = -1;
    d_ocp_qp_ipm_get_iter(&workspace, &iterations);
    if (iterations >= 0) result.solver_iterations = static_cast<std::uint64_t>(iterations);
    int status = -1;
    d_ocp_qp_ipm_get_status(&workspace, &status);
    result.native_status = "hpipm-status-" + std::to_string(status);
    result.termination = Termination::completed;
    if (status == 0) result.outcome = MathematicalOutcome::optimal;
    else result.outcome = MathematicalOutcome::undetermined;
    double objective = 0.0;
    d_ocp_qp_ipm_get_obj(&workspace, &objective);
    result.solver_objective = objective + qp.objective_offset;

    const auto extraction_start = Clock::now();
    if (status == 0 || status == 1 || status == 2) extract_trajectory(problem, solution, result);
    const auto extraction_end = Clock::now();
    result.extraction_ns = elapsed_ns(extraction_start, extraction_end);
    return result;
}

} // namespace csl::mpc01
