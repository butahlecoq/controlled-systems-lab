#include <csl/optimization/finite_action_minimax_port.hpp>
#include <cmath>

namespace csl::optimization {
namespace {

std::optional<std::size_t> compact_point_count(const sets::SetData& set) {
    const auto rep=set.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep)) return 0;
    if(std::holds_alternative<sets::SingletonRepresentation>(rep)) return 1;
    const auto* v=std::get_if<sets::VRepresentation>(&rep);
    if(v && v->rays.rows()==0) return v->vertices.rows();
    return std::nullopt;
}

bool safe_set(const sets::SetData& set) {
    const auto rep=set.representation();
    return std::holds_alternative<sets::HRepresentation>(rep) ||
        std::holds_alternative<sets::SingletonRepresentation>(rep) ||
        std::holds_alternative<sets::UniversalRepresentation>(rep) ||
        std::holds_alternative<sets::EmptyRepresentation>(rep);
}

Diagnostics reject(DiagnosticCode code,std::string field,std::string reason) {
    return {{code,std::move(field),std::move(reason)}};
}

Diagnostics admit(const FiniteActionMinimaxQuery& query,const registry::Requirements& requirements) {
    const auto& request=query.request;
    const auto dims=request.system.dimensions();
    const auto horizon=request.system.horizon();
    if(request.problem.value.empty() || request.request.value.empty())
        return reject(DiagnosticCode::invalid_input,"finite_minimax.identity",
            "Nonempty problem and request identities are required.");
    if(!std::isfinite(query.limits.near_optimal_tolerance) || query.limits.near_optimal_tolerance<0)
        return reject(DiagnosticCode::invalid_input,"finite_minimax.tolerance",
            "Near-optimal tolerance must be finite and nonnegative.");
    if(request.actions.dimension!=dims.control || request.disturbances.size()!=horizon ||
       request.admissible_states.size()!=horizon+1 || request.objective.dimension()!=dims.state)
        return reject(DiagnosticCode::invalid_input,"finite_minimax.dimension",
            "Action, stage, or objective dimensions differ from the model.");
    for(const auto& action:request.actions.catalogue) {
        if(action.size()!=dims.control)
            return reject(DiagnosticCode::invalid_input,"finite_minimax.action",
                "Action row has the wrong dimension.");
        for(const auto value:action)
            if(!std::isfinite(value))
                return reject(DiagnosticCode::invalid_input,"finite_minimax.action",
                    "Action rows must be finite.");
    }
    if(request.initial.metadata()->set.dimension!=dims.state)
        return reject(DiagnosticCode::invalid_input,"fixed_plan.initial.dimension",
            "Initial state dimension differs from model.");
    auto candidate_count=compact_point_count(request.initial);
    if(!candidate_count)
        return reject(DiagnosticCode::unsupported,"finite_minimax.initial.representation",
            "Initial states require a compact V description, singleton, or empty set.");
    if(*candidate_count>query.limits.max_points_per_stage)
        return reject(DiagnosticCode::unsupported,"fixed_plan.capacity",
            "Initial point count exceeds the caller limit.");
    for(const auto& disturbance:request.disturbances) {
        if(disturbance.metadata()->set.dimension!=dims.external)
            return reject(DiagnosticCode::invalid_input,"fixed_plan.stage.dimension",
                "Disturbance dimension differs from model.");
        const auto count=compact_point_count(disturbance);
        if(!count)
            return reject(DiagnosticCode::unsupported,"finite_minimax.disturbance.representation",
                "Independent disturbances require compact V descriptions, singletons, or empty sets.");
        if(*count>query.limits.max_points_per_stage ||
           (*count!=0 && *candidate_count>query.limits.max_points_per_stage / *count))
            return reject(DiagnosticCode::unsupported,"fixed_plan.capacity",
                "Generated point count exceeds the caller limit.");
        candidate_count=*count==0?0:*candidate_count * *count;
    }
    for(const auto& safe:request.admissible_states) {
        if(safe.metadata()->set.dimension!=dims.state ||
           (!safe.metadata()->coordinate_labels.empty() &&
            !request.initial.metadata()->coordinate_labels.empty() &&
            safe.metadata()->coordinate_labels!=request.initial.metadata()->coordinate_labels))
            return reject(DiagnosticCode::invalid_input,"fixed_plan.safe.dimension",
                "Safe set dimensions or named coordinates differ from initial state.");
        if(!safe_set(safe))
            return reject(DiagnosticCode::unsupported,"finite_minimax.safe.representation",
                "Admissible states require H, singleton, universal, or empty descriptions.");
    }
    if(!(horizon && request.actions.catalogue.empty())) {
        std::size_t plan_count=1;
        for(std::size_t stage=0;stage<horizon;++stage) {
            if(plan_count>query.limits.max_plans/request.actions.catalogue.size())
                return reject(DiagnosticCode::unsupported,"finite_minimax.capacity",
                    "Action product exceeds the caller plan limit.");
            plan_count*=request.actions.catalogue.size();
        }
        if(plan_count>query.limits.max_plans)
            return reject(DiagnosticCode::unsupported,"finite_minimax.capacity",
                "Action product exceeds the caller plan limit.");
    }
    if(request.objective.policy().assurance!=Assurance::numerical ||
       requirements.output.assurance!=Assurance::numerical)
        return reject(DiagnosticCode::unsupported,"finite_minimax.objective.assurance",
            "Only numerical convex terminal objectives and numerical output assurance are supported.");
    return {};
}

