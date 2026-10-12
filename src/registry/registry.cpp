#include <csl/registry/registry.hpp>
#include <cmath>
#include <algorithm>

namespace csl::registry {
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
    if (!(request.family.numerical==context.numerical))
        return Unsupported{{{DiagnosticCode::invalid_input,"family.numerical","ExecutionContext numerical policy differs from the prepared family request"}}};
    if (request.family.assurance==Assurance::validated)
        return Unsupported{{{DiagnosticCode::unsupported,"family.assurance","No validated family verifier is implemented"}}};
    const auto id=request.problem.identity();
    const FamilyIdentity expected{id,request.family,request.problem.constraints().coordinates(),
        request.configuration.strategy,request.strategy_version,{}};
    auto answer=workspace.solve(request.problem,request.family,context);
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
            return supported_feasible_incumbent(incumbent,expected) &&
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
        return !supported_feasible_incumbent(incumbent,expected);
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
    if (request.family.objective!=request.problem.identity() || request.family.profile.empty() ||
        !std::isfinite(request.family.numerical.absolute_tolerance) ||
        !std::isfinite(request.family.numerical.relative_tolerance) ||
        request.family.numerical.absolute_tolerance<0 || request.family.numerical.relative_tolerance<0)
        return detail::reject(provenance,"family","Effective family request must bind the resolved objective/profile and finite nonnegative numerical policy");
    if ((requirements.output.family && *requirements.output.family!=request.family.target) ||
        requirements.output.assurance!=request.family.assurance)
        return detail::reject(provenance,"family","Registry requirements differ from the immutable effective family request");
    if (request.family.assurance==Assurance::validated)
        return detail::reject(provenance,"family.assurance","Validated family evidence is not implemented");
    const auto capability = entry.capabilities(request,requirements);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&capability)) return detail::capability_rejection(provenance,*diagnostics);
    auto diagnostics = detail::check_offer(std::get<Offer>(capability),requirements,false);
    if (!diagnostics.empty()) return Rejection{provenance,std::move(diagnostics)};
    auto planned = entry.planner(request,requirements);
    if (const auto* rejection = std::get_if<Rejection>(&planned)) return *rejection;
    auto& plan = std::get<StrategyPlan>(planned);
    auto records = plan.provenance_;
    records.insert(records.begin(),provenance);
    // Every pure dependency/transition check has succeeded. Only now copy numerical requests.
    auto frozen=StrategyPort::snapshot(request);
    frozen.strategy_version=entry.identity.version;
    auto snapshot = std::make_shared<const StrategyRequest>(std::move(frozen));
    auto factory = plan.snapshot_();
    return PreparedStrategy{std::move(snapshot),requirements,std::move(factory),std::move(records)};
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
Diagnostics check_request_policy(const Requirements& required, bool has_basis) {
    if (required.scalar != Scalar::binary64)
        return {{DiagnosticCode::unsupported,"scalar","only binary64 buffers are supported"}};
    if (required.output.assurance == Assurance::validated)
        return {{DiagnosticCode::unsupported,"output.assurance","revision 1.1 has no validated evidence interface"}};
    if (required.basis_diagnostics && !has_basis)
        return {{DiagnosticCode::unsupported,"basis","selected method has no basis diagnostics factory"}};
    return {};
}
Diagnostics check_offer(const Offer& offer, const Requirements& required, bool has_basis) {
    auto diagnostics=check_request_policy(required,has_basis);
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
