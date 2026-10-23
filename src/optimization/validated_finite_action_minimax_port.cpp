#include <csl/optimization/validated_finite_action_minimax_port.hpp>

#include <cmath>
#include <limits>

namespace csl::optimization {
namespace {

std::optional<std::size_t> point_count(const sets::SetData& set) {
    const auto rep=set.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep)) return 0;
    if(std::holds_alternative<sets::SingletonRepresentation>(rep)) return 1;
    if(const auto* v=std::get_if<sets::VRepresentation>(&rep)) {
        if(v->rays.rows()) return std::nullopt;
        return v->vertices.rows();
    }
    return std::nullopt;
}

bool safe_representation(const sets::SetData& set) {
    const auto rep=set.representation();
    return std::holds_alternative<sets::HRepresentation>(rep) ||
        std::holds_alternative<sets::SingletonRepresentation>(rep) ||
        std::holds_alternative<sets::EmptyRepresentation>(rep) ||
        std::holds_alternative<sets::UniversalRepresentation>(rep);
}

Diagnostics reject(DiagnosticCode code,std::string field,std::string message) {
    return {{code,std::move(field),std::move(message)}};
}

Diagnostics admit(const ValidatedFiniteActionMinimaxQuery& query,
        const registry::Requirements& requirements) {
    const auto& request=query.request;
    const auto dims=request.system.dimensions();
    const auto horizon=request.system.horizon();
    if(requirements.scalar!=registry::Scalar::binary64 ||
       requirements.output.representation!=RepresentationId{"csl.optimization.validated-finite-action-minimax.bounds"} ||
       requirements.output.assurance!=Assurance::validated || requirements.output.relation ||
       requirements.output.family || requirements.output.completeness)
        return reject(DiagnosticCode::unsupported,"validated_minimax.requirements",
            "The validated oracle offers only binary64 endpoints with validated assurance and no set relation or family claim.");
    if(request.problem.value.empty()||request.request.value.empty())
        return reject(DiagnosticCode::invalid_input,"validated_minimax.identity",
            "Nonempty problem and request identities are required.");
    if(request.actions.dimension!=dims.control || request.disturbances.size()!=horizon ||
       request.safe_sets.size()!=horizon+1 || request.objective.dimension()!=dims.state ||
       request.initial.metadata()->set.dimension!=dims.state)
        return reject(DiagnosticCode::invalid_input,"validated_minimax.dimension",
            "Action, set, objective, or stage dimensions differ from the model.");
    if(request.objective.policy().assurance!=Assurance::numerical ||
       std::holds_alternative<QuadraticCoefficients>(request.objective.coefficients()))
        return reject(DiagnosticCode::unsupported,"validated_minimax.objective",
            "Only stored binary64 linear and residual-norm objective coefficients are admitted.");
    for(const auto& action:request.actions.catalogue) {
        if(action.size()!=dims.control)
            return reject(DiagnosticCode::invalid_input,"validated_minimax.action.dimension",
                "Action dimension differs from the model.");
        for(double value:action) if(!std::isfinite(value))
            return reject(DiagnosticCode::invalid_input,"validated_minimax.action.finite",
                "Action values must be finite.");
    }
    auto histories=point_count(request.initial);
    if(!histories)
        return reject(DiagnosticCode::unsupported,"validated_minimax.initial.representation",
            "Initial states require a bounded native V description, singleton, or empty set.");
    for(const auto& disturbance:request.disturbances) {
        if(disturbance.metadata()->set.dimension!=dims.external)
            return reject(DiagnosticCode::invalid_input,"validated_minimax.disturbance.dimension",
                "Disturbance dimension differs from the model.");
        const auto count=point_count(disturbance);
        if(!count)
            return reject(DiagnosticCode::unsupported,"validated_minimax.disturbance.representation",
                "Disturbances require bounded native V descriptions, singletons, or empty sets.");
        if(*count&&*histories>std::numeric_limits<std::size_t>::max()/ *count)
            return reject(DiagnosticCode::unsupported,"validated_minimax.histories.overflow",
                "Disturbance history count overflows size_t.");
        *histories*=*count;
    }
    if(*histories && *histories>query.limits.max_histories_per_plan)
        return reject(DiagnosticCode::unsupported,"validated_minimax.histories.limit",
            "History count exceeds the caller limit.");
    for(const auto& safe:request.safe_sets) {
        if(safe.metadata()->set.dimension!=dims.state)
            return reject(DiagnosticCode::invalid_input,"validated_minimax.safe.dimension",
                "Safe-set dimension differs from the model.");
        const auto& labels=safe.metadata()->coordinate_labels;
        const auto& state_labels=request.initial.metadata()->coordinate_labels;
        if(!labels.empty()&&!state_labels.empty()&&labels!=state_labels)
            return reject(DiagnosticCode::invalid_input,"validated_minimax.safe.coordinates",
                "Safe-set coordinate labels differ from the initial-state labels.");
        if(!safe_representation(safe))
            return reject(DiagnosticCode::unsupported,"validated_minimax.safe.representation",
                "Safe sets require H, singleton, empty, or universal descriptions.");
    }
    if(horizon&&!request.actions.catalogue.empty()) {
        std::size_t plans=1;
        for(std::size_t stage=0;stage<horizon;++stage) {
            if(plans>std::numeric_limits<std::size_t>::max()/request.actions.catalogue.size())
                return reject(DiagnosticCode::unsupported,"validated_minimax.plans.overflow",
                    "Action plan count overflows size_t.");
            plans*=request.actions.catalogue.size();
        }
        if(plans>query.limits.max_plans)
            return reject(DiagnosticCode::unsupported,"validated_minimax.plans.limit",
                "Action plan count exceeds the caller limit.");
    }
    return {};
}