class ReferenceWorkspace final : public FiniteActionMinimaxWorkspace {
public:
    FiniteActionMinimaxOutcome solve(const FiniteActionMinimaxQuery& query,
        const ExecutionContext& context) override {
        return finite_action_minimax(query.request,query.limits,context);
    }
};

} // namespace

registry::Requirements finite_action_minimax_requirements() {
    registry::Requirements required;
    required.output.representation={"csl.optimization.finite-action-minimax.value"};
    return required;
}

registry::Registration<registry::FiniteActionMinimaxPort>
make_finite_action_minimax_registration() {
    return {{{"csl.optimization.finite-action-minimax"},"1.0.0"},
        [](const FiniteActionMinimaxQuery& query,const registry::Requirements& requirements) -> registry::Capability {
            if(auto diagnostics=admit(query,requirements);!diagnostics.empty())
                return diagnostics;
            return registry::Offer{finite_action_minimax_requirements().output};
        },
        [](const FiniteActionMinimaxQuery&) -> std::unique_ptr<FiniteActionMinimaxWorkspace> {
            return std::make_unique<ReferenceWorkspace>();
        }};
}

} // namespace csl::optimization

namespace csl::registry {

optimization::FiniteActionMinimaxOutcome FiniteActionMinimaxPort::run(
        Workspace& workspace,const Request& query,const ExecutionContext& context) {
    auto result=workspace.solve(query,context);
    auto identity_mismatch=[&](const auto& completed) {
        return completed.problem!=query.request.problem ||
            completed.request!=query.request.request ||
            completed.assurance!=Assurance::numerical;
    };
    if(const auto* optimal=std::get_if<optimization::FiniteMinimaxOptimal>(&result)) {
        if(identity_mismatch(*optimal))
            return Unsupported{{{DiagnosticCode::evidence_mismatch,"finite_minimax.result.identity",
                "Completed minimax result differs from the frozen request identity or numerical assurance."}}};
    }
    if(const auto* infeasible=std::get_if<optimization::FiniteMinimaxInfeasible>(&result)) {
        if(identity_mismatch(*infeasible))
            return Unsupported{{{DiagnosticCode::evidence_mismatch,"finite_minimax.result.identity",
                "Completed minimax result differs from the frozen request identity or numerical assurance."}}};
    }
    return result;
}

} // namespace csl::registry
