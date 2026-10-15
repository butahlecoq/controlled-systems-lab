#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/execution/timing_collector.hpp>
#include "../../registry/compiled_verifiers.hpp"
#include "../../registry/strategy_a_lineage.hpp"
#include <algorithm>
#include <new>
#include <utility>

namespace csl::synthesis::strategy_a {
CandidateHistory::CandidateHistory(PreimageTarget scope,JointHistoryRelation h,reachability::ForwardTube f,
    std::optional<TerminalMinimizers> t):target(scope),history(std::move(h)),forward(std::move(f)),terminal(std::move(t)){}
namespace {
const ModuleId strategy{"csl.synthesis.reach-back"};
const std::string version="1";
Diagnostics unsupported(std::string field,std::string reason) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(reason)}};
}
Diagnostics capabilities(const problem::ResolvedProblem& problem,const FamilyRequest& family) {
    if(auto errors=check_family_request(family,problem.identity());!errors.empty())return errors;
    const bool exact_ts01=registry::detail::ts01_case_valid(problem,family,family.representation);
    const bool exact_ts02=registry::detail::ts02_case_valid(problem,family,family.representation);
    if(!exact_ts01&&!exact_ts02&&family.profile!="nominal_open_loop")return unsupported("strategy_a.profile","Only nominal_open_loop candidates and the reviewed T-S01/T-S02 exact profiles are supported.");
    if(!exact_ts01&&!exact_ts02&&family.target!=FamilyTarget::candidate_relaxation)
        return unsupported("strategy_a.coverage","No reviewed coverage procedure or optimal-subset verifier; request a candidate relation.");
    if(family.assurance!=Assurance::numerical)
        return unsupported("strategy_a.assurance","Only unestablished binary64 candidate construction is supported.");
    if(family.representation.value!="csl.polyhedron.h")
        return unsupported("strategy_a.representation","Canonical joint native H output required.");
    if(family.materialization_limit)
        return unsupported("strategy_a.capacity","Family materialization-limit semantics have not been reviewed; no limit is silently ignored.");
    const auto source=problem.description();
    if(auto errors=check_nominal_profile(*source,false,family.assurance);!errors.empty())return errors;
    if(source->temporal && source->temporal->joint_map.rows!=0)
        return unsupported("strategy_a.temporal","Nonempty temporal constraints require a coupled-history implementation.");
    const auto native=[](const AdmissibleSet& set) {
        const auto* handle=std::get_if<SetHandle>(&set);
        if(!handle)return true;
        auto data=sets::from_handle(*handle);const auto* value=std::get_if<sets::SetData>(&data);
        return value && !std::holds_alternative<sets::VRepresentation>(value->representation());
    };
    for(const auto& set:source->states)if(!native(set))
        return unsupported("strategy_a.states","Native H, singleton, empty or universal state factors required.");
    for(const auto& set:std::get<ContinuousDomain>(source->controls).stages)if(!native(set))
        return unsupported("strategy_a.controls","Native H, singleton, empty or universal control factors required.");
    return {};
}
RetainedEvidenceScope retained(const SynthesisResult& result) {
    return {result.objective.lower.has_value(),result.objective.upper.has_value(),
        result.incumbents.size(),result.family.has_value()};
}
RequestProvenance provenance(RequestId request,const registry::Provenance& provider) {
    return {std::move(request),provider.port,provider.requested.id,provider.requested.version,
        provider.actual?std::optional<ModuleId>{provider.actual->id}:std::nullopt,
        provider.actual?std::optional<std::string>{provider.actual->version}:std::nullopt};
}
RequestProvenance local(RequestId request) {
    return {std::move(request),"strategy",strategy,version,strategy,version};
}
std::vector<TransformStepIdentity> forward_lineage(const reachability::ForwardTube& tube) {
    std::vector<TransformStepIdentity> result;
    for(const auto& stage:tube.stages) {
        const auto& reference=stage.marginal.evidence.reference;
        result.push_back({reference.identity.request,stage.source_factors.front(),
            stage.marginal.output.id,strategy,version});
    }
    return result;
}
std::variant<std::shared_ptr<const ::csl::synthesis::Ts02ConstantIntegratorRelation>,Diagnostics>
canonical_ts02_relation() {
    auto inequalities=numeric::snapshot(Matrix{4,5,{0,0,0,1,0, 0,0,0,-1,0,
        0,0,0,0,1, 0,0,0,0,-1}});
    auto upper=numeric::snapshot_vector(Vector{1,0,1,0});
    auto equalities=numeric::snapshot(Matrix{3,5,{1,0,0,0,0, -1,1,0,-1,0,
        0,-1,1,0,-1}});
    auto equality_values=numeric::snapshot_vector(Vector{0,0,0});
    if(!std::holds_alternative<numeric::MatrixView>(inequalities)||
        !std::holds_alternative<numeric::VectorView>(upper)||
        !std::holds_alternative<numeric::MatrixView>(equalities)||
        !std::holds_alternative<numeric::VectorView>(equality_values))
        return Diagnostics{{DiagnosticCode::invalid_input,"strategy_a.ts02.relation","Could not construct exact canonical H-relation buffers."}};
    auto data=sets::make_h({{"ts02-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    if(!std::holds_alternative<sets::SetData>(data))
        return Diagnostics{{DiagnosticCode::invalid_input,"strategy_a.ts02.relation","Canonical T-S02 H-relation is not a valid polyhedron."}};
    return std::make_shared<const ::csl::synthesis::Ts02ConstantIntegratorRelation>(
        std::get<sets::SetData>(std::move(data)));
}
void reject(SynthesisResult& result,RequestProvenance request,Diagnostics diagnostics,
    const std::vector<TransformStepIdentity>& lineage) {
    result.termination=Termination::operation_rejected;
    result.stop=ScopedRequestRejection{std::move(request),std::move(diagnostics),lineage,retained(result)};
}
void contract_failure(SynthesisResult& result,Diagnostics diagnostics) {
    result.termination=Termination::contract_rejected;
    result.stop=ContractValidationFailure{std::move(diagnostics),retained(result),{}};
}
void stop(SynthesisResult& result,RequestProvenance request,OperationStopped cause) {
    switch(cause.reason) {
    case StopReason::cancelled:result.termination=Termination::cancelled;break;
    case StopReason::deadline_expired:
        // Existing shared guard accepts deadline_expired with cancelled. Keep
        // the distinct source reason rather than rewriting a deadline as a cap.
        result.termination=Termination::cancelled;break;
    case StopReason::resource_limit:result.termination=Termination::resource_limit;break;
    case StopReason::numerical_failure:result.termination=Termination::numerical_failure;break;
    }
    result.stop=ScopedOperationStopped{std::move(cause),std::move(request),retained(result)};
}
std::optional<OperationStopped> interruption(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Cancelled between Strategy A phases."};
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"Deadline expired between Strategy A phases."};
    return {};
}
std::optional<execution::observability::TimingScope> timing_scope(
    const ExecutionContext& context,artifacts::SpanId id) {
    auto started=execution::observability::start_timing(context,id);
    if(auto* scope=std::get_if<execution::observability::TimingScope>(&started))return std::move(*scope);
    return {};
}
void close_timing(std::optional<execution::observability::TimingScope>& scope,Termination termination) noexcept {
    if(scope)scope->close(termination);
}
class ResultTimingScope {
    std::optional<execution::observability::TimingScope> scope_;
    const Termination* termination_;
public:
    ResultTimingScope(std::optional<execution::observability::TimingScope> scope,const Termination& termination)
        :scope_(std::move(scope)),termination_(&termination){}
    ~ResultTimingScope(){if(scope_)scope_->close(*termination_);}
    ResultTimingScope(const ResultTimingScope&)=delete;
    ResultTimingScope& operator=(const ResultTimingScope&)=delete;
};
Termination forward_termination(const reachability::ForwardFailure& failure) {
    if(std::holds_alternative<Unsupported>(failure.cause))return Termination::operation_rejected;
    switch(std::get<OperationStopped>(failure.cause).reason) {
    case StopReason::cancelled:case StopReason::deadline_expired:return Termination::cancelled;
    case StopReason::resource_limit:return Termination::resource_limit;
    case StopReason::numerical_failure:return Termination::numerical_failure;
    }
    return Termination::numerical_failure;
}
bool publish(SynthesisResult& result,const problem::ResolvedProblem& problem,const FamilyRequest& request,
    JointHistoryRelation history,const reachability::ForwardTube& tube,std::optional<TerminalMinimizers> terminal,
    std::vector<TransformStepIdentity> lineage,PreimageTarget target=PreimageTarget::forward_terminal_slice) {
    const auto coordinates=history.coordinates;
    auto data=std::make_shared<const CandidateHistory>(target,std::move(history),tube,std::move(terminal));
    const std::string method=target==PreimageTarget::terminal_candidate?
        "binary64 feasible preimage of entire terminal candidate; terminal optimizer anchor and forward coverage unestablished":
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate";
    auto outcome=FamilyPublisher::publish({problem.identity(),request,coordinates,strategy,version,std::move(lineage)},
        CandidateFamily{{coordinates,request.representation,std::move(data)},HeuristicRelationEvidence{method},Unestablished{}});
    if(auto* errors=std::get_if<Diagnostics>(&outcome)){contract_failure(result,*errors);return false;}
    result.family=std::get<OptimalFamily>(std::move(outcome));return true;
}
} // namespace
namespace detail {
class StrategyAExecutionRunner final : public SynthesisWorkspace, public registry::detail::StrategyARuntimeReceiptSource {
    reachability::ForwardDependencies forward_;
    TerminalOptimizer terminal_;
    registry::StrategyRequest prepared_request_;
    registry::StrategyRegistration::CompleteFamilyVerifierKey verifier_binding_;
    std::optional<registry::detail::StrategyARuntimeLineageReceipt> receipt_;
public:
    StrategyAExecutionRunner(reachability::ForwardDependencies forward,registry::PreparedProvider<registry::LPPort> lp,
        registry::PreparedProvider<registry::ConvexPort> convex,registry::StrategyRequest prepared_request,
        registry::StrategyRegistration::CompleteFamilyVerifierKey verifier_binding)
        :forward_(std::move(forward)),terminal_(std::move(lp),std::move(convex)),
         prepared_request_(std::move(prepared_request)),verifier_binding_(std::move(verifier_binding)){}

    std::optional<registry::detail::StrategyARuntimeLineageReceipt> take_strategy_a_runtime_receipt() noexcept override {
        return std::exchange(receipt_,std::nullopt);
    }

    SynthesisResult solve(const problem::ResolvedProblem& problem,const FamilyRequest& request,
        const ExecutionContext& context) override {
        receipt_.reset();
        SynthesisResult result{Termination::completed,{problem.identity(),MathematicalOutcome::undetermined,
            Unestablished{},{"forward recurrence, terminal construction and joint-history coverage remain unestablished"}},
            {},{},{},{},{}};
        ResultTimingScope run_timing{timing_scope(context,timing::run),result.termination};
        std::vector<TransformStepIdentity> lineage;
        try {
            if(auto errors=capabilities(problem,request);!errors.empty()) {
                reject(result,local({"strategy-a/admission"}),std::move(errors),lineage);return result;
            }
            auto forward_timing=timing_scope(context,timing::forward);
            auto forwarded=reachability::nominal_forward(problem,{"strategy-a/forward"},forward_,context);
            if(const auto* failure=std::get_if<reachability::ForwardFailure>(&forwarded)) {
                close_timing(forward_timing,forward_termination(*failure));
                lineage=forward_lineage(failure->prefix);
                const auto selected=failure->providers.empty()?local({"strategy-a/forward"}):failure->providers.back();
                if(const auto* cause=std::get_if<Unsupported>(&failure->cause))reject(result,selected,cause->diagnostics,lineage);
                else stop(result,selected,std::get<OperationStopped>(failure->cause));
                return result;
            }
            close_timing(forward_timing,Termination::completed);
            if(const auto* empty=std::get_if<reachability::EmptyForwardStage>(&forwarded)) {
                result.outcome.assumptions.push_back("forward stage "+std::to_string(empty->stage.value)+
                    " compiled empty; authored infeasibility is not independently established");return result;
            }
            const auto tube=std::get<reachability::ForwardTube>(std::move(forwarded));
            lineage=forward_lineage(tube);
            auto feasible=sets::from_handle(tube.stages.back().marginal.output);
            if(const auto* error=std::get_if<Diagnostic>(&feasible)){contract_failure(result,{*error});return result;}
            const TerminalSlice slice{problem.identity(),std::get<sets::SetData>(std::move(feasible))};
            auto feasible_preimage_timing=timing_scope(context,timing::feasible_preimage);
            auto recovery=recover_joint_history(problem,slice.feasible);
            if(const auto* errors=std::get_if<Diagnostics>(&recovery)) {
                close_timing(feasible_preimage_timing,Termination::operation_rejected);
                reject(result,local({"strategy-a/feasible-preimage"}),*errors,lineage);return result;
            }
            close_timing(feasible_preimage_timing,Termination::completed);
            const auto feasible_history=std::get<JointHistoryRelation>(std::move(recovery));
            auto feasible_lineage=lineage;
            feasible_lineage.push_back({{"strategy-a/feasible-preimage"},slice.feasible.metadata()->id,
                feasible_history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});
            if(!publish(result,problem,request,feasible_history,tube,{},feasible_lineage))return result;
            if(auto interrupted=interruption(context)) {
                stop(result,local({"strategy-a/terminal"}),*interrupted);return result;
            }
            auto terminal_timing=timing_scope(context,timing::terminal_optimization);
            auto minimized=terminal_.solve(problem,request,slice,context);
            close_timing(terminal_timing,minimized.termination);
            const auto terminal_request=minimized.optimization?
                RequestId{minimized.optimization->outcome.subject.program.value}:
                RequestId{"syn02-terminal:"+slice.feasible.metadata()->id.value};
            const auto selected=minimized.provider?provenance(terminal_request,*minimized.provider):local(terminal_request);
            lineage=feasible_lineage;
            if(minimized.relation)lineage.push_back({terminal_request,slice.feasible.metadata()->id,
                minimized.relation->metadata()->id,{"csl.synthesis.terminal-minimizers"},"1"});
            // Preserve every completed transformation and scoped solver evidence,
            // even if cancellation stops before the terminal preimage is joined.
            // These program bounds cannot become original-problem bounds.
            if(!publish(result,problem,request,feasible_history,tube,minimized,lineage))return result;
            if(minimized.termination==Termination::operation_rejected) {
                reject(result,selected,minimized.diagnostics,lineage);return result;
            }
            if(minimized.termination==Termination::contract_rejected) {
                contract_failure(result,minimized.diagnostics);return result;
            }
            if(minimized.termination!=Termination::completed) {
                const auto reason=minimized.termination==Termination::cancelled?StopReason::cancelled:
                    minimized.termination==Termination::resource_limit?StopReason::resource_limit:StopReason::numerical_failure;
                stop(result,selected,{reason,"Terminal optimization stopped; slice-scoped evidence retained."});return result;
            }
            if(!minimized.relation) {
                if(!minimized.diagnostics.empty())contract_failure(result,minimized.diagnostics);
                return result;
            }
            if(auto interrupted=interruption(context)) {stop(result,local({"strategy-a/terminal-preimage"}),*interrupted);return result;}
            auto terminal_preimage_timing=timing_scope(context,timing::terminal_preimage);
            auto recovered=recover_joint_history(problem,*minimized.relation);
            if(const auto* errors=std::get_if<Diagnostics>(&recovered)) {
                close_timing(terminal_preimage_timing,Termination::operation_rejected);
                reject(result,local({"strategy-a/terminal-preimage"}),*errors,lineage);return result;
            }
            close_timing(terminal_preimage_timing,Termination::completed);
            auto history=std::get<JointHistoryRelation>(std::move(recovered));
            lineage.push_back({{"strategy-a/terminal-preimage"},minimized.relation->metadata()->id,
                history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});
            const bool exact_ts01=registry::detail::ts01_case_valid(problem,request,request.representation)&&
                lineage==prepared_request_.lineage&&minimized.optimization&&
                minimized.optimization->outcome.value==MathematicalOutcome::optimal;
            const bool exact_ts02=registry::detail::ts02_case_valid(problem,request,request.representation)&&lineage==prepared_request_.lineage&&
                minimized.optimization&&minimized.optimization->outcome.value==MathematicalOutcome::optimal;
            const auto proposal_identity=FamilyIdentity{problem.identity(),request,history.coordinates,
                strategy,version,lineage};
            if(exact_ts01&&result.termination==Termination::completed) {
                receipt_=registry::detail::StrategyARuntimeLineageReceipt{prepared_request_,
                    std::make_shared<const reachability::ForwardTube>(tube),
                    std::make_shared<const sets::SetData>(slice.feasible),
                    std::make_shared<const JointHistoryRelation>(feasible_history),
                    std::make_shared<const TerminalMinimizers>(minimized),
                    std::make_shared<const JointHistoryRelation>(history),verifier_binding_};
            }
            publish(result,problem,request,std::move(history),tube,std::move(minimized),std::move(lineage),
                PreimageTarget::terminal_candidate);
            if(exact_ts01&&result.termination==Termination::completed) {
                auto canonical=registry::detail::make_ts01_relation();
                if(const auto* errors=std::get_if<Diagnostics>(&canonical)) {
                    contract_failure(result,*errors);return result;
                }
                const SymbolicArgument derivation{"T-S01 exact analytic derivation",
                    "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
                const ClaimEvidence claim{problem.identity(),derivation};
                const ObjectiveBound zero{0,{problem.identity(),derivation}};
                const OptimumEvidence optimum{claim,{zero,zero}};
                auto payload=std::get<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>>(std::move(canonical));
                CompleteOptimalFamily family{{proposal_identity.coordinates,request.representation,payload},optimum,
                    {proposal_identity,RegisteredCompletenessEvidence{{"csl.verifier.ts01-analytic"},"1","TS01-analytic-v1"}},
                    Assurance::numerical};
                result.outcome={problem.identity(),MathematicalOutcome::optimal,derivation,{}};
                result.objective=optimum.bounds;
                result.complete_proposal=CompleteFamilyProposal{proposal_identity,std::move(family)};
            }
            if(exact_ts02&&result.termination==Termination::completed) {
                const SymbolicArgument derivation{"T-S02 exact constant-objective derivation",
                    "For x0=0, x1=x0+u0, x2=x1+u1 and u0,u1 in [0,1], every feasible history has terminal objective 3. Therefore the argmin relation is exactly the full feasible joint-history polyhedron."};
                const ClaimEvidence claim{problem.identity(),derivation};
                const ObjectiveBound constant{3,{problem.identity(),derivation}};
                const OptimumEvidence optimum{claim,{constant,constant}};
                auto canonical=canonical_ts02_relation();
                if(const auto* errors=std::get_if<Diagnostics>(&canonical)){contract_failure(result,*errors);return result;}
                CompleteOptimalFamily family{{proposal_identity.coordinates,request.representation,
                        std::get<std::shared_ptr<const ::csl::synthesis::Ts02ConstantIntegratorRelation>>(std::move(canonical))},optimum,
                    {proposal_identity,RegisteredCompletenessEvidence{{::csl::synthesis::ts02_constant_integrator_verifier},"1",
                        ::csl::synthesis::ts02_constant_integrator_proof}},
                    Assurance::numerical};
                result.outcome={problem.identity(),MathematicalOutcome::optimal,derivation,{}};
                result.objective=optimum.bounds;
                result.complete_proposal=CompleteFamilyProposal{proposal_identity,std::move(family)};
            }
            return result;
        } catch(const std::bad_alloc&) {
            stop(result,local({"strategy-a/storage"}),{StopReason::resource_limit,"Strategy A allocation failed; previously published evidence retained."});
        } catch(const std::length_error&) {
            stop(result,local({"strategy-a/storage"}),{StopReason::resource_limit,"Strategy A container capacity exceeded; previously published evidence retained."});
        }
        return result;
    }
};
}
registry::StrategyRegistration make_registration(Providers providers) {
    registry::StrategyRegistration registration{{strategy,version},
        [](const registry::StrategyRequest& request,const registry::Requirements&)->registry::Capability {
            if(auto errors=capabilities(request.problem,request.family);!errors.empty())return errors;
            registry::Output output;output.representation=request.family.representation;
            output.family=request.family.target;
            output.completeness=request.family.target==FamilyTarget::exact_optimal_relation?
                registry::Completeness::established:registry::Completeness::unestablished;
            return registry::Offer{std::move(output)};
        },[providers=std::move(providers)](const registry::StrategyRequest&,const registry::Requirements&)
            ->std::variant<registry::StrategyPlan,registry::Rejection> {
            auto fixed=std::get<registry::CheckedPipeline<>>(registry::check_pipeline());
            return registry::compose_strategy(std::move(fixed),providers,
                [](auto,const auto& generated,const registry::StrategyRequest& prepared,const registry::Requirements&)
                    ->std::unique_ptr<SynthesisWorkspace> {
                    auto selected_verifier=registry::StrategyRegistration::CompleteFamilyVerifierKey{{"csl.verifier.ts01-analytic"},"1"};
                    if(prepared.family.profile==::csl::synthesis::ts02_constant_integrator_profile&&
                        prepared.family.target==FamilyTarget::exact_optimal_relation)
                        selected_verifier={{::csl::synthesis::ts02_constant_integrator_verifier},"1"};
                    return std::make_unique<detail::StrategyAExecutionRunner>(reachability::ForwardDependencies{
                        std::get<0>(generated),std::get<1>(generated),std::get<2>(generated)},
                        std::get<3>(generated),std::get<4>(generated),prepared,std::move(selected_verifier));
                });
        },registry::StrategyRegistration::CompleteFamilyVerifierKey{{"csl.verifier.ts01-analytic"},"1"},
        [](const registry::StrategyRequest& request) {
            if(request.strategy_version==version&&request.configuration.strategy==strategy&&
                registry::detail::ts01_case_valid(request.problem,request.family,request.configuration.representation))
                return detail::expected_ts01_lineage(request.problem.identity());
            if(request.strategy_version==version&&request.configuration.strategy==strategy&&
                registry::detail::ts02_case_valid(request.problem,request.family,request.configuration.representation))
                return detail::expected_ts02_lineage(request.problem.identity());
            return std::vector<TransformStepIdentity>{};
        }};
    registration.complete_family_verifier_selector=[](const registry::StrategyRequest& request)
        ->std::optional<registry::StrategyRegistration::CompleteFamilyVerifierKey> {
        if(request.configuration.strategy==strategy&&
            registry::detail::ts02_case_valid(request.problem,request.family,request.configuration.representation))
            return registry::StrategyRegistration::CompleteFamilyVerifierKey{{::csl::synthesis::ts02_constant_integrator_verifier},"1"};
        // Retain the original T-S01 binding for all other requests; capabilities
        // still reject unsupported coverage/profile requests with scoped diagnostics.
        return registry::StrategyRegistration::CompleteFamilyVerifierKey{{"csl.verifier.ts01-analytic"},"1"};
    };
    return registration;
}
}
