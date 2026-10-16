#include <csl/reachability/finite_feedback_port.hpp>
#include <chrono>
#include <memory>
#include <utility>

namespace csl::reachability::finite_feedback {
namespace {
class ReferenceWorkspace final : public Workspace {
public:
    PortResult compute(const Request& request,const ExecutionContext& context) override {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Finite feedback calculation cancelled."};
        if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
            return OperationStopped{StopReason::deadline_expired,"Finite feedback deadline expired."};
        auto answer=solve(request.game);
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Finite feedback calculation cancelled."};
        if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
            return OperationStopped{StopReason::deadline_expired,"Finite feedback deadline expired."};
        if(const auto* error=std::get_if<Diagnostic>(&answer))return *error;
        return std::get<Policy>(std::move(answer));
    }
};
}

registry::Requirements finite_table_requirements() {
    registry::Requirements required;
    required.output.representation={"csl.feedback.finite-winning-table"};
    return required;
}

registry::Registration<registry::FiniteFeedbackPort> make_registration() {
    return {{{"csl.reachability.finite-feedback-table"},"1.0.0"},
        [](const Request& request,const registry::Requirements&) -> registry::Capability {
            if(request.problem.value.empty() || request.request.value.empty())
                return Diagnostics{{DiagnosticCode::invalid_input,"feedback.identity",
                    "Complete problem and request identity is required."}};
            if(const auto error=validate(request.game))return Diagnostics{*error};
            return registry::Offer{finite_table_requirements().output};
        },
        [](const Request&) -> std::unique_ptr<Workspace> {
            return std::make_unique<ReferenceWorkspace>();
        }};
}

RegisteredOutcome run_registered(const registry::Registry<registry::FiniteFeedbackPort>& registry,
        registry::Method method,const Request& request,const registry::Requirements& requirements,
        const ExecutionContext& context) {
    auto prepared=registry::prepare_pipeline(registry::select(registry,std::move(method),request,requirements));
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))
        return RegisteredFailure{request.problem,request.request,rejected->provenance,rejected->diagnostics};
    auto pipeline=std::get<registry::PreparedPipeline<registry::FiniteFeedbackPort>>(std::move(prepared));
    const auto provenance=pipeline.provenance()[0];
    if(context.cancellation.stop_requested())
        return RegisteredStopped{request.problem,request.request,provenance,
            {StopReason::cancelled,"Finite feedback calculation cancelled before workspace creation."}};
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return RegisteredStopped{request.problem,request.request,provenance,
            {StopReason::deadline_expired,"Finite feedback deadline expired before workspace creation."}};
    auto workspace=std::get<0>(pipeline.create());
    auto answer=workspace->run(context);
    if(auto* completed=std::get_if<Policy>(&answer))
        return RegisteredPolicy{request.problem,request.request,provenance,std::move(*completed)};
    if(auto* stopped=std::get_if<OperationStopped>(&answer))
        return RegisteredStopped{request.problem,request.request,provenance,std::move(*stopped)};
    return RegisteredFailure{request.problem,request.request,provenance,
        {std::get<Diagnostic>(std::move(answer))}};
}

} // namespace csl::reachability::finite_feedback

namespace csl::registry {
reachability::finite_feedback::PortResult FiniteFeedbackPort::run(Workspace& workspace,
        const Request& request,const ExecutionContext& context) {
    auto answer=workspace.compute(request,context);
    if(const auto* candidate=std::get_if<reachability::finite_feedback::Policy>(&answer)) {
        const auto reference=reachability::finite_feedback::solve(request.game);
        const auto* expected=std::get_if<reachability::finite_feedback::Policy>(&reference);
        if(!expected || *candidate!=*expected)
            return Diagnostic{DiagnosticCode::evidence_mismatch,"feedback.policy",
                "Provider winning states or admissible actions disagree with the complete finite-table reference."};
    }
    return answer;
}
} // namespace csl::registry
