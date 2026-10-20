from fractions import Fraction
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
case = json.loads((ROOT / "canonical-case.json").read_text(encoding="utf-8-sig"))
n, horizon = case["state_dimension"], case["horizon"]

def F(value):
    return Fraction(str(value))

def cdouble(value):
    return format(float(F(value)), ".17g")

def array(values):
    return ", ".join(cdouble(value) for value in values)

def matrix_col_major(row_major, rows, cols):
    return [row_major[i * cols + j] for j in range(cols) for i in range(rows)]

Wraw = case["terminal_objective"]["W_row_major"]
W = [[F(Wraw[i*n+j]) for j in range(n)] for i in range(case["terminal_objective"]["matrix_rows"])]
target = [F(value) for value in case["terminal_objective"]["target"]]
Araw = case["dynamics"]["A_row_major"]
A = [[F(Araw[i*n+j]) for j in range(n)] for i in range(n)]
B = [F(value) for value in case["dynamics"]["B"]]
x0 = [F(value) for value in case["initial_state"]]
base = x0[:]
for _ in range(horizon):
    base = [sum((A[i][j] * base[j] for j in range(n)), Fraction(0)) for i in range(n)]
Nmat = [[A[i][j] - Fraction(int(i == j)) for j in range(n)] for i in range(n)]
NB = [sum((Nmat[i][j] * B[j] for j in range(n)), Fraction(0)) for i in range(n)]
WB = [sum((row[j] * B[j] for j in range(n)), Fraction(0)) for row in W]
WNB = [sum((row[j] * NB[j] for j in range(n)), Fraction(0)) for row in W]
V = [[WB[i], WNB[i]] for i in range(len(W))]
y = [sum((W[i][j] * base[j] for j in range(n)), Fraction(0)) - target[i] for i in range(len(W))]
Qterminal = [[2 * sum((row[i] * row[j] for row in W), Fraction(0)) for j in range(n)] for i in range(n)]
qterminal = [-2 * sum((W[k][i] * target[k] for k in range(len(target))), Fraction(0)) for i in range(n)]
terminal_offset = sum((value * value for value in target), Fraction(0))
Qterminal_flat = [Qterminal[i][j] for i in range(n) for j in range(n)]
Qmoments = [[sum((row[i] * row[j] for row in V), Fraction(0)) for j in range(2)] for i in range(2)]
qmoments = [sum((V[k][i] * y[k] for k in range(len(y))), Fraction(0)) for i in range(2)]
moment_offset = sum((value * value for value in y), Fraction(0)) / 2
Qmoments_flat = [Qmoments[i][j] for i in range(2) for j in range(2)]

