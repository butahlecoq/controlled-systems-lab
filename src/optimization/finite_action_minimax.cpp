#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/execution/timing_collector.hpp>
#include "finite_action_plans.hpp"
#include <algorithm>

#include <cmath>
#include <limits>
#include <optional>
#include <stdexcept>

namespace csl::optimization {
namespace {
namespace ob = execution::observability;
Unsupported unsupported(std::string field, std::string explanation,
                        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{{code, std::move(field), std::move(explanation)}}};
}
Termination stopped_termination(StopReason reason) {
    switch(reason) {
    case StopReason::cancelled:return Termination::cancelled;
    case StopReason::deadline_expired:return Termination::deadline_expired;
    case StopReason::resource_limit:return Termination::resource_limit;
    case StopReason::numerical_failure:return Termination::numerical_failure;
    }
    return Termination::numerical_failure;
}
class FinalizeUnstartedPhases;
class PlannedPhase {
    std::optional<ob::TimingScope> scope_;
    Termination termination_{Termination::operation_rejected};
public:
    PlannedPhase(const ExecutionContext& context,std::optional<artifacts::SpanId> id,
        FinalizeUnstartedPhases* finalizer=nullptr);
    ~PlannedPhase()=default;
    void close(Termination termination) noexcept {
        termination_=termination;
        if(scope_){scope_->close(termination_);scope_.reset();}
    }
    PlannedPhase(const PlannedPhase&)=delete;
    PlannedPhase& operator=(const PlannedPhase&)=delete;
};
class FinalizeUnstartedPhases {
    const ExecutionContext& context_;
    const FiniteMinimaxTimingSpans* spans_;
    std::vector<unsigned char> started_;
    void close_if_unstarted(artifacts::SpanId id) noexcept {
        if(id.value<started_.size() && started_[id.value])return;
        auto started=ob::start_timing(context_,id);
        if(auto* scope=std::get_if<ob::TimingScope>(&started))
            scope->close_not_called(artifacts::NotCalledReason::earlier_phase_exit,Termination::completed);
    }
public:
    FinalizeUnstartedPhases(const ExecutionContext& context,const FiniteMinimaxTimingSpans* spans)
        :context_(context),spans_(spans),started_(spans?spans->result_selection.value+1:0,0){}
    void mark_started(artifacts::SpanId id) {if(id.value<started_.size())started_[id.value]=1;}
    ~FinalizeUnstartedPhases() {
        if(!spans_)return;
        close_if_unstarted(spans_->validation);
        for(const auto& plan:spans_->plans) {
            close_if_unstarted(plan.plan_setup);
            if(plan.propagation.value>=started_.size() || !started_[plan.propagation.value]) {
                auto parent=ob::start_timing(context_,plan.propagation);
                if(auto* scope=std::get_if<ob::TimingScope>(&parent)) {
                    for(const auto id:plan.stage_materialization) {
                        auto child=ob::start_timing(context_,id);
                        if(auto* child_scope=std::get_if<ob::TimingScope>(&child))
                            child_scope->close_not_called(artifacts::NotCalledReason::earlier_phase_exit,
                                Termination::completed);
                    }
                    scope->close_not_called(artifacts::NotCalledReason::earlier_phase_exit,
                        Termination::completed);
                }
            }
            close_if_unstarted(plan.objective);
            close_if_unstarted(plan.record_assembly);
        }
        close_if_unstarted(spans_->result_selection);
    }
    FinalizeUnstartedPhases(const FinalizeUnstartedPhases&)=delete;
    FinalizeUnstartedPhases& operator=(const FinalizeUnstartedPhases&)=delete;
};
PlannedPhase::PlannedPhase(const ExecutionContext& context,std::optional<artifacts::SpanId> id,
    FinalizeUnstartedPhases* finalizer) {
    if(!id)return;
    auto started=ob::start_timing(context,*id);
    if(auto* scope=std::get_if<ob::TimingScope>(&started)) {
        scope_.emplace(std::move(*scope));
        if(finalizer)finalizer->mark_started(*id);
    } else if(const auto* error=std::get_if<artifacts::ArtifactError>(&started)) {
        throw std::runtime_error(error->path+": "+error->message);
    }
}
Termination propagation_termination(const reachability::FixedPlanOutcome& outcome) {
    if(std::holds_alternative<Unsupported>(outcome))return Termination::operation_rejected;
    if(const auto* stop=std::get_if<OperationStopped>(&outcome))return stopped_termination(stop->reason);
    return Termination::completed;
}
Termination objective_termination(const WorstCaseVertexOutcome& outcome) {
    if(std::holds_alternative<Unsupported>(outcome))return Termination::operation_rejected;
    if(const auto* stop=std::get_if<OperationStopped>(&outcome))return stopped_termination(stop->reason);
    return Termination::completed;
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
    const ExecutionContext& context,
    const FiniteMinimaxTimingSpans* timing_spans) {
    if(timing_spans&&context.timing) {
        std::vector<artifacts::SpanId> ids{timing_spans->validation,timing_spans->result_selection};
        for(const auto& plan:timing_spans->plans) {
            ids.push_back(plan.plan_setup);ids.push_back(plan.propagation);
            ids.insert(ids.end(),plan.stage_materialization.begin(),plan.stage_materialization.end());
            ids.push_back(plan.objective);ids.push_back(plan.record_assembly);
        }
        const auto valid=context.timing->validate_unstarted(ids);
        if(const auto* failure=std::get_if<artifacts::ArtifactError>(&valid))
            return unsupported("finite_minimax.timing_spans",failure->message,DiagnosticCode::invalid_input);
    }
    FinalizeUnstartedPhases finalize{context,timing_spans};
    PlannedPhase validation{context,timing_spans?std::optional{timing_spans->validation}:std::nullopt,&finalize};
    auto reject_validation=[&validation](Unsupported result) {
        validation.close(Termination::operation_rejected);
        return FiniteActionMinimaxOutcome{std::move(result)};
    };
    const auto horizon=request.system.horizon();
    const auto dimensions=request.system.dimensions();
    if(request.problem.value.empty() || request.request.value.empty())
        return reject_validation(unsupported("finite_minimax.identity", "Nonempty problem and request identities are required.",
                           DiagnosticCode::invalid_input));
    if(!std::isfinite(limits.near_optimal_tolerance) || limits.near_optimal_tolerance<0)
        return reject_validation(unsupported("finite_minimax.tolerance", "Near-optimal tolerance must be finite and nonnegative.",
                           DiagnosticCode::invalid_input));
    if(request.actions.dimension!=dimensions.control ||
       request.disturbances.size()!=horizon || request.admissible_states.size()!=horizon+1 ||
       request.objective.dimension()!=dimensions.state)
        return reject_validation(unsupported("finite_minimax.dimension", "Action, stage, or objective dimensions differ from the model.",
                           DiagnosticCode::invalid_input));
    for(const auto& action:request.actions.catalogue) {
        if(action.size()!=dimensions.control)
            return reject_validation(unsupported("finite_minimax.action", "Action row has the wrong dimension.",DiagnosticCode::invalid_input));
        for(const auto value:action)
            if(!std::isfinite(value))
                return reject_validation(unsupported("finite_minimax.action", "Action rows must be finite.",DiagnosticCode::invalid_input));
    }
    if(horizon && request.actions.catalogue.empty()) return FiniteMinimaxEmptyCatalogue{};
    std::size_t plan_count=1;
    for(std::size_t stage=0;stage<horizon;++stage) {
        if(plan_count>limits.max_plans/request.actions.catalogue.size())
            return reject_validation(unsupported("finite_minimax.capacity", "Action product exceeds the caller plan limit."));
        plan_count*=request.actions.catalogue.size();
    }
    if(plan_count>limits.max_plans)
        return reject_validation(unsupported("finite_minimax.capacity", "Action product exceeds the caller plan limit."));
    if(timing_spans && (timing_spans->plans.size()!=plan_count ||
        std::any_of(timing_spans->plans.begin(),timing_spans->plans.end(),[horizon](const auto& plan) {
            return plan.stage_materialization.size()!=horizon;
        }))) {
        return reject_validation(unsupported("finite_minimax.timing_spans",
            "Timing span layout must contain one plan record and one stage materialization span per horizon stage."));
    }
    validation.close(Termination::completed);
    std::vector<FinitePlanRecord> records;
    records.reserve(plan_count);
    double minimum=std::numeric_limits<double>::infinity();
    for(std::size_t plan_index=0;plan_index<plan_count;++plan_index) {
        const auto choices=detail::action_plan_indices(plan_index,request.actions.catalogue.size(),horizon);
        const FiniteMinimaxPlanTimingSpans* spans=timing_spans&&plan_index<timing_spans->plans.size()?
            &timing_spans->plans[plan_index]:nullptr;
        PlannedPhase plan_setup{context,spans?std::optional{spans->plan_setup}:std::nullopt,&finalize};
        std::vector<Vector> controls;
        controls.reserve(horizon);
        for(auto choice:choices) controls.push_back(request.actions.catalogue[choice]);
        reachability::FixedPlanRequest plan{
            request.system,request.initial,std::move(controls),request.disturbances,
            request.admissible_states,{request.request.value+"/plan/"+std::to_string(plan_index)}};
        plan_setup.close(Termination::completed);
        PlannedPhase propagation_timing{context,spans?std::optional{spans->propagation}:std::nullopt,&finalize};
        reachability::FixedPlanTimingSpans reachability_spans;
        if(spans)reachability_spans.stage_materialization=spans->stage_materialization;
        const auto propagated=reachability::fixed_plan_disturbance(plan,limits.max_points_per_stage,context,
            spans?&reachability_spans:nullptr);
        propagation_timing.close(propagation_termination(propagated));
        if(const auto* error=std::get_if<Unsupported>(&propagated)) return *error;
        if(const auto* stop=std::get_if<OperationStopped>(&propagated)) return *stop;
        // The first fixed-plan call admits every shared stage before an empty
        // product is classified. Scan the product even if propagation found an
        // earlier safe-set violation before reaching an empty later stage.
        if(plan_index==0) {
            if(empty_set(request.initial)) return FiniteMinimaxNoScenarios{};
            for(const auto& disturbance:request.disturbances)
                if(empty_set(disturbance)) return FiniteMinimaxNoScenarios{};
        }
        if(const auto* empty=std::get_if<reachability::FixedPlanEmpty>(&propagated)) {
            (void)empty;
            return FiniteMinimaxNoScenarios{};
        }
        if(const auto* violation=std::get_if<reachability::FixedPlanViolation>(&propagated))
        {
            PlannedPhase record_timing{context,spans?std::optional{spans->record_assembly}:std::nullopt,&finalize};
            records.emplace_back(FinitePlanRejected{choices,violation->stage,violation->violating_successor});
            record_timing.close(Termination::completed);
        }
        else {
            const auto& tube=std::get<reachability::FixedPlanReachable>(propagated);
            const auto& terminal=tube.stages.back();
            PlannedPhase objective_timing{context,spans?std::optional{spans->objective}:std::nullopt,&finalize};
            const auto worst=worst_case_vertex(terminal,request.objective,limits.max_points_per_stage,context);
            objective_timing.close(objective_termination(worst));
            if(const auto* error=std::get_if<Unsupported>(&worst)) return *error;
            if(const auto* stop=std::get_if<OperationStopped>(&worst)) return *stop;
            if(std::holds_alternative<WorstCaseEmpty>(worst)) return FiniteMinimaxNoScenarios{};
            const auto& value=std::get<WorstCaseValue>(worst);
            if(value.value<minimum) minimum=value.value;
            PlannedPhase record_timing{context,spans?std::optional{spans->record_assembly}:std::nullopt,&finalize};
            records.emplace_back(FinitePlanFeasible{choices,value.value,value.maximizer,
                value.evaluated_vertices,terminal});
            record_timing.close(Termination::completed);
        }
    }
    PlannedPhase result_selection{context,timing_spans?std::optional{timing_spans->result_selection}:std::nullopt,&finalize};
    if(!std::isfinite(minimum)) {
        std::vector<FinitePlanRejected> rejected;
        rejected.reserve(records.size());
        for(auto& record:records) rejected.push_back(std::get<FinitePlanRejected>(std::move(record)));
        result_selection.close(Termination::completed);
        return FiniteMinimaxInfeasible{request.problem,request.request,std::move(rejected),Assurance::numerical};
    }
    std::vector<std::size_t> selected;
    for(std::size_t index=0;index<records.size();++index)
        if(const auto* feasible=std::get_if<FinitePlanFeasible>(&records[index]))
            if(static_cast<long double>(feasible->worst_value)-minimum<=limits.near_optimal_tolerance)
                selected.push_back(index);
    result_selection.close(Termination::completed);
    return FiniteMinimaxOptimal{request.problem,request.request,minimum,
        std::move(records),std::move(selected),Assurance::numerical};
}
} // namespace csl::optimization
