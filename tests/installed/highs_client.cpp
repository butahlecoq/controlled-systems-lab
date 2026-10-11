#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/objectives.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::registry;
    using namespace csl::optimization;
    auto data = make_linear_program({{{"installed"},{"offset-triangle"}}, {-1,-2},7,
        {1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}});
    const auto* program = std::get_if<LinearProgram>(&data);
    if (!program) return 1;
    auto registration = adapters::lp::make_highs_registration();
    auto* entry = std::get_if<Registration<LPPort>>(&registration);
    if (!entry) return 2;
    Registry<LPPort> registry;
    if (registry.add(std::move(*entry))) return 3;
    Requirements request;
    request.output.representation = {"csl.program-result.v1"};
    auto preparation = prepare_pipeline(select(registry,{{"csl.lp.highs"},{}},*program,request));
    auto* prepared = std::get_if<PreparedPipeline<LPPort>>(&preparation);
    if (!prepared || prepared->provenance()[0].actual->version != "1.0.0+highs.1.11.0") return 4;
    auto [worker] = prepared->create();
    if (worker->basis()) return 5;
    const auto outcome = worker->run({{}, {}, {}, {1e-8,1e-8}, "installed"});
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed || result->outcome.value != MathematicalOutcome::optimal ||
        !result->primal || *result->primal != Vector{0,1} || !std::holds_alternative<Unestablished>(result->outcome.support) ||
        result->objective.lower || result->objective.upper || !check_program_result(*result,*program,Assurance::numerical).empty()) return 6;
    const auto evaluated = evaluate_primal(*program,*result->primal,{1e-8,1e-8},{{"installed.oracle"},"1"});
    const auto* value = std::get_if<PrimalEvaluation>(&evaluated);
    if (!value || value->objective != 5 || value->residuals.rows.violation != 0 || value->residuals.variables.violation != 0) return 7;
    if (!result->residuals.primal || !result->residuals.dual ||
        result->residuals.primal->context.subject != program->identity() ||
        result->raw_diagnostics.find("native.version=1.11.0") == std::string::npos ||
        result->raw_diagnostics.find("Model status") == std::string::npos) return 8;
    std::cout << "Installed HiGHS client: registered offset optimum and neutral evidence passed\n";
}