source_c = r'''#include <stdio.h>
#include "acados_c/ocp_qp_interface.h"

int main(void) {
    const int N = @@N@@;
    const int nx_value = @@NX@@;
    const double A[] = {@@A_COL@@};
    const double B[] = {@@B@@};
    const double affine[] = {@@AFFINE@@};
    const double Qstage[] = {@@QSTAGE@@};
    const double Sstage[] = {@@SSTAGE@@};
    const double Rstage[] = {0.0};
    const double qstage[] = {@@QSTAGE_LINEAR@@};
    const double rstage[] = {0.0};
    const double initial[] = {@@INITIAL@@};
    const int idxbu[] = {0};
    const int idxbx_initial[] = {0, 1, 2, 3};
    const int idxbx_flow[] = {@@FLOW_COORDS@@};
    const double flow_lower[] = {@@FLOW_LOWER@@};
    const double flow_upper[] = {@@FLOW_UPPER@@};
    const double control_lower[] = {@@CONTROL_LOWER@@};
    const double control_upper[] = {@@CONTROL_UPPER@@};
    const double Qterminal[] = {@@QTERMINAL@@};
    const double qterminal[] = {@@QTERMINAL_LINEAR@@};
    ocp_qp_solver_plan_t plan;
    plan.qp_solver = FULL_CONDENSING_HPIPM;
    ocp_qp_xcond_solver_config *config = ocp_qp_xcond_solver_config_create(plan);
    ocp_qp_dims *dims = ocp_qp_dims_create(N);
    for (int stage = 0; stage <= N; ++stage) {
        int nx = nx_value;
        int nu = stage < N ? 1 : 0;
        ocp_qp_dims_set(config, dims, stage, "nx", &nx);
        ocp_qp_dims_set(config, dims, stage, "nu", &nu);
        if (stage < N) {
            int nbu = 1;
            ocp_qp_dims_set(config, dims, stage, "nbu", &nbu);
        }
        int nbx = stage == 0 ? nx_value : 2;
        ocp_qp_dims_set(config, dims, stage, "nbx", &nbx);
    }
    ocp_qp_in *in = ocp_qp_in_create(dims);
    for (int stage = 0; stage < N; ++stage) {
        ocp_qp_in_set(config, in, stage, "A", (void *)A);
        ocp_qp_in_set(config, in, stage, "B", (void *)B);
        ocp_qp_in_set(config, in, stage, "b", (void *)affine);
        ocp_qp_in_set(config, in, stage, "Q", (void *)Qstage);
        ocp_qp_in_set(config, in, stage, "S", (void *)Sstage);
        ocp_qp_in_set(config, in, stage, "R", (void *)Rstage);
        ocp_qp_in_set(config, in, stage, "q", (void *)qstage);
        ocp_qp_in_set(config, in, stage, "r", (void *)rstage);
        ocp_qp_in_set(config, in, stage, "idxbu", (void *)idxbu);
        ocp_qp_in_set(config, in, stage, "lbu", (void *)&control_lower[stage]);
        ocp_qp_in_set(config, in, stage, "ubu", (void *)&control_upper[stage]);
    }
    ocp_qp_in_set(config, in, 0, "idxbx", (void *)idxbx_initial);
    ocp_qp_in_set(config, in, 0, "lbx", (void *)initial);
    ocp_qp_in_set(config, in, 0, "ubx", (void *)initial);
    for (int stage = 1; stage <= N; ++stage) {
        ocp_qp_in_set(config, in, stage, "idxbx", (void *)idxbx_flow);
        ocp_qp_in_set(config, in, stage, "lbx", (void *)flow_lower);
        ocp_qp_in_set(config, in, stage, "ubx", (void *)flow_upper);
    }
    ocp_qp_in_set(config, in, N, "Q", (void *)Qterminal);
    ocp_qp_in_set(config, in, N, "q", (void *)qterminal);
    ocp_qp_xcond_solver_dims *solver_dims = ocp_qp_xcond_solver_dims_create_from_ocp_qp_dims(config, dims);
    void *opts = ocp_qp_xcond_solver_opts_create(config, solver_dims);
    ocp_qp_out *out = ocp_qp_out_create(dims);
    ocp_qp_solver *solver = ocp_qp_create(config, solver_dims, opts);
    const int status = ocp_qp_solve(solver, in, out);
    double residual[4] = {0.0, 0.0, 0.0, 0.0};
    ocp_qp_inf_norm_residuals(dims, in, out, residual);
    printf("case=@@CASE@@\nsolver=FULL_CONDENSING_HPIPM\nstatus=%d\n", status);
    for (int stage = 0; stage <= N; ++stage) {
        double x[@@NX@@] = {0.0};
        ocp_qp_out_get(out, stage, "x", x);
        for (int coordinate = 0; coordinate < nx_value; ++coordinate)
            printf("x%d_%d=%.17g\n", stage, coordinate, x[coordinate]);
        if (stage < N) {
            double u[1] = {0.0};
            ocp_qp_out_get(out, stage, "u", u);
            printf("u%d=%.17g\n", stage, u[0]);
        }
    }
    double xN[@@NX@@] = {0.0};
    ocp_qp_out_get(out, N, "x", xN);
    double variable_objective = 0.0;
    for (int i = 0; i < nx_value; ++i) {
        variable_objective += qterminal[i] * xN[i];
        for (int j = 0; j < nx_value; ++j) variable_objective += 0.5 * xN[i] * Qterminal[i * nx_value + j] * xN[j];
    }
    printf("variable_objective=%.17g\n", variable_objective);
    printf("squared_objective_offset=%.17g\n", (double)(@@OFFSET@@));
    printf("res_stationarity=%.17g\nres_dynamics=%.17g\nres_inequality=%.17g\nres_complementarity=%.17g\n",
        residual[0], residual[1], residual[2], residual[3]);
    return status == ACADOS_SUCCESS ? 0 : 1;
}
'''
replacements_c = {
    "@@N@@": str(horizon), "@@NX@@": str(n),
    "@@A_COL@@": array(matrix_col_major(case["dynamics"]["A_row_major"], n, n)),
    "@@B@@": array(case["dynamics"]["B"]), "@@AFFINE@@": array(case["dynamics"]["affine"]),
    "@@QSTAGE@@": ", ".join(["0.0"] * (n*n)), "@@SSTAGE@@": ", ".join(["0.0"] * n),
    "@@QSTAGE_LINEAR@@": ", ".join(["0.0"] * n), "@@INITIAL@@": array(case["initial_state"]),
    "@@FLOW_COORDS@@": ", ".join(str(row["coordinate"]) for row in case["state_bounds_each_stage"]),
    "@@FLOW_LOWER@@": array([row["lower"] for row in case["state_bounds_each_stage"]]),
    "@@FLOW_UPPER@@": array([row["upper"] for row in case["state_bounds_each_stage"]]),
    "@@CONTROL_LOWER@@": ", ".join([cdouble(case["control_bounds_each_stage"]["lower"])] * horizon),
    "@@CONTROL_UPPER@@": ", ".join([cdouble(case["control_bounds_each_stage"]["upper"])] * horizon),
    "@@QTERMINAL@@": array(matrix_col_major([str(value) for value in Qterminal_flat], n, n)),
    "@@QTERMINAL_LINEAR@@": array(qterminal), "@@CASE@@": case["case_id"], "@@OFFSET@@": cdouble(terminal_offset),
}
for token, value in replacements_c.items():
    source_c = source_c.replace(token, value)
