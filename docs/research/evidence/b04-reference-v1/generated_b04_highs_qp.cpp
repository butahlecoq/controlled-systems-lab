#include <csl/adapters/convex/highs.hpp>
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
    const double V[] = {17, 0, 0, -106.25, -32, 0, 0, 200, 0, -306.25};
    const double y[] = {16.904, -2190.4000000000001, -29.901333333333334, 3790.1333333333332, -5980.5333333333338};
    ConvexProgramInput input;
    input.identity = {ProblemId{"b04-reference-v1"}, ProgramId{"terminal-plane-squared"}};
    input.objective = QuadraticTerminal{Matrix{2, 2, {1313, 0, 0, 145078.125}}, {1244.2106666666666, 2822295}, 27465460.815253332};
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
    std::cout << std::setprecision(17) << "case=b04-reference-v1\ntermination=" << termination << "\noutcome=" << status << "\n";
    for (std::size_t i = 0; i < result->primal->size(); ++i) std::cout << "x" << i << "=" << result->primal->at(i) << "\n";
    double squared_norm = 0.0;
    for (int row = 0; row < 5; ++row) {
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
