#include <csl/optimization/finite_action_minimax.hpp>

#include <cmath>
#include <limits>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string explanation,
                        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{{code, std::move(field), std::move(explanation)}}};
}
bool empty_set(const sets::SetData& set) {
    const auto rep=set.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep)) return true;
    if(const auto* v=std::get_if<sets::VRepresentation>(&rep))
        return v->vertices.rows()==0 && v->rays.rows()==0;
    return false;
}
}

FiniteActionMinimaxOutcome finite_action_minimax(
    const FiniteActionMinimaxRequest& request,
    FiniteActionMinimaxLimits limits,
    const ExecutionContext& context) {
    const auto horizon=request.system.horizon();
    const auto dimensions=request.system.dimensions();
    if(request.problem.value.empty() || request.request.value.empty())
        return unsupported("finite_minimax.identity", "Nonempty problem and request identities are required.",
                           DiagnosticCode::invalid_input);
    if(!std::isfinite(limits.near_optimal_tolerance) || limits.near_optimal_tolerance<0)
        return unsupported("finite_minimax.tolerance", "Near-optimal tolerance must be finite and nonnegative.",
                           DiagnosticCode::invalid_input);
    if(request.actions.dimension!=dimensions.control ||
       request.disturbances.size()!=horizon || request.admissible_states.size()!=horizon+1 ||
       request.objective.dimension()!=dimensions.state)
        return unsupported("finite_minimax.dimension", "Action, stage, or objective dimensions differ from the model.",
                           DiagnosticCode::invalid_input);
    for(const auto& action:request.actions.catalogue) {
        if(action.size()!=dimensions.control)
            return unsupported("finite_minimax.action", "Action row has the wrong dimension.",DiagnosticCode::invalid_input);
        for(const auto value:action)
            if(!std::isfinite(value))
                return unsupported("finite_minimax.action", "Action rows must be finite.",DiagnosticCode::invalid_input);
    }
    if(horizon && request.actions.catalogue.empty()) return FiniteMinimaxEmptyCatalogue{};
    std::size_t plan_count=1;
    for(std::size_t stage=0;stage<horizon;++stage) {
        if(plan_count>limits.max_plans/request.actions.catalogue.size())
            return unsupported("finite_minimax.capacity", "Action product exceeds the caller plan limit.");
        plan_count*=request.actions.catalogue.size();
    }
    if(plan_count>limits.max_plans)
        return unsupported("finite_minimax.capacity", "Action product exceeds the caller plan limit.");
    if(empty_set(request.initial)) return FiniteMinimaxNoScenarios{};
    for(const auto& disturbance:request.disturbances)
        if(empty_set(disturbance)) return FiniteMinimaxNoScenarios{};

    std::vector<FinitePlanRecord> records;
    records.reserve(plan_count);
    std::vector<std::size_t> choices(horizon);
    double minimum=std::numeric_limits<double>::infinity();
    for(std::size_t plan_index=0;plan_index<plan_count;++plan_index) {
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for(auto choice:choices) controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{
            request.system,request.initial,std::move(controls),request.disturbances,
            request.admissible_states,{request.request.value+"/plan/"+std::to_string(plan_index)}};
        const auto propagated=reachability::fixed_plan_disturbance(plan,limits.max_points_per_stage,context);
        if(const auto* error=std::get_if<Unsupported>(&propagated)) return *error;
        if(const auto* stop=std::get_if<OperationStopped>(&propagated)) return *stop;
        if(const auto* empty=std::get_if<reachability::FixedPlanEmpty>(&propagated)) {
            (void)empty;
            return FiniteMinimaxNoScenarios{};
        }
        if(const auto* violation=std::get_if<reachability::FixedPlanViolation>(&propagated))
            records.emplace_back(FinitePlanRejected{choices,violation->stage,violation->violating_successor});
        else {
            const auto& tube=std::get<reachability::FixedPlanReachable>(propagated);
            const auto& terminal=tube.stages.back();
            const auto worst=worst_case_vertex(terminal,request.objective,limits.max_points_per_stage,context);
            if(const auto* error=std::get_if<Unsupported>(&worst)) return *error;
            if(const auto* stop=std::get_if<OperationStopped>(&worst)) return *stop;
            if(std::holds_alternative<WorstCaseEmpty>(worst)) return FiniteMinimaxNoScenarios{};
            const auto& value=std::get<WorstCaseValue>(worst);
            if(value.value<minimum) minimum=value.value;
            records.emplace_back(FinitePlanFeasible{choices,value.value,value.maximizer,
                value.evaluated_vertices,terminal});
        }
        for(std::size_t stage=horizon;stage>0;--stage) {
            if(++choices[stage-1]<request.actions.catalogue.size()) break;
            choices[stage-1]=0;
        }
    }
    if(!std::isfinite(minimum)) {
        std::vector<FinitePlanRejected> rejected;
        rejected.reserve(records.size());
        for(auto& record:records) rejected.push_back(std::get<FinitePlanRejected>(std::move(record)));
        return FiniteMinimaxInfeasible{request.problem,request.request,std::move(rejected),Assurance::numerical};
    }
    std::vector<std::size_t> selected;
    for(std::size_t index=0;index<records.size();++index)
        if(const auto* feasible=std::get_if<FinitePlanFeasible>(&records[index]))
            if(static_cast<long double>(feasible->worst_value)-minimum<=limits.near_optimal_tolerance)
                selected.push_back(index);
    return FiniteMinimaxOptimal{request.problem,request.request,minimum,
        std::move(records),std::move(selected),Assurance::numerical};
}
} // namespace csl::optimization
