#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/phase_one.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    if (argc != 2) {
        std::cerr << "Usage: backend_substitution csl.lp.highs|phase-one-bland\n";
        return 2;
    }
    // Both real backends support this exact LP: u0+u1=1, u>=0, objective zero.
    const auto program = std::get<LinearProgram>(phase_one::make_program(
        {{"example.common-feasibility"}, {"lp"}}, {1, 2, {0, 2}, {0, 1}, {1, 1}}, Vector{1}));
    Registry<LPPort> registry;
    auto highs = std::get<Registration<LPPort>>(adapters::lp::make_highs_registration());
    auto bland = std::get<Registration<LPPort>>(phase_one::make_registration());
    if (registry.add(std::move(highs)) || registry.add(std::move(bland)))
        throw std::runtime_error("Backend registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    // Only the ID varies: program, port, preparation, execution and checks are shared.
    auto preparation = prepare_pipeline(select(registry, {{argv[1]}, {}}, program, requirements));
    if (const auto* rejected = std::get_if<Rejection>(&preparation)) {
        std::cerr << "Selection rejected: " << rejected->provenance.requested.id.value << '\n';
        for (const auto& d : rejected->diagnostics)
            std::cerr << "DiagnosticCode=" << static_cast<int>(d.code) << " " << d.field << ": " << d.explanation << '\n';
        return 2;
    }
    const auto& prepared = std::get<PreparedPipeline<LPPort>>(preparation);
    auto [workspace] = prepared.create();
    const auto outcome = workspace->run({{}, {}, {}, {1e-8, 1e-8}, "substitution"});
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("Backend did not return a completed feasible zero-objective result");
    const auto& u = *result->primal;
    const auto check = std::get<PrimalEvaluation>(evaluate_primal(
        program, u, {1e-8, 1e-8}, {{"example.common-original-rows"}, "1"}));
    // Accept any feasible witness, without assuming a particular basis or endpoint.
    if (u.size() != 2 || u[0] < -1e-8 || u[1] < -1e-8 || std::abs(u[0] + u[1] - 1) > 1e-8 ||
        check.objective != 0 || check.residuals.rows.violation > 1e-8 || check.residuals.variables.violation > 1e-8 ||
        !std::holds_alternative<Unestablished>(result->outcome.support) || result->objective.lower || result->objective.upper)
        throw std::runtime_error("Independent common feasibility oracle or evidence scope differs");
    const auto actual = prepared.provenance()[0].actual.value();
    std::cout << "backend=" << actual.id.value << " version=" << actual.version << '\n'
              << "u0=" << u[0] << " u1=" << u[1] << " sum=" << u[0] + u[1] << " original_cost=" << check.objective << '\n'
              << "termination=completed outcome=optimal evidence=unestablished\n"
              << "Scope: zero-objective equality/nonnegative feasibility only.\n"
              << "Phase I is not a second general optimizer or control-synthesis strategy.\n";
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