class ReferenceWorkspace final : public ValidatedFiniteActionMinimaxWorkspace {
public:
    ValidatedFiniteActionMinimaxOutcome solve(
            const ValidatedFiniteActionMinimaxQuery& query,
            const ExecutionContext& context) override {
        return validated_finite_action_minimax(query.request,query.limits,context);
    }
};

} // namespace

registry::Requirements validated_finite_action_minimax_requirements() {
    registry::Requirements requirements;
    requirements.output.representation={"csl.optimization.validated-finite-action-minimax.bounds"};
    requirements.output.assurance=Assurance::validated;
    return requirements;
}

registry::Registration<registry::ValidatedFiniteActionMinimaxPort>
make_validated_finite_action_minimax_registration() {
    return {{{"csl.optimization.validated-finite-action-minimax"},"1.0.0"},
        [](const ValidatedFiniteActionMinimaxQuery& query,
                const registry::Requirements& requirements)->registry::Capability {
            if(auto diagnostics=admit(query,requirements);!diagnostics.empty()) return diagnostics;
            return registry::Offer{validated_finite_action_minimax_requirements().output};
        },
        [](const ValidatedFiniteActionMinimaxQuery&)->
                std::unique_ptr<ValidatedFiniteActionMinimaxWorkspace> {
            return std::make_unique<ReferenceWorkspace>();
        }};
}

} // namespace csl::optimization

namespace csl::registry {

optimization::ValidatedFiniteActionMinimaxOutcome
ValidatedFiniteActionMinimaxPort::run(Workspace& workspace,const Request& query,
        const ExecutionContext& context) {
    auto result=workspace.solve(query,context);
    auto identity_mismatch=[&](const auto& completed) {
        return completed.problem()!=query.request.problem ||
            completed.request()!=query.request.request;
    };
    if(const auto* bounds=std::get_if<optimization::ValidatedMinimaxBounds>(&result)) {
        if(identity_mismatch(*bounds))
            return Unsupported{{{DiagnosticCode::evidence_mismatch,
                "validated_minimax.result.identity",
                "Completed bounds differ from the frozen request identity."}}};
    }
    if(const auto* infeasible=std::get_if<optimization::ValidatedMinimaxInfeasible>(&result)) {
        if(identity_mismatch(*infeasible))
            return Unsupported{{{DiagnosticCode::evidence_mismatch,
                "validated_minimax.result.identity",
                "Completed infeasible catalogue differs from the frozen request identity."}}};
    }
    if(const auto* unresolved=std::get_if<optimization::ValidatedMinimaxUnresolved>(&result)) {
        if(identity_mismatch(*unresolved))
            return Unsupported{{{DiagnosticCode::evidence_mismatch,
                "validated_minimax.result.identity",
                "Completed unresolved catalogue differs from the frozen request identity."}}};
    }
    return result;
}

} // namespace csl::registry
