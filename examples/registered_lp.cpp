#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    if (argc > 2) { std::cerr << "Usage: registered_lp [backend-id]\n"; return 2; }
    const std::string backend = argc == 2 ? argv[1] : "csl.lp.highs";

    // min -x-2y+7, x,y >= 0, x+y <= 1. The literal optimum is (0,1), cost 5.
    const auto program = std::get<LinearProgram>(make_linear_program({
        {{"example.triangle"}, {"lp"}}, {-1, -2}, 7,
        {1, 2, {0, 2}, {0, 1}, {1, 1}}, {{0, {}}, {0, {}}}, {{{}, 1}}}));
    Registry<LPPort> registry;
    auto entry = std::get<Registration<LPPort>>(adapters::lp::make_highs_registration());
    if (registry.add(std::move(entry))) throw std::runtime_error("LP registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto preparation = prepare_pipeline(select(registry, {{backend}, {}}, program, requirements));
    if (const auto* rejected = std::get_if<Rejection>(&preparation)) {
        std::cerr << "Selection rejected: " << rejected->provenance.requested.id.value << '\n';
        for (const auto& d : rejected->diagnostics)
            std::cerr << "DiagnosticCode=" << static_cast<int>(d.code) << " " << d.field << ": " << d.explanation << '\n';
        return 2;
    }
    const auto& prepared = std::get<PreparedPipeline<LPPort>>(preparation);
    auto [workspace] = prepared.create();
    const auto outcome = workspace->run({{}, {}, {}, {1e-8, 1e-8}, "triangle"});
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("LP did not return the expected completed optimal result");
    const auto check = std::get<PrimalEvaluation>(evaluate_primal(
        program, *result->primal, {1e-8, 1e-8}, {{"example.original-rows"}, "1"}));
    if (result->primal->size() != 2 || std::abs((*result->primal)[0]) > 1e-8 ||
        std::abs((*result->primal)[1] - 1) > 1e-8 || std::abs(check.objective - 5) > 1e-8 ||
        check.residuals.rows.violation > 1e-8 || check.residuals.variables.violation > 1e-8 ||
        !std::holds_alternative<Unestablished>(result->outcome.support) || result->objective.lower || result->objective.upper)
        throw std::runtime_error("Independent triangle oracle or evidence scope differs");
    const auto actual = prepared.provenance()[0].actual.value();
    std::cout << "backend=" << actual.id.value << " version=" << actual.version << '\n'
              << "x=" << (*result->primal)[0] << " y=" << (*result->primal)[1] << " original_cost=" << check.objective << '\n'
              << "termination=completed outcome=optimal evidence=unestablished\n"
              << "row_violation=" << check.residuals.rows.violation
              << " variable_violation=" << check.residuals.variables.violation
              << " tolerance_abs=1e-8 tolerance_rel=1e-8\n"
              << "No certified bounds or optimal-family result.\n";
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
