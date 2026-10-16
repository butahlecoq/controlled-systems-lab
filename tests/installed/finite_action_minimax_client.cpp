#include <csl/optimization/finite_action_minimax_port.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,1,{1}},{0}}},{}};
    const auto system=std::get<model::LinearSystem>(model::snapshot(authored,Vector{0}));
    const auto initial=std::get<sets::SetData>(sets::make_singleton({{"installed-x0"},1,{"x"}},
        std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{0}))));
    const auto safe=std::get<sets::SetData>(sets::make_universal({{"installed-safe"},1,{"x"}}));
    const auto objective=std::get<Objective>(snapshot(QuadraticTerminal{{1,1,{2}},{-2},1}));
    const FiniteActionMinimaxQuery query{{{"installed-problem"},{"installed-run"},system,initial,
        {1,{}},{},{safe},objective},{1,1,0}};
    Registry<FiniteActionMinimaxPort> entries;
    if(entries.add(make_finite_action_minimax_registration()))return 1;
    auto selected=prepare_pipeline(select(entries,
        Method{{"csl.optimization.finite-action-minimax"},"1.0.0"},
        query,finite_action_minimax_requirements()));
    if(!std::holds_alternative<PreparedPipeline<FiniteActionMinimaxPort>>(selected))return 2;
    auto prepared=std::get<PreparedPipeline<FiniteActionMinimaxPort>>(std::move(selected));
    const auto provider=prepared.provenance()[0];
    if(provider.port!="finite-action-minimax" ||
        provider.requested.id!=ModuleId{"csl.optimization.finite-action-minimax"} ||
        provider.requested.version!=std::optional<std::string>{"1.0.0"} ||
        !provider.actual || provider.actual->version!="1.0.0")return 3;
    auto workspace=std::get<0>(prepared.create());
    const auto result=workspace->run({});
    if(!std::holds_alternative<FiniteMinimaxOptimal>(result))return 4;
    const auto& optimal=std::get<FiniteMinimaxOptimal>(result);
    if(optimal.problem!=ProblemId{"installed-problem"} ||
        optimal.request!=RequestId{"installed-run"} ||
        optimal.value!=1 || optimal.assurance!=Assurance::numerical ||
        optimal.minimizing_plan_indices!=std::vector<std::size_t>{0} ||
        optimal.plans.size()!=1 ||
        !std::holds_alternative<FinitePlanFeasible>(optimal.plans[0]))return 5;
    std::cout<<"Installed finite minimax client: registered scalar and provenance passed\n";
}
