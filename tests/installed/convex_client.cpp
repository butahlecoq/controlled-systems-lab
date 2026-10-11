#include <csl/adapters/convex/highs.hpp>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
template<class T,class... R> T accepted(std::variant<T,R...> result) {
    if(!std::holds_alternative<T>(result)) throw std::runtime_error("convex consumer boundary rejected");
    return std::get<T>(std::move(result));
}
int main() {
    try {
        const auto p=accepted(make_convex_program({{{"installed"},{"original-norm"}},
            ResidualNormTerminal{{2,1,{1,0}},{3,-4}},{0,1,{0},{},{}},{{0,2}},{},ProgramId{"squared-norm"}}));
        Registry<ConvexPort> registry;
        if(registry.add(accepted(adapters::convex::make_highs_registration()))) return 1;
        Requirements req; req.output.representation={"csl.program-result.v1"};
        auto plan=accepted(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},p,req)));
        auto [worker]=plan.create();
        ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"installed"};
        auto r=accepted(worker->run(context));
        if(r.termination!=Termination::completed || r.outcome.value!=MathematicalOutcome::optimal || !r.primal ||
            std::abs((*r.primal)[0]-2)>1e-9 || !r.residuals.dual || !r.residuals.dual->complementarity ||
            r.objective.lower || r.objective.upper || !check_program_result(r,p,Assurance::numerical).empty()) return 2;
        const auto e=accepted(evaluate_primal(p,*r.primal,{1e-8,1e-8},{{"installed.literal"},"1"}));
        if(std::abs(e.original_objective-std::sqrt(17.0))>1e-9 || std::abs(e.solver_objective-17)>1e-9 ||
            p.identity()==p.quadratic_program().identity()) return 3;
        // An authored explicit-zero row must survive the same native invariant
        // boundary, including a nonzero feasibility-start/private-row activity.
        const auto zero=accepted(make_convex_program({{{"installed"},{"zero-row-original-norm"}},
            ResidualNormTerminal{{2,1,{1,0}},{3,-4}},{1,1,{0,1},{0},{0}},{{1,2}},{{0,0}},ProgramId{"zero-row-squared-norm"}}));
        auto zero_plan=accepted(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},zero,req)));
        auto [zero_worker]=zero_plan.create();const auto zero_result=accepted(zero_worker->run(context));
        if(zero_result.termination!=Termination::completed || zero_result.outcome.value!=MathematicalOutcome::optimal ||
            !zero_result.primal || std::abs((*zero_result.primal)[0]-2)>1e-9 || !zero_result.residuals.dual ||
            zero_result.outcome.subject!=zero.identity() || zero_result.objective.lower || zero_result.objective.upper ||
            !check_program_result(zero_result,zero,Assurance::numerical).empty()) return 5;
        const auto zero_cost=accepted(evaluate_primal(zero,*zero_result.primal,{1e-8,1e-8},{{"installed.literal"},"1"}));
        if(std::abs(zero_cost.original_objective-std::sqrt(17.0))>1e-9 || std::abs(zero_cost.solver_objective-17)>1e-9 ||
            zero.quadratic_program().rows().size()!=1 || zero_cost.residuals.rows.violation!=0) return 6;
        std::cout<<"Installed convex client: original norm, squared provenance and numerical KKT passed\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 4;}
}
