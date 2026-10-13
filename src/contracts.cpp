#include <csl/contracts.hpp>
#include <limits>
#include <cmath>
#include <utility>
#include <set>
#include <algorithm>
namespace csl {
namespace {
template<class... Visitors> struct Overloaded : Visitors... { using Visitors::operator()...; };
bool matrix_matches(const Matrix& m, std::size_t rows, std::size_t cols) {
    return m.rows == rows && m.cols == cols &&
        (cols == 0 || rows <= std::numeric_limits<std::size_t>::max() / cols) &&
        m.values.size() == rows * cols;
}
struct OperationScope { std::vector<SetId> inputs; GeometryClaimScope claim; };
bool valid_lineage(const std::vector<TransformStepIdentity>& lineage) {
    std::set<std::string> requests;
    for (const auto& step:lineage)
        if (step.request.value.empty() || step.input.value.empty() || step.output.value.empty() ||
            step.module.value.empty() || step.version.empty() ||
            !requests.insert(step.request.value).second)
            return false;
    return true;
}
bool valid_request_provenance(const RequestProvenance& provenance) {
    return !provenance.request.value.empty() && !provenance.port.empty() &&
        !provenance.requested_module.value.empty() &&
        (!provenance.requested_version || !provenance.requested_version->empty()) &&
        provenance.actual_module.has_value()==provenance.actual_version.has_value() &&
        (!provenance.actual_module || !provenance.actual_module->value.empty()) &&
        (!provenance.actual_version || !provenance.actual_version->empty());
}
OperationScope operation_scope(const GeometryOperation& operation) {
    return std::visit(Overloaded{
        [](const AffineImage& op) { return OperationScope{{op.input.id},GeometryClaimScope::set_relation}; },
        [](const MinkowskiSum& op) { return OperationScope{{op.left.id,op.right.id},GeometryClaimScope::set_relation}; },
        [](const Intersection& op) { return OperationScope{{op.left.id,op.right.id},GeometryClaimScope::set_relation}; },
        [](const Projection& op) { return OperationScope{{op.input.id},GeometryClaimScope::set_relation}; },
        [](const AffinePreimage& op) { return OperationScope{{op.target.id},GeometryClaimScope::set_relation}; },
        [](const SupportQuery& op) { return OperationScope{{op.input.id},GeometryClaimScope::support_value}; },
        [](const ContainmentQuery& op) { return OperationScope{{op.subset.id,op.superset.id},GeometryClaimScope::containment}; }
    },operation);
}
Diagnostics check_geometry_binding(const GeometryEvidence& evidence, const GeometryReference& reference,
                                   GeometryClaimScope scope, Assurance assurance) {
    Diagnostics result;
    if (evidence.reference != reference || evidence.scope != scope)
        result.push_back({DiagnosticCode::evidence_mismatch,"geometry.reference","Evidence does not identify the requested operation, ordered inputs, ideal output and claim scope"});
    if (assurance == Assurance::validated)
        result.push_back({DiagnosticCode::unsupported,"geometry.assurance","No validated geometry verifier is implemented"});
    if (evidence.error_bound && (!std::isfinite(evidence.error_bound->bound) || evidence.error_bound->bound < 0 ||
        std::holds_alternative<Unestablished>(evidence.support)))
        result.push_back({DiagnosticCode::invalid_claim,"geometry.error_bound","A finite nonnegative error bound requires claim support; this check does not verify the bound"});
    return result;
}
template<class Subject>
Diagnostics check_outcome(const OutcomeClaim<Subject>& claim, const Subject& expected, Assurance assurance) {
    Diagnostics result;
    if (claim.subject != expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"outcome.subject","Outcome claim does not belong to the expected problem/program"});
    if (assurance == Assurance::validated)
        result.push_back({DiagnosticCode::unsupported,"outcome.assurance","Outcome support is unestablished, numerical, symbolic provenance or an unchecked certificate, not validated evidence"});
    return result;
}
} // namespace
Diagnostics check_operation_shape(const OperationRequest& request) {
    const bool valid = std::visit(Overloaded{
        [](const AffineImage& op) {
            return matrix_matches(op.map,op.map.rows,op.input.metadata.dimension) && op.offset.size() == op.map.rows;
        },
        [](const MinkowskiSum& op) { return op.left.metadata.dimension == op.right.metadata.dimension; },
        [](const Intersection& op) { return op.left.metadata.dimension == op.right.metadata.dimension; },
        [](const Projection& op) {
            for (const auto coordinate : op.coordinates) if (coordinate >= op.input.metadata.dimension) return false;
            return true;
        },
        [](const AffinePreimage& op) {
            return matrix_matches(op.map,op.target.metadata.dimension,op.map.cols) && op.offset.size() == op.map.rows;
        },
        [](const SupportQuery& op) { return op.direction.size() == op.input.metadata.dimension; },
        [](const ContainmentQuery& op) { return op.subset.metadata.dimension == op.superset.metadata.dimension; }
    },request.operation);
    if (!valid) return {{DiagnosticCode::invalid_input,"geometry.operands","Operation shapes, buffer storage or coordinates do not match the input dimensions"}};
    return {};
}
Diagnostics check_geometry_evidence(const GeometryEvidence& evidence, const OperationRequest& request) {
    const auto scope = operation_scope(request.operation);
    return check_geometry_binding(evidence,{request.identity,scope.inputs},scope.claim,request.assurance);
}
Diagnostics check_geometry_evidence(const GeometryEvidence& evidence, const ConversionRequest& request) {
    return check_geometry_binding(evidence,{request.identity,{request.input.id}},GeometryClaimScope::set_relation,request.assurance);
}
Diagnostics check_geometry_evidence(const GeometryEvidence& evidence, const ApproximationRequest& request) {
    return check_geometry_binding(evidence,{request.identity,{request.input.id}},GeometryClaimScope::set_relation,request.assurance);
}
Diagnostics check_outcome_evidence(const ProgramOutcomeClaim& claim, const ProgramIdentity& expected, Assurance assurance) {
    return check_outcome(claim,expected,assurance);
}
Diagnostics check_outcome_evidence(const SynthesisOutcomeClaim& claim, const ProblemId& expected, Assurance assurance) {
    return check_outcome(claim,expected,assurance);
}
Diagnostics check_model_shape(const Dynamics& dynamics, std::size_t horizon) {
    Diagnostics result;
    auto check = [&](const LinearStage& stage) {
        const auto [n,m,p] = dynamics.dimensions;
        if (!matrix_matches(stage.A,n,n) || !matrix_matches(stage.B,n,m) ||
            !matrix_matches(stage.E,n,p) || stage.offset.size() != n)
            result.push_back({DiagnosticCode::invalid_input,"dynamics.stages","Coefficient shapes or storage do not match dimensions"});
    };
    if (auto constant = std::get_if<LinearStage>(&dynamics.stages)) check(*constant);
    else {
        const auto& stages = std::get<std::vector<LinearStage>>(dynamics.stages);
        if (stages.size() != horizon)
            result.push_back({DiagnosticCode::invalid_input,"dynamics.stages","Expected T stage coefficients"});
        for (const auto& stage : stages) check(stage);
    }
    return result;
}
Diagnostics check_nominal_profile(const Problem& p, bool requires_inverse, Assurance assurance) {
    Diagnostics result;
    auto unsupported = [&](std::string field, std::string explanation) {
        result.push_back({DiagnosticCode::unsupported,std::move(field),std::move(explanation)});
    };
    if (!p.model) return {{DiagnosticCode::invalid_input,"model","Model snapshot is required"}};
    if (p.model->dynamics.time_domain != TimeDomain::discrete)
        unsupported("time_domain","Only supplied discrete transitions are supported");
    if (requires_inverse)
        unsupported("dynamics.inverse","Revision 1 supplies no invertibility proof; choose a pipeline not requiring inverse dynamics");
    if (!std::holds_alternative<KnownInitial>(p.initial))
        unsupported("initial","Known initial point required");
    if (p.information != InformationPattern::nominal_open_loop)
        unsupported("information","Nominal open-loop profile required");
    if (p.external || p.model->dynamics.dimensions.external != 0)
        unsupported("external","External-input semantics require another capability profile");
    if (p.temporal && p.temporal->joint_map.rows != 0)
        unsupported("temporal","Nonempty temporal constraints require a compatible lift");
    auto polyhedral = [](const AdmissibleSet& set) {
        auto handle = std::get_if<SetHandle>(&set);
        return !handle || (handle->metadata.convex == SetProperty::yes && handle->metadata.polyhedral == SetProperty::yes);
    };
    if (auto continuous = std::get_if<ContinuousDomain>(&p.controls)) {
        for (const auto& set : continuous->stages)
            if (!polyhedral(set)) unsupported("controls","Convex polyhedral stage sets required");
    } else unsupported("controls","Continuous controls required; finite/mixed domains are not silently convexified");
    for (const auto& set : p.states)
        if (!polyhedral(set)) unsupported("states","Convex polyhedral stage sets required");
    if (assurance == Assurance::validated)
        unsupported("assurance","No validated verifier is implemented in revision 1");
    return result;
}
Diagnostics check_family_request(const FamilyRequest& request,const ProblemId& expected) {
    Diagnostics result;
    if (expected.value.empty() || request.objective!=expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"family.objective",
            "Effective family objective must bind the resolved problem"});
    if (request.profile.empty())
        result.push_back({DiagnosticCode::invalid_input,"family.profile","Effective family profile is required"});
    if (!std::isfinite(request.numerical.absolute_tolerance) ||
        !std::isfinite(request.numerical.relative_tolerance) ||
        request.numerical.absolute_tolerance<0 || request.numerical.relative_tolerance<0)
        result.push_back({DiagnosticCode::invalid_input,"family.numerical",
            "Effective numerical policy requires finite nonnegative tolerances"});
    return result;
}
Diagnostics check_family_evidence(const OptimalFamily& family, const ProblemId& expected, Assurance assurance) {
    const auto& identity=family.identity();
    auto result=check_family_request(identity.request,expected);
    if (assurance == Assurance::validated)
        result.push_back({DiagnosticCode::unsupported,"assurance","Numerical checks, symbolic arguments and unchecked certificate references are not validated evidence"});
    if (identity.problem != expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"family.problem","Family does not belong to expected problem"});
    if (identity.problem.value.empty() || identity.request.objective!=identity.problem ||
        identity.request.profile.empty() || identity.strategy.value.empty() || identity.strategy_version.empty())
        result.push_back({DiagnosticCode::evidence_mismatch,"family.identity",
            "Publisher needs a resolved objective, effective request profile and strategy identity"});
    if (!valid_lineage(identity.lineage))
        result.push_back({DiagnosticCode::invalid_claim,"family.lineage",
            "Ordered transformation lineage requires distinct nonempty request and input/output/module/version identities"});
    std::visit(Overloaded{
        [&](const CompleteOptimalFamily& complete) {
            if (complete.relation.coordinates != identity.coordinates ||
                complete.completeness.binding != identity ||
                complete.optimum.optimum.problem != expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.completeness.binding","Complete-family evidence does not bind the resolved problem, effective request, coordinates, strategy and ordered lineage"});
            if (complete.assurance != assurance)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.completeness.assurance","Claimed assurance differs from the request"});
            if (std::holds_alternative<Unestablished>(complete.optimum.optimum.support))
                result.push_back({DiagnosticCode::invalid_claim,"family.optimum","Complete-family optimum needs supporting evidence"});
            // The numerical coverage procedure and its acceptance thresholds have not
            // been reviewed. Neither a symbolic note nor a residual is a substitute.
            result.push_back({DiagnosticCode::unsupported,"family.completeness","Complete-family publication is disabled until reviewed coverage evidence is implemented"});
        },
        [&](const PartialOptimalFamily& partial) {
            if (partial.relation.coordinates != identity.coordinates ||
                partial.optimum.optimum.problem != expected ||
                partial.optimal_subset.every_history_optimal.problem != expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.partial","Partial-family evidence does not bind the joint relation and problem"});
            if (partial.known_scope.description.empty() || partial.optimal_subset.procedure.empty() ||
                std::holds_alternative<Unestablished>(partial.optimum.optimum.support) ||
                std::holds_alternative<Unestablished>(partial.optimal_subset.every_history_optimal.support) ||
                std::holds_alternative<NumericalCheck>(partial.optimal_subset.every_history_optimal.support))
                result.push_back({DiagnosticCode::invalid_claim,"family.partial.optimality","An inner subset is not known optimal without scoped optimal-membership support"});
            result.push_back({DiagnosticCode::unsupported,"family.partial.optimality",
                "No reviewed verifier can establish that every history in a partial relation is optimal"});
        },
        [&](const CandidateFamily& candidate) {
            if (candidate.relation.coordinates != identity.coordinates)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate","Candidate relation does not bind the joint coordinates and problem"});
            std::visit(Overloaded{
                [&](const Unestablished&) {},
                [&](const RelationFeasibilityEvidence& feasibility) {
                    if (feasibility.support.problem!=expected ||
                        std::holds_alternative<Unestablished>(feasibility.support.support))
                        result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.feasibility.relation",
                            "Whole-relation feasibility needs supported evidence for this problem"});
                },
                [&](const WitnessFeasibilityEvidence& feasibility) {
                    if (feasibility.support.problem!=expected || feasibility.witness.problem!=expected ||
                        std::holds_alternative<Unestablished>(feasibility.support.support) ||
                        !std::isfinite(feasibility.witness.original_objective) ||
                        identity.coordinates.horizon==std::numeric_limits<std::size_t>::max() ||
                        feasibility.witness.states.size()!=identity.coordinates.horizon+1 ||
                        feasibility.witness.controls.size()!=identity.coordinates.horizon ||
                        std::any_of(feasibility.witness.states.begin(),feasibility.witness.states.end(),[&](const Vector& state){
                            return state.size()!=identity.coordinates.dimensions.state ||
                                std::any_of(state.begin(),state.end(),[](double value){return !std::isfinite(value);});}) ||
                        std::any_of(feasibility.witness.controls.begin(),feasibility.witness.controls.end(),[&](const Vector& control){
                            return control.size()!=identity.coordinates.dimensions.control ||
                                std::any_of(control.begin(),control.end(),[](double value){return !std::isfinite(value);});}))
                        result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.feasibility.witness",
                            "Witness-scoped feasibility needs a supported full history for this problem"});
                }
            },candidate.feasibility);
            std::visit(Overloaded{
                [&](const OuterCandidateEvidence& relation) { if (relation.enclosure.problem != expected)
                    result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.outer","Outer evidence is bound to another problem"});
                    else if (std::holds_alternative<Unestablished>(relation.enclosure.support))
                    result.push_back({DiagnosticCode::invalid_claim,"family.candidate.outer","Outer enclosure needs supporting evidence"}); },
                [&](const FeasibleCandidateEvidence& relation) { if (relation.feasibility.problem != expected)
                    result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.inner","Feasible-candidate evidence is bound to another problem"});
                    else if (std::holds_alternative<Unestablished>(relation.feasibility.support))
                    result.push_back({DiagnosticCode::invalid_claim,"family.candidate.inner","Inner feasibility needs supporting evidence"});
                    if (!std::holds_alternative<RelationFeasibilityEvidence>(candidate.feasibility))
                        result.push_back({DiagnosticCode::invalid_claim,"family.candidate.feasibility.relation",
                            "A feasible inner relation needs whole-relation feasibility, not only a witness"}); },
                [&](const HeuristicRelationEvidence& relation) { if (relation.method.empty())
                    result.push_back({DiagnosticCode::invalid_claim,"family.candidate.heuristic","Heuristic relation must name its method"}); }
            },candidate.relation_to_target);
        }
    },family.outcome());
    const auto* relation=std::visit([](const auto& product)->const JointRelation*{return &product.relation;},family.outcome());
    if (relation->representation!=identity.request.representation)
        result.push_back({DiagnosticCode::evidence_mismatch,"family.representation",
            "Published relation representation differs from the effective family request"});
    return result;
}
std::variant<OptimalFamily,Diagnostics> FamilyPublisher::publish(FamilyIdentity identity,OptimalFamilyOutcome outcome) {
    OptimalFamily proposed{std::move(identity),std::move(outcome)};
    auto diagnostics=check_family_evidence(proposed,proposed.identity().problem,proposed.identity().request.assurance);
    if (!diagnostics.empty()) return diagnostics;
    return proposed;
}
bool supported_synthesis_bound(const ObjectiveBound& bound,const ProblemId& problem) {
    return bound.evidence.problem==problem && std::isfinite(bound.value) &&
        !std::holds_alternative<Unestablished>(bound.evidence.support);
}
bool supported_feasible_incumbent(const FeasibleIncumbent& incumbent,const FamilyIdentity& expected) {
    const auto& witness=incumbent.witness;
    const auto& coordinates=expected.coordinates;
    if (witness.problem!=expected.problem || incumbent.feasibility.problem!=expected.problem ||
        std::holds_alternative<Unestablished>(incumbent.feasibility.support) ||
        !std::isfinite(witness.original_objective) ||
        coordinates.horizon==std::numeric_limits<std::size_t>::max() ||
        witness.states.size()!=coordinates.horizon+1 || witness.controls.size()!=coordinates.horizon)
        return false;
    const auto finite_dimension=[](const Vector& values,std::size_t dimension) {
        return values.size()==dimension &&
            std::all_of(values.begin(),values.end(),[](double value){return std::isfinite(value);});
    };
    return std::all_of(witness.states.begin(),witness.states.end(),[&](const Vector& state){
            return finite_dimension(state,coordinates.dimensions.state);}) &&
        std::all_of(witness.controls.begin(),witness.controls.end(),[&](const Vector& control){
            return finite_dimension(control,coordinates.dimensions.control);});
}
Diagnostics check_synthesis_result(const SynthesisResult& result,const FamilyIdentity& expected) {
    return check_synthesis_result(result,SynthesisIdentityExpectation{expected.problem,expected.request,
        expected.coordinates,expected.strategy,expected.strategy_version,expected.lineage});
}
Diagnostics check_synthesis_result(const SynthesisResult& result,const SynthesisIdentityExpectation& expected) {
    Diagnostics diagnostics=check_outcome_evidence(result.outcome,expected.problem,expected.request.assurance);
    const FamilyIdentity expected_identity{expected.problem,expected.request,expected.coordinates,
        expected.strategy,expected.strategy_version,expected.lineage.value_or(std::vector<TransformStepIdentity>{})};
    auto add=[&](DiagnosticCode code,std::string field,std::string explanation) {
        diagnostics.push_back({code,std::move(field),std::move(explanation)});
    };
    for (const auto* bound : {&result.objective.lower,&result.objective.upper})
        if (*bound && !supported_synthesis_bound(**bound,expected.problem))
            add(DiagnosticCode::evidence_mismatch,"result.objective","A retained bound needs finite value, matching problem and stated support");
    if (result.objective.lower && result.objective.upper && result.objective.lower->value>result.objective.upper->value)
        add(DiagnosticCode::invalid_claim,"result.objective","Lower bound exceeds upper bound");
    for (const auto& incumbent:result.incumbents)
        if (!supported_feasible_incumbent(incumbent,expected_identity))
            add(DiagnosticCode::evidence_mismatch,"result.incumbents",
                "An incumbent needs matching problem, supported feasibility and a finite full history in canonical dimensions");
    if (result.outcome.value==MathematicalOutcome::infeasible &&
        std::any_of(result.incumbents.begin(),result.incumbents.end(),[&](const FeasibleIncumbent& incumbent){
            return supported_feasible_incumbent(incumbent,expected_identity);
        }))
        add(DiagnosticCode::invalid_claim,"result.outcome.infeasible",
            "A supported feasible incumbent contradicts an infeasibility claim");
    if (result.objective.lower && supported_synthesis_bound(*result.objective.lower,expected.problem) &&
        std::any_of(result.incumbents.begin(),result.incumbents.end(),[&](const FeasibleIncumbent& incumbent){
            return supported_feasible_incumbent(incumbent,expected_identity) &&
                incumbent.witness.original_objective<result.objective.lower->value;
        }))
        add(DiagnosticCode::invalid_claim,"result.objective.lower",
            "A supported feasible incumbent has objective below the claimed lower bound");
    if (result.family) {
        const auto& identity=result.family->identity();
        if (identity.problem!=expected.problem || identity.request!=expected.request ||
            identity.coordinates!=expected.coordinates || identity.strategy!=expected.strategy ||
            identity.strategy_version!=expected.strategy_version ||
            (expected.lineage && identity.lineage!=*expected.lineage))
            add(DiagnosticCode::evidence_mismatch,"family.identity","Family identity differs from the prepared problem, request, coordinates, strategy or ordered transformation lineage");
        auto family_diagnostics=check_family_evidence(*result.family,expected.problem,expected.request.assurance);
        diagnostics.insert(diagnostics.end(),family_diagnostics.begin(),family_diagnostics.end());
        if (result.family->target()==FamilyTarget::exact_optimal_relation &&
            (result.termination!=Termination::completed || result.outcome.value!=MathematicalOutcome::optimal))
            add(DiagnosticCode::invalid_claim,"family.complete","Only a completed, supported optimal outcome may carry a complete family");
        if (result.outcome.value==MathematicalOutcome::infeasible ||
            result.outcome.value==MathematicalOutcome::unbounded ||
            result.outcome.value==MathematicalOutcome::infimum_not_attained)
            add(DiagnosticCode::invalid_claim,"family.outcome","This mathematical outcome cannot carry an optimal-family product");
        if ((expected.request.target!=FamilyTarget::exact_optimal_relation &&
            result.family->target()==FamilyTarget::exact_optimal_relation) ||
            (expected.request.target==FamilyTarget::candidate_relaxation &&
            result.family->target()==FamilyTarget::partial_relation))
            add(DiagnosticCode::invalid_claim,"family.target","A result cannot upgrade the requested family target");
    }
    if (result.termination==Termination::operation_rejected) {
        if (!std::holds_alternative<ScopedRequestRejection>(result.stop))
            add(DiagnosticCode::invalid_claim,"result.stop","operation_rejected requires ScopedRequestRejection");
        else {
            const auto& rejected=std::get<ScopedRequestRejection>(result.stop);
            if (!valid_request_provenance(rejected.request))
                add(DiagnosticCode::invalid_claim,"result.stop.provenance",
                    "Scoped rejection requires requested provider identity and paired nonempty actual module/version when available");
            if (rejected.request.request.value.empty() || rejected.request.port.empty() || rejected.diagnostics.empty())
                add(DiagnosticCode::invalid_claim,"result.stop.rejection","Scoped rejection needs the exact request identity, port and provider diagnostic");
            if (!valid_lineage(rejected.completed_lineage))
                add(DiagnosticCode::invalid_claim,"result.stop.rejection.lineage",
                    "Completed transformation lineage requires distinct nonempty request and input/output/module/version identities");
            const RetainedEvidenceScope observed{result.objective.lower.has_value(),result.objective.upper.has_value(),
                result.incumbents.size(),result.family.has_value()};
            if (rejected.retained.lower_bound!=observed.lower_bound ||
                rejected.retained.upper_bound!=observed.upper_bound ||
                rejected.retained.incumbents!=observed.incumbents ||
                rejected.retained.partial_or_candidate_family!=observed.partial_or_candidate_family)
                add(DiagnosticCode::evidence_mismatch,"result.stop.retained","Retained-evidence scope differs from the result payload");
        }
    } else if (std::holds_alternative<ScopedRequestRejection>(result.stop))
        add(DiagnosticCode::invalid_claim,"result.stop","ScopedRequestRejection requires operation_rejected termination");
    if (result.termination==Termination::contract_rejected) {
        if (!std::holds_alternative<ContractValidationFailure>(result.stop))
            add(DiagnosticCode::invalid_claim,"result.stop","contract_rejected requires ContractValidationFailure");
        else {
            const auto& failure=std::get<ContractValidationFailure>(result.stop);
            const RetainedEvidenceScope observed{result.objective.lower.has_value(),result.objective.upper.has_value(),
                result.incumbents.size(),result.family.has_value()};
            if (failure.diagnostics.empty() || failure.retained.lower_bound!=observed.lower_bound ||
                failure.retained.upper_bound!=observed.upper_bound || failure.retained.incumbents!=observed.incumbents ||
                failure.retained.partial_or_candidate_family!=observed.partial_or_candidate_family)
                add(DiagnosticCode::evidence_mismatch,"result.stop.contract","Contract failure needs diagnostics and exact retained scope");
        }
    } else if (std::holds_alternative<ContractValidationFailure>(result.stop))
        add(DiagnosticCode::invalid_claim,"result.stop","ContractValidationFailure requires contract_rejected termination");
    if (result.termination==Termination::cancelled || result.termination==Termination::resource_limit ||
        result.termination==Termination::numerical_failure) {
        if (!std::holds_alternative<ScopedOperationStopped>(result.stop))
            add(DiagnosticCode::invalid_claim,"result.stop","Cancelled, deadline and resource stops require scoped stop evidence");
        else {
        const auto reason=std::get<ScopedOperationStopped>(result.stop).stop.reason;
        if ((result.termination==Termination::cancelled && reason!=StopReason::cancelled &&
                reason!=StopReason::deadline_expired) ||
            (result.termination==Termination::resource_limit && reason!=StopReason::resource_limit) ||
            (result.termination==Termination::numerical_failure && reason!=StopReason::numerical_failure))
            add(DiagnosticCode::invalid_claim,"result.stop.reason","Execution termination and scoped stop reason differ");
        const auto& stopped=std::get<ScopedOperationStopped>(result.stop);
        if (!valid_request_provenance(stopped.request))
            add(DiagnosticCode::invalid_claim,"result.stop.provenance",
                "Scoped stop requires requested provider identity and paired nonempty actual module/version when available");
        const RetainedEvidenceScope observed{result.objective.lower.has_value(),result.objective.upper.has_value(),
            result.incumbents.size(),result.family.has_value()};
        if (stopped.request.request.value.empty() || stopped.request.port.empty() || stopped.stop.diagnostics.empty() ||
            stopped.retained.lower_bound!=observed.lower_bound || stopped.retained.upper_bound!=observed.upper_bound ||
            stopped.retained.incumbents!=observed.incumbents ||
            stopped.retained.partial_or_candidate_family!=observed.partial_or_candidate_family)
            add(DiagnosticCode::evidence_mismatch,"result.stop.retained","Scoped stop must name its source, diagnostics and actual retained payload");
        }
    } else if (std::holds_alternative<ScopedOperationStopped>(result.stop))
        add(DiagnosticCode::invalid_claim,"result.stop","ScopedOperationStopped requires a matching stopped termination");
    return diagnostics;
}
Diagnostics check_resources(const ResourcePolicy& r) {
    if (r.total_threads == 0 || r.outer_workers == 0 || r.threads_per_worker == 0 ||
        r.outer_workers > r.total_threads / r.threads_per_worker)
        return {{DiagnosticCode::invalid_input,"resources","Positive worker/thread counts must fit the single total thread budget"}};
    return {};
}
}
