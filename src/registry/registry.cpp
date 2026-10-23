#include <csl/registry/registry.hpp>
#include "compiled_verifiers.hpp"
#include <algorithm>

namespace csl::registry {
SynthesisIdentityExpectation PreparedStrategy::expected_synthesis_identity() const {
    return {request_->problem.identity(), request_->family,
        request_->problem.constraints().coordinates(), request_->configuration.strategy,
        request_->strategy_version, request_->lineage};
}
namespace {
bool matches_prepared_identity(const FamilyIdentity& actual,
    const problem::ResolvedProblem& problem,const FamilyRequest& family,
    const StrategyRequest& request) {
    const FamilyIdentity expected{problem.identity(),family,problem.constraints().coordinates(),
        request.configuration.strategy,request.strategy_version,request.lineage};
    return actual==expected;
}
}

SynthesisResult detail::VerifiedStrategyWorkspace::solve(const problem::ResolvedProblem& problem,
    const FamilyRequest& family,const ExecutionContext& context) {
    auto result=workspace_->solve(problem,family,context);
    auto reject=[&](Diagnostics diagnostics) {
        result.family.reset();
        result.complete_proposal.reset();
        result.partial_proposal.reset();
        result.outcome={problem.identity(),MathematicalOutcome::undetermined,Unestablished{}, {}};
        result.objective={};
        result.termination=Termination::contract_rejected;
        result.stop=ContractValidationFailure{std::move(diagnostics),{false,false,result.incumbents.size(),false},{}};
        return result;
    };
    if(result.complete_proposal&&result.partial_proposal)
        return reject({{DiagnosticCode::invalid_claim,"family.proposal.ambiguous",
            "A strategy cannot submit complete-family and partial-family proposals in one result"}});
    if(result.partial_proposal) {
        if(!partial_verifier_||!partial_authority_)
            return reject({{DiagnosticCode::unsupported,"family.partial.verifier",
                "Selected strategy has no registered partial-family verifier"}});
        const auto& proposal=*result.partial_proposal;
        const auto& identity=proposal.identity;
        if(family.target!=FamilyTarget::partial_relation||
            !matches_prepared_identity(identity,problem,family,*request_))
            return reject({{DiagnosticCode::evidence_mismatch,"family.partial.binding",
                "Partial-family proposal differs from the prepared problem, effective request, coordinates, strategy or lineage"}});
        auto diagnostics=partial_verifier_->verify(*request_,proposal);
        if(!diagnostics.empty())return reject(std::move(diagnostics));
        const auto published=FamilyPublisher::publish_verified_partial(identity,proposal.family,*partial_authority_,
            partial_verifier_->id(),partial_verifier_->version());
        if(const auto* errors=std::get_if<Diagnostics>(&published))return reject(*errors);
        result.family=std::get<OptimalFamily>(published);
        result.partial_proposal.reset();
        return result;
    }
    if(!result.complete_proposal)return result;
    if(!verifier_)
        return reject({{DiagnosticCode::unsupported,"family.verifier","Selected strategy has no complete-family verifier"}});
    const auto& proposal=*result.complete_proposal;
    const auto& identity=proposal.identity;
    if(!matches_prepared_identity(identity,problem,family,*request_)||
        proposal.family.completeness.binding!=identity)
        return reject({{DiagnosticCode::evidence_mismatch,"family.proposal.binding",
            "Complete-family proposal differs from the prepared problem, effective request or selected registration"}});
    const bool strategy_b_ts01=request_->family.target==FamilyTarget::exact_optimal_relation&&
        detail::strategy_b_ts01_profile_valid(request_->problem,*request_);
    if(strategy_b_ts01) {
        auto* source=dynamic_cast<detail::RuntimeReceiptSource*>(workspace_.get());
        auto receipt=source?source->take_runtime_receipt():std::nullopt;
        const StrategyRegistration::CompleteFamilyVerifierKey selected_verifier{verifier_->id(),verifier_->version()};
        if(!receipt||!receipt->matches(*request_,identity,selected_verifier))
            return reject({{DiagnosticCode::evidence_mismatch,"family.runtime_receipt",
                "Complete Strategy B T-S01 publication requires fresh runtime evidence for the executed build and extraction sequence"}});
    }
    const bool strategy_a_ts01=request_->family.target==FamilyTarget::exact_optimal_relation&&
        detail::strategy_a_ts01_profile_valid(request_->problem,*request_);
    const bool strategy_a_ts03=request_->family.target==FamilyTarget::exact_optimal_relation&&
        detail::strategy_a_ts03_profile_valid(request_->problem,*request_);
    if(strategy_a_ts01||strategy_a_ts03) {
        auto* source=dynamic_cast<detail::StrategyARuntimeReceiptSource*>(workspace_.get());
        auto receipt=source?source->take_strategy_a_runtime_receipt():std::nullopt;
        const StrategyRegistration::CompleteFamilyVerifierKey selected_verifier{verifier_->id(),verifier_->version()};
        if(!receipt||!receipt->matches(*request_,identity,selected_verifier))
            return reject({{DiagnosticCode::evidence_mismatch,"family.runtime_receipt",
                "Complete Strategy A T-S01/T-S03 publication requires fresh runtime evidence for the executed forward, terminal, and recovery sequence"}});
    }
    const auto* registered=std::get_if<RegisteredCompletenessEvidence>(&proposal.family.completeness.support);
    if(!registered||registered->verifier!=verifier_->id()||
        registered->verifier_version!=verifier_->version()||registered->proof.empty())
        return reject({{DiagnosticCode::evidence_mismatch,"family.proposal.verifier",
            "Proposal proof payload does not match the frozen strategy registration"}});
    // The registry owns identity/context binding; the compiled verifier
    // validate theorem content against that already-frozen authoritative input.
    auto diagnostics=verifier_->verify(*request_,proposal);
    if(!diagnostics.empty())return reject(std::move(diagnostics));
    auto published=FamilyPublisher::publish_verified(identity,OptimalFamilyOutcome{proposal.family},authority_);
    if(const auto* errors=std::get_if<Diagnostics>(&published))return reject(*errors);
    result.family=std::get<OptimalFamily>(std::move(published));
    result.complete_proposal.reset();
    return result;
}
std::variant<WitnessSelection,Unsupported> SelectorPort::run(Workspace& workspace,const Request& request,
    const ExecutionContext& context) {
    auto diagnostics=check_family_evidence(request.family,request.family.identity().problem,
        request.family.identity().request.assurance);
    if (!diagnostics.empty()) return Unsupported{std::move(diagnostics)};
    auto selection=workspace.select(request.family,request.selection,context);
    if (auto* result=std::get_if<WitnessSelection>(&selection)) {
        if (result->batch.source_family && *result->batch.source_family!=request.family.identity())
            return Unsupported{{{DiagnosticCode::evidence_mismatch,"selection.source_family",
                "Selector reported a different source family identity"}}};
        for (const auto& witness:result->batch.witnesses)
            if (witness.problem!=request.family.identity().problem)
                return Unsupported{{{DiagnosticCode::evidence_mismatch,"selection.witness.problem",
                    "Selected witness belongs to another resolved problem"}}};
        result->batch.source_family=request.family.identity();
    }
    return selection;
}
StrategyRequest StrategyPort::snapshot(const Request& request) {
    return request; // ResolvedProblem already owns immutable canonical data and its content.
}
SynthesisOutcome StrategyPort::run(Workspace& workspace,const Request& request,const ExecutionContext& context) {
    auto admission=check_family_request(request.family,request.problem.identity());
    if (!admission.empty()) return Unsupported{std::move(admission)};
    if (!(request.family.numerical==context.numerical)) {
        Diagnostics diagnostics{{DiagnosticCode::invalid_input,"family.numerical",
            "ExecutionContext numerical policy differs from the prepared family request"}};
        return SynthesisResult{Termination::contract_rejected,
            {request.problem.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},{},{},ContractValidationFailure{std::move(diagnostics),{},{}}};
    }
    if (request.family.assurance==Assurance::validated)
        return Unsupported{{{DiagnosticCode::unsupported,"family.assurance","No validated family verifier is implemented"}}};
    const auto id=request.problem.identity();
    const SynthesisIdentityExpectation expected{id,request.family,request.problem.constraints().coordinates(),
        request.configuration.strategy,request.strategy_version,std::nullopt};
    const FamilyIdentity validation_identity{id,request.family,request.problem.constraints().coordinates(),
        request.configuration.strategy,request.strategy_version,{}};
    auto answer=workspace.solve(request.problem,request.family,context);
    const bool supported_unbounded_with_lower_bound=answer.outcome.value==MathematicalOutcome::unbounded &&
        !std::holds_alternative<Unestablished>(answer.outcome.support) && answer.objective.lower &&
        supported_synthesis_bound(*answer.objective.lower,id);
    auto diagnostics=check_synthesis_result(answer,expected);
    if (diagnostics.empty()) return answer;
    // The workspace result is exclusively owned here and has not been published.
    // Keep its original stop before moving and sanitize only this unpublished value.
    SourceStopEvidence source_stop{};
    if (const auto* stopped=std::get_if<ScopedOperationStopped>(&answer.stop)) source_stop=*stopped;
    if (const auto* rejected=std::get_if<ScopedRequestRejection>(&answer.stop)) source_stop=*rejected;
    const bool inverted_bounds=answer.objective.lower.has_value() && answer.objective.upper.has_value() &&
        supported_synthesis_bound(*answer.objective.lower,id) &&
        supported_synthesis_bound(*answer.objective.upper,id) &&
        answer.objective.lower->value>answer.objective.upper->value;
    const bool lower_exceeds_incumbent=answer.objective.lower.has_value() &&
        supported_synthesis_bound(*answer.objective.lower,id) &&
        std::any_of(answer.incumbents.begin(),answer.incumbents.end(),[&](const FeasibleIncumbent& incumbent){
            return supported_feasible_incumbent(incumbent,validation_identity) &&
                incumbent.witness.original_objective<answer.objective.lower->value;
        });
    auto retained=std::move(answer);
    if (!check_outcome_evidence(retained.outcome,id,request.family.assurance).empty())
        retained.outcome={id,MathematicalOutcome::undetermined,Unestablished{}, {}};
    if (retained.objective.lower && !supported_synthesis_bound(*retained.objective.lower,id))
        retained.objective.lower.reset();
    if (retained.objective.upper && !supported_synthesis_bound(*retained.objective.upper,id))
        retained.objective.upper.reset();
    if (inverted_bounds) {
        retained.objective.lower.reset(); retained.objective.upper.reset();
    } else if (lower_exceeds_incumbent) retained.objective.lower.reset();
    std::erase_if(retained.incumbents,[&](const FeasibleIncumbent& incumbent) {
        return !supported_feasible_incumbent(incumbent,validation_identity);
    });
    if (retained.family && !check_family_evidence(*retained.family,id,request.family.assurance).empty())
        retained.family.reset();
    if (retained.family) {
        const auto& identity=retained.family->identity();
        if (identity.problem!=expected.problem || identity.request!=expected.request ||
            identity.coordinates!=expected.coordinates || identity.strategy!=expected.strategy ||
            identity.strategy_version!=expected.strategy_version) retained.family.reset();
    }
    if (retained.family && retained.family->target()==FamilyTarget::exact_optimal_relation) retained.family.reset();
    // A supported candidate or incumbent survives a contradictory solver status;
    // the rejected mathematical claim remains in the diagnostics, not the result.
    if ((retained.family || (!retained.incumbents.empty() &&
            retained.outcome.value==MathematicalOutcome::infeasible)) &&
        (retained.outcome.value==MathematicalOutcome::infeasible ||
            retained.outcome.value==MathematicalOutcome::unbounded ||
            retained.outcome.value==MathematicalOutcome::infimum_not_attained))
        retained.outcome={id,MathematicalOutcome::undetermined,Unestablished{}, {}};
    if (supported_unbounded_with_lower_bound)
        retained.outcome={id,MathematicalOutcome::undetermined,Unestablished{}, {}};
    const RetainedEvidenceScope scope{retained.objective.lower.has_value(),retained.objective.upper.has_value(),
        retained.incumbents.size(),retained.family.has_value()};
    retained.termination=Termination::contract_rejected;
    retained.stop=ContractValidationFailure{std::move(diagnostics),scope,std::move(source_stop)};
    return retained;
}
std::optional<Rejection> StrategyRegistry::add(StrategyRegistration entry) {
    Provenance provenance{StrategyPort::name,{entry.identity.id,entry.identity.version},entry.identity};
    if (entry.identity.id.value.empty() || entry.identity.version.empty() || !entry.capabilities || !entry.planner)
        return detail::reject(provenance,"registration","identity, version, capabilities and planner are required");
    const auto found = entries_.find(entry.identity.id.value);
    if (found != entries_.end()) {
        provenance.actual = found->second.identity;
        return detail::reject(provenance,"registration","method ID already registered");
    }
    entries_.emplace(entry.identity.id.value,std::move(entry));
    return {};
}
std::variant<PreparedStrategy,Rejection> StrategyRegistry::prepare(const StrategyRequest& request,
    const Requirements& requirements, std::optional<std::string> version) const {
    Provenance provenance{StrategyPort::name,{request.configuration.strategy,std::move(version)},{}};
    const auto found = entries_.find(request.configuration.strategy.value);
    if (found == entries_.end()) return detail::reject(provenance,"method","unknown strategy ID");
    const auto& entry = found->second;
    provenance.actual = entry.identity;
    if (provenance.requested.version && *provenance.requested.version != entry.identity.version)
        return detail::reject(provenance,"method.version","requested strategy version is unavailable");
    auto request_diagnostics=check_family_request(request.family,request.problem.identity());
    if (!request_diagnostics.empty()) return Rejection{provenance,std::move(request_diagnostics)};
    if ((requirements.output.family && *requirements.output.family!=request.family.target) ||
        requirements.output.assurance!=request.family.assurance)
        return detail::reject(provenance,"family","Registry requirements differ from the immutable effective family request");
    if (request.family.assurance==Assurance::validated)
        return detail::reject(provenance,"family.assurance","Validated family evidence is not implemented");
    auto verifier_key=entry.complete_family_verifier;
    if(requirements.output.completeness==Completeness::established&&entry.complete_family_verifier_selector) {
        const auto selected=entry.complete_family_verifier_selector(request);
        if(!selected)
            return detail::reject(provenance,"family.verifier.profile",
                "No compiled complete-family verifier is registered for this request profile");
        verifier_key=*selected;
    }
    const auto capability = entry.capabilities(request,requirements);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&capability)) return detail::capability_rejection(provenance,*diagnostics);
    auto diagnostics = detail::check_offer(std::get<Offer>(capability),requirements,false);
    if (!diagnostics.empty()) return Rejection{provenance,std::move(diagnostics)};
    auto verifier=verifier_key.id.value.empty()?nullptr:
        detail::find_compiled_verifier(verifier_key.id,verifier_key.version);
    if(requirements.output.completeness==Completeness::established&&!verifier)
        return detail::reject(provenance,"family.verifier","Complete-family output requires a verifier in the compiled library catalog");
    auto partial_verifier=entry.partial_family_verifier.id.value.empty()?nullptr:
        detail::find_compiled_partial_verifier(entry.partial_family_verifier.id,entry.partial_family_verifier.version);
    auto planned = entry.planner(request,requirements);
    if (const auto* rejection = std::get_if<Rejection>(&planned)) return *rejection;
    auto& plan = std::get<StrategyPlan>(planned);
    auto records = plan.provenance_;
    records.insert(records.begin(),provenance);
    // Every pure dependency/transition check has succeeded. Only now copy numerical requests.
    auto frozen=StrategyPort::snapshot(request);
    frozen.strategy_version=entry.identity.version;
    if(entry.expected_lineage) frozen.lineage=entry.expected_lineage(frozen);
    auto snapshot = std::make_shared<const StrategyRequest>(std::move(frozen));
    auto factory = plan.snapshot_();
    std::optional<detail::VerifiedFamilyAuthority> authority;
    if(verifier||partial_verifier)
        authority=detail::VerifiedFamilyAuthority(entry.identity.id,entry.identity.version);
    std::optional<detail::VerifiedPartialFamilyAuthority> partial_authority;
    if(partial_verifier)
        partial_authority=detail::VerifiedPartialFamilyAuthority(entry.identity.id,entry.identity.version,
            partial_verifier->id(),partial_verifier->version());
    return PreparedStrategy{std::move(snapshot),requirements,std::move(factory),std::move(verifier),
        std::move(authority),std::move(partial_verifier),std::move(partial_authority),std::move(records)};
}
namespace detail {
namespace {
Diagnostics compare_output(const Output& actual, const Output& required, const std::string& prefix) {
    auto failure = [&](const char* field, const char* reason) -> Diagnostics {
        return {{DiagnosticCode::unsupported,prefix+field,reason}};
    };
    if (actual.representation.value != required.representation.value)
        return failure("representation","selected output representation is incompatible");
    if (actual.assurance != required.assurance)
        return failure("assurance","selected output assurance is incompatible");
    if (required.relation && actual.relation != required.relation)
        return failure("relation","selected output relation is incompatible");
    if (required.family && actual.family != required.family)
        return failure("family","selected output family scope is incompatible");
    if (required.completeness && actual.completeness != required.completeness)
        return failure("completeness","selected output completeness is not established at the requested level");
    return {};
}
}
Diagnostics check_request_policy(const Requirements& required, bool has_basis, bool accepts_validated) {
    if (required.scalar != Scalar::binary64)
        return {{DiagnosticCode::unsupported,"scalar","only binary64 buffers are supported"}};
    if (required.output.assurance == Assurance::validated && !accepts_validated)
        return {{DiagnosticCode::unsupported,"output.assurance","selected port does not admit validated assurance"}};
    if (required.basis_diagnostics && !has_basis)
        return {{DiagnosticCode::unsupported,"basis","selected method has no basis diagnostics factory"}};
    return {};
}
Diagnostics check_offer(const Offer& offer, const Requirements& required, bool has_basis, bool accepts_validated) {
    auto diagnostics=check_request_policy(required,has_basis,accepts_validated);
    if (!diagnostics.empty()) return diagnostics;
    return compare_output(offer.output,required.output,"output.");
}
Diagnostics check_transition(const Output& actual, const Output& required) {
    return compare_output(actual,required,"transition.");
}
Rejection reject(Provenance provenance, std::string field, std::string reason) {
    return {std::move(provenance),{{DiagnosticCode::unsupported,std::move(field),std::move(reason)}}};
}
Rejection capability_rejection(Provenance provenance, Diagnostics diagnostics) {
    if (diagnostics.empty()) return reject(std::move(provenance),"capability","capability callback rejected without diagnostics");
    return {std::move(provenance),std::move(diagnostics)};
}
}
} // namespace csl::registry
