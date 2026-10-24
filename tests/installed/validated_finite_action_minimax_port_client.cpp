#include <csl/optimization/validated_finite_action_minimax_port.hpp>

#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}}, {}};
    const auto system=std::get<model::LinearSystem>(model::snapshot(authored,Vector{0}));
    const auto initial=std::get<sets::SetData>(sets::make_singleton({{"installed-x0"},1,{"x"}},
        std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{0}))));
    const auto safe=std::get<sets::SetData>(sets::make_universal({{"installed-all"},1,{"x"}}));
    auto objective=optimization::snapshot(LinearTerminal{{1},0});
    if(!std::holds_alternative<optimization::Objective>(objective)) return 1;
    ValidatedFiniteActionMinimaxRequest request{{"installed-problem"},{"installed-run"},
        system,initial,{1,{}},{},{safe},std::get<optimization::Objective>(std::move(objective))};
    ValidatedFiniteActionMinimaxQuery query{std::move(request),{1,1,100}};
    Registry<ValidatedFiniteActionMinimaxPort> registry;
    if(registry.add(make_validated_finite_action_minimax_registration())) return 2;
    const Method method{{"csl.optimization.validated-finite-action-minimax"},"1.0.0"};
    auto selected=prepare_pipeline(select(registry,method,query,
        validated_finite_action_minimax_requirements()));
    if(!std::holds_alternative<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(selected)) return 3;
    auto prepared=std::get<PreparedPipeline<ValidatedFiniteActionMinimaxPort>>(std::move(selected));
    auto workspace=std::get<0>(prepared.create());
    const auto outcome=workspace->run({});
    const auto* bounds=std::get_if<ValidatedMinimaxBounds>(&outcome);
    if(!bounds || bounds->problem()!=ProblemId{"installed-problem"} ||
       bounds->request()!=RequestId{"installed-run"} || bounds->lower()!=0 || bounds->upper()!=0) return 4;
    std::cout << "Installed validated minimax port client: selected validated bounds passed\n";
}
