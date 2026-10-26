#include "../../benchmarks/reporting/mpc01/fixtures.hpp"
#include "../../benchmarks/reporting/mpc01/problem_mapping.hpp"

#include <cstdlib>
#include <cmath>
#include <iostream>
#include <limits>

namespace {

csl::mpc01::MpcCase scalar_case() {
    using namespace csl::mpc01;
    MpcCase result;
    result.id = "ts01-exact";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "T-S01";
    result.canonical_input_bytes = "{}";
    result.canonical_input_sha256 = "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a";
    result.initial_state = {0.0};
    result.dynamics = {{{{1.0}}, {{1.0}}, {0.0}},
                       {{{1.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, Box{{0.0}, {1.0}}},
                     {{}, Box{{0.0}, {1.0}}},
                     {{}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{2.0}}, {-2.0}, 1.0};
    return result;
}

int fail(const char* message) {
    std::cerr << message << '\n';
    return EXIT_FAILURE;
}

double at(const csl::mpc01::CscMatrix& matrix, std::size_t row, std::size_t column) {
    for (std::size_t i = matrix.column_offsets[column]; i < matrix.column_offsets[column + 1]; ++i) {
        if (matrix.row_indices[i] == row) return matrix.values[i];
    }
    return 0.0;
}

} // namespace

int main(int argc, char** argv) {
    using namespace csl::mpc01;
    auto mismatched_input = scalar_case();
    mismatched_input.canonical_input_sha256 = std::string(64, 'a');
    if (!validate(mismatched_input)) return fail("case input digest mismatch was accepted");
    if (validate(scalar_case())) return fail("valid scalar fixture rejected");
    if (validate(make_ts01())) return fail("T-S01 fixture is invalid");
    if (validate(make_ts02())) return fail("T-S02 fixture is invalid");
    if (validate(make_infeasible())) return fail("infeasible analytic fixture is invalid");
    if (validate(make_unbounded())) return fail("unbounded analytic fixture is invalid");
    const auto infeasible = make_infeasible();
    const auto& infeasible_dynamics = infeasible.dynamics.front();
    const auto forced_next = infeasible_dynamics.a[0][0] * infeasible.initial_state[0] +
                             infeasible_dynamics.b[0][0] * 0.0 +
                             infeasible_dynamics.affine[0];
    if (!infeasible.stages.front().control ||
        infeasible.stages.front().control->lower != Vector{0.0} ||
        infeasible.stages.front().control->upper != Vector{0.0} ||
        !infeasible.stages.back().state || forced_next != 0.0 ||
        infeasible.stages.back().state->lower != Vector{1.0} ||
        infeasible.stages.back().state->upper != Vector{1.0}) {
        return fail("exact infeasibility oracle no longer encodes 0=1");
    }
    const auto unbounded = make_unbounded();
    if (unbounded.stages.front().control || unbounded.stages.back().state ||
        unbounded.dynamics.front().b[0][0] != 1.0) {
        return fail("exact unboundedness oracle lost its free control direction");
    }
    for (const double control : Vector{0.0, 1.0, 2.0, 4.0}) {
        const auto terminal = unbounded.dynamics.front().a[0][0] * unbounded.initial_state[0] +
                             unbounded.dynamics.front().b[0][0] * control +
                             unbounded.dynamics.front().affine[0];
        if (original_terminal_objective(unbounded, Vector{terminal}) != -control) {
            return fail("exact unboundedness oracle does not decrease along its feasible recession direction");
        }
    }
    const auto ts01 = make_ts01();
    const auto sparse = make_osqp_problem(ts01);
    if (!std::holds_alternative<SparseQp>(sparse)) return fail("T-S01 sparse mapping failed");
    const auto& ts01_qp = std::get<SparseQp>(sparse);
    if (ts01_qp.hessian.rows != 5 || ts01_qp.constraints.rows != 2 ||
        at(ts01_qp.constraints, 0, 0) != -1.0 || at(ts01_qp.constraints, 0, 1) != 1.0 ||
        at(ts01_qp.constraints, 0, 3) != -1.0 || ts01_qp.row_lower != Vector{0.0, 0.0} ||
        ts01_qp.hessian.values != Vector{2.0}) {
        return fail("T-S01 sparse matrix does not encode the original stage equations and cost");
    }
    const auto structured = make_hpipm_problem(ts01);
    if (!std::holds_alternative<OcpQp>(structured)) return fail("T-S01 OCP-QP mapping failed");
    const auto& ts01_ocp = std::get<OcpQp>(structured);
    if (ts01_ocp.stages.size() != 3 || !ts01_ocp.stages[0].dynamics ||
        ts01_ocp.stages[2].dynamics || ts01_ocp.stages[2].q[0][0] != 2.0 ||
        ts01_ocp.stages[2].q_linear[0] != -2.0) {
        return fail("T-S01 structured mapping does not preserve its stage structure and terminal cost");
    }
    if (original_terminal_objective(ts01, Vector{1.0}) != 0.0) {
        return fail("original T-S01 objective evaluator disagrees with the analytic optimum");
    }
    auto problem = scalar_case();
    if (validate(problem)) return fail("valid scalar fixture rejected");
    problem.dynamics[1].b[0].push_back(2.0);
    const auto ragged = validate(problem);
    if (!ragged || ragged->path != "dynamics[1].B") {
        return fail("stage-varying control dimension mismatch was not identified");
    }
    problem = scalar_case();
    problem.stages[0].control->lower[0] = 2.0;
    const auto reversed = validate(problem);
    if (!reversed || reversed->path != "stages[0].control") {
        return fail("reversed control interval was not identified");
    }
    problem = scalar_case();
    problem.terminal_cost = AffineResidualNormTerminalCost{{{1.0}, {2.0}}, {0.0, 1.0}};
    if (validate(problem)) return fail("valid affine residual norm fixture rejected");
    if (argc >= 2) {
        auto loaded = load_double_integrator_421(argv[1]);
        if (const auto* error = std::get_if<std::string>(&loaded)) return fail(error->c_str());
        const auto& fixture = std::get<MpcCase>(loaded);
        if (fixture.id != "double-integrator-421-v1" || fixture.horizon() != 3 ||
            fixture.state_dimension() != 2 || fixture.control_dimension() != 1) {
            return fail("#421 scenario identity or dimensions differ from its contract");
        }
        if (!fixture.stages[1].state || fixture.stages[1].state->lower != Vector{0.0, -1.0} ||
            fixture.stages[1].state->upper != Vector{0.5, 1.0}) {
            return fail("#421 stage-1 state bounds differ from the canonical scenario");
        }
        const auto* cost = std::get_if<QuadraticTerminalCost>(&fixture.terminal_cost);
        if (!cost || cost->q != Matrix{{2.0, 0.0}, {0.0, 2.0}} ||
            cost->linear != Vector{-2.0, -1.0} || cost->offset != 1.25) {
            return fail("#421 terminal objective differs from the canonical scenario");
        }
    }
    if (argc == 3) {
        auto loaded = load_b04_reference_v1(argv[2]);
        if (const auto* error = std::get_if<std::string>(&loaded)) return fail(error->c_str());
        const auto& fixture = std::get<MpcCase>(loaded);
        if (fixture.id != "b04-reference-v1" || fixture.horizon() != 16 ||
            fixture.state_dimension() != 4 || fixture.control_dimension() != 1) {
            return fail("B04 reference identity or dimensions changed");
        }
        if (!fixture.stages[0].state || !fixture.stages[16].state || fixture.stages[1].state ||
            fixture.stages[0].state->lower[0] != 1176.0 ||
            fixture.stages[0].state->upper[2] != 468.0 ||
            !std::isinf(fixture.stages[0].state->lower[1]) ||
            fixture.stages[0].state->lower[1] > 0.0 ||
            fixture.stages[16].state->upper[3] != std::numeric_limits<double>::infinity()) {
            return fail("B04 flow limits or unconstrained stock coordinates changed");
        }
        if (!std::holds_alternative<AffineResidualNormTerminalCost>(fixture.terminal_cost)) {
            return fail("B04 terminal objective was not retained as an affine residual norm");
        }
        const auto b04_sparse = make_osqp_problem(fixture);
        if (!std::holds_alternative<SparseQp>(b04_sparse) ||
            std::get<SparseQp>(b04_sparse).objective_transform !=
                ObjectiveTransform::residual_norm_squared) {
            return fail("B04 sparse mapping failed to record its norm-squared solver transformation");
        }
        const Vector terminal{1200.0, 0.0, 1200.0, 0.0};
        const auto& mapped = std::get<SparseQp>(b04_sparse);
        double squared_solver_value = mapped.objective_offset;
        const auto terminal_offset = fixture.horizon() * fixture.state_dimension();
        for (std::size_t i = 0; i < terminal.size(); ++i) {
            squared_solver_value += mapped.linear[terminal_offset + i] * terminal[i];
            for (std::size_t j = i; j < terminal.size(); ++j) {
                const double scale = (i == j) ? 0.5 : 1.0;
                squared_solver_value += scale * at(mapped.hessian, terminal_offset + i,
                                                   terminal_offset + j) * terminal[i] * terminal[j];
            }
        }
        const auto original_value = original_terminal_objective(fixture, terminal);
        if (std::abs(squared_solver_value - original_value * original_value) > 1e-7) {
            return fail("B04 solver objective is not the square of its original residual norm");
        }
        const auto b04_structured = make_hpipm_problem(fixture);
        if (!std::holds_alternative<OcpQp>(b04_structured) ||
            std::get<OcpQp>(b04_structured).stages.size() != 17 ||
            std::get<OcpQp>(b04_structured).stages.back().q[0][0] == 0.0) {
            return fail("B04 OCP mapping did not retain all 16 transitions and terminal cost");
        }
    }
    return EXIT_SUCCESS;
}
