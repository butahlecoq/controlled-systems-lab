#include <csl/optimization/lp_backend.hpp>
#include <csl/registry/registry.hpp>
#include <iostream>
using namespace csl;
using namespace csl::optimization;
// Contract fixture that evaluates one candidate; it does not solve arbitrary LPs.
class CandidateWorkspace final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& context) override {
        const auto evaluation=evaluate_primal(p,Vector{0,1},context.numerical,{{"installed-check"},"1"});
        if(const auto* diagnostics=std::get_if<Diagnostics>(&evaluation)) return Unsupported{*diagnostics};
        const auto& value=std::get<PrimalEvaluation>(evaluation);
        return ProgramResult{Termination::resource_limit,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            Vector{0,1},{},std::to_string(value.objective),{value.residuals,{}}};
    }
};
int main() {
    LinearProgramInput input{{{"p"},{"offset-triangle"}},{-1,-2},7,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}};
    auto created=make_linear_program(input);
    if(!std::holds_alternative<LinearProgram>(created)) return 1;
    auto p=std::get<LinearProgram>(created);
    input.objective[0]=100; input.rows[0].upper=-100;
    const auto evaluation=evaluate_primal(p,Vector{0,1},{1e-9,1e-9},{{"installed-check"},"1"});
    if(!std::holds_alternative<PrimalEvaluation>(evaluation)) return 2;
    const auto& v=std::get<PrimalEvaluation>(evaluation);
    if(v.objective!=5 || v.residuals.rows.violation!=0 || v.residuals.variables.violation!=0) return 3;
    registry::Registry<registry::LPPort> registry;
    registry.add({{{"candidate"},"1"},[](const LinearProgram&,const registry::Requirements&)->registry::Capability {return registry::Offer{};},
        [](const LinearProgram&){return std::make_unique<CandidateWorkspace>();}});
    auto prepared=registry::prepare_pipeline(registry::select(registry,registry::Method{{"candidate"},{}},p));
    if(!std::holds_alternative<registry::PreparedPipeline<registry::LPPort>>(prepared)) return 4;
    auto plan=std::get<registry::PreparedPipeline<registry::LPPort>>(prepared);
    auto first=plan.create(),second=plan.create(); auto& a=*std::get<0>(first); auto& b=*std::get<0>(second);
    ExecutionContext context{{},{},{},{1e-9,1e-9},"installed"};
    const auto outcome=a.run(context); b.run(context);
    if(a.workspace_identity()==b.workspace_identity() || !a.last_attempt() || a.last_attempt()->stamp.attempt()!=1 || a.basis()!=nullptr) return 5;
    if(!std::holds_alternative<ProgramResult>(outcome)) return 6;
    const auto& result=std::get<ProgramResult>(outcome);
    if(!check_program_result(result,p,Assurance::numerical).empty() || result.raw_diagnostics!="5.000000" ||
        result.outcome.value!=MathematicalOutcome::undetermined || result.objective.lower || result.objective.upper) return 7;
    registry::Requirements basis; basis.basis_diagnostics=true;
    auto unavailable=registry::prepare_pipeline(registry::select(registry,registry::Method{{"candidate"},{}},p,basis));
    if(!std::holds_alternative<registry::Rejection>(unavailable)) return 8;
    std::cout << "Installed optimization client: immutable program, literal checks and exclusive attempts passed\n";
}
