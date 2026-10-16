#include <csl/optimization/finite_action_minimax_port.hpp>

namespace csl::optimization {
namespace {

bool compact_points(const sets::SetData& set) {
    const auto rep=set.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep) ||
       std::holds_alternative<sets::SingletonRepresentation>(rep)) return true;
    const auto* v=std::get_if<sets::VRepresentation>(&rep);
    return v && v->rays.rows()==0;
}

bool safe_set(const sets::SetData& set) {
    const auto rep=set.representation();
    return std::holds_alternative<sets::HRepresentation>(rep) ||
        std::holds_alternative<sets::SingletonRepresentation>(rep) ||
        std::holds_alternative<sets::UniversalRepresentation>(rep) ||
        std::holds_alternative<sets::EmptyRepresentation>(rep);
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
        [](const FiniteActionMinimaxQuery& query,const registry::Requirements&) -> registry::Capability {
            if(!compact_points(query.request.initial))
                return Diagnostics{{DiagnosticCode::unsupported,"finite_minimax.initial.representation",
                    "Initial states require a compact V description, singleton, or empty set."}};
            for(const auto& disturbance:query.request.disturbances)
                if(!compact_points(disturbance))
                    return Diagnostics{{DiagnosticCode::unsupported,"finite_minimax.disturbance.representation",
                        "Independent disturbances require compact V descriptions, singletons, or empty sets."}};
            for(const auto& safe:query.request.admissible_states)
                if(!safe_set(safe))
                    return Diagnostics{{DiagnosticCode::unsupported,"finite_minimax.safe.representation",
                        "Admissible states require H, singleton, universal, or empty descriptions."}};
            if(query.request.objective.policy().assurance!=Assurance::numerical)
                return Diagnostics{{DiagnosticCode::unsupported,"finite_minimax.objective.assurance",
                    "Only numerical convex terminal objectives are supported."}};
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