if "@@" in source_c:
    raise SystemExit("Unresolved placeholder in generated acados source")
(ROOT / "generated_b04_ocp_qp.c").write_text(source_c, encoding="ascii", newline="\n")

source_cpp = r'''#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/registry.hpp>
#include <csl/execution/contracts.hpp>
#include <csl/core/outcomes.hpp>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <vector>

int main() {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    using namespace csl::adapters::convex;
    const double V[] = {@@V@@};
    const double y[] = {@@Y@@};
    ConvexProgramInput input;
    input.identity = {ProblemId{"@@CASE@@"}, ProgramId{"terminal-plane-squared"}};
    input.objective = QuadraticTerminal{Matrix{2, 2, {@@Q@@}}, {@@LINEAR@@}, @@OFFSET@@};
    input.constraints = SparseMatrix{0, 2, {0}, {}, {}};
    input.variables = std::vector<Interval>(2, Interval{});
    const auto made = make_convex_program(input);
    const auto *program = std::get_if<ConvexProgram>(&made);
    if (!program) { std::cerr << "make_convex_program failed\n"; return 2; }
    Registry<ConvexPort> registry;
    const auto registration_result = make_highs_registration();
    const auto *registration = std::get_if<Registration<ConvexPort>>(&registration_result);
    if (!registration) { std::cerr << "HiGHS registration failed\n"; return 3; }
    const auto registration_rejection = registry.add(*registration);
    if (registration_rejection) { std::cerr << "HiGHS registration rejected\n"; return 4; }
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    const auto selection = select(registry, Method{ModuleId{"csl.convex.highs"}, std::nullopt}, *program, requirements);
    const auto prepared_result = prepare_pipeline(selection);
    auto *prepared = std::get_if<PreparedPipeline<ConvexPort>>(&prepared_result);
    if (!prepared) { std::cerr << "HiGHS pipeline preparation rejected\n"; return 5; }
    auto [workspace] = prepared->create();
    ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {}, {}, {1e-8, 1e-8}, "b04-reference-v1-terminal-plane"};
    const auto outcome = workspace->run(context);
    const auto *result = std::get_if<ProgramResult>(&outcome);
    if (!result || !result->primal) { std::cerr << "HiGHS returned no primal result\n"; return 6; }
    const auto termination = result->termination == Termination::completed ? "completed" : "other";
    const auto status = result->outcome.value == MathematicalOutcome::optimal ? "optimal" : "other";
    std::cout << std::setprecision(17) << "case=@@CASE@@\ntermination=" << termination << "\noutcome=" << status << "\n";
    for (std::size_t i = 0; i < result->primal->size(); ++i) std::cout << "x" << i << "=" << result->primal->at(i) << "\n";
    double squared_norm = 0.0;
    for (int row = 0; row < @@WROWS@@; ++row) {
        double residual = y[row];
        for (int col = 0; col < 2; ++col) residual += V[row * 2 + col] * result->primal->at(static_cast<std::size_t>(col));
        squared_norm += residual * residual;
    }
    std::cout << "certified_squared_value=" << 0.5 * squared_norm << "\n";
    std::cout << "converted_norm=" << std::sqrt(2.0 * (0.5 * squared_norm)) << "\n";
    if (result->residuals.primal) {
        std::cout << "primal_rows_violation=" << result->residuals.primal->rows.violation << "\n";
        std::cout << "primal_variables_violation=" << result->residuals.primal->variables.violation << "\n";
    }
    if (result->residuals.dual) {
        if (result->residuals.dual->stationarity) std::cout << "dual_stationarity_violation=" << result->residuals.dual->stationarity->violation << "\n";
        if (result->residuals.dual->signs) std::cout << "dual_signs_violation=" << result->residuals.dual->signs->violation << "\n";
        if (result->residuals.dual->complementarity) std::cout << "dual_complementarity_violation=" << result->residuals.dual->complementarity->violation << "\n";
    }
    std::cout << "raw_diagnostics_begin\n" << result->raw_diagnostics << "\nraw_diagnostics_end\n";
    return result->termination == Termination::completed && result->outcome.value == MathematicalOutcome::optimal ? 0 : 7;
}
'''
replacements_cpp = {
    "@@CASE@@": case["case_id"], "@@Q@@": array(Qmoments_flat),
    "@@LINEAR@@": array(qmoments), "@@OFFSET@@": cdouble(moment_offset),
    "@@WROWS@@": str(len(W)), "@@V@@": array([value for row in V for value in row]),
    "@@Y@@": array(y),
}
for token, value in replacements_cpp.items():
    source_cpp = source_cpp.replace(token, value)
if "@@" in source_cpp:
    raise SystemExit("Unresolved placeholder in generated HiGHS source")
(ROOT / "generated_b04_highs_qp.cpp").write_text(source_cpp, encoding="ascii", newline="\n")
print("Generated acados and project-HiGHS model inputs from canonical-case.json; solver execution was not performed.")
