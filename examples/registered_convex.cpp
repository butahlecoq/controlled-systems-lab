#include <csl/adapters/convex/highs.hpp>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    if (argc > 2) { std::cerr << "Usage: registered_convex [backend-id]\n"; return 2; }
    const std::string backend = argc == 2 ? argv[1] : "csl.convex.highs";

    // Original cost ||(x-3,4)||, 0 <= x <= 2. The adapter solves its squared form.
    const auto program = std::get<ConvexProgram>(make_convex_program({
        {{"example.norm"}, {"original"}}, ResidualNormTerminal{{2, 1, {1, 0}}, {3, -4}},
        {0, 1, {0}, {}, {}}, {{0, 2}}, {}, ProgramId{"squared"}}));
    Registry<ConvexPort> registry;
    auto entry = std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration());
    if (registry.add(std::move(entry))) throw std::runtime_error("Convex registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto preparation = prepare_pipeline(select(registry, {{backend}, {}}, program, requirements));
    if (const auto* rejected = std::get_if<Rejection>(&preparation)) {
        std::cerr << "Selection rejected: " << rejected->provenance.requested.id.value << '\n';
        for (const auto& d : rejected->diagnostics)
            std::cerr << "DiagnosticCode=" << static_cast<int>(d.code) << " " << d.field << ": " << d.explanation << '\n';
        return 2;
    }
    const auto& prepared = std::get<PreparedPipeline<ConvexPort>>(preparation);
    auto [workspace] = prepared.create();
    const auto resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    const auto outcome = workspace->run({resources, {}, {}, {1e-8, 1e-8}, "original-norm"});
    if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        for (const auto& d : unsupported->diagnostics)
            std::cerr << d.field << ": " << d.explanation << '\n';
        return 1;
    }
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("Convex solve did not return the expected completed optimal result");
    const auto check = std::get<ConvexPrimalEvaluation>(evaluate_primal(
        program, *result->primal, {1e-8, 1e-8}, {{"example.original-cost"}, "1"}));
    if (result->primal->size() != 1 || std::abs((*result->primal)[0] - 2) > 1e-8 ||
        std::abs(check.original_objective - std::sqrt(17.0)) > 1e-8 ||
        std::abs(check.solver_objective - 17) > 1e-8 || check.residuals.rows.violation > 1e-8 ||
        check.residuals.variables.violation > 1e-8 || result->objective.lower || result->objective.upper ||
        !std::holds_alternative<Unestablished>(result->outcome.support))
        throw std::runtime_error("Independent norm oracle or evidence scope differs");
    const auto actual = prepared.provenance()[0].actual.value();
    std::cout << std::setprecision(10) << "backend=" << actual.id.value << " version=" << actual.version << '\n'
              << "x=" << (*result->primal)[0] << " original_cost=" << check.original_objective
              << " squared_cost=" << check.solver_objective << '\n'
              << "original_program=" << program.identity().program.value
              << " solver_program=" << program.quadratic_program().identity().program.value << '\n'
              << "termination=completed outcome=optimal evidence=unestablished\n"
              << "No certified bounds or optimal-family result.\n";
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
