#include <csl/contracts.hpp>
#include <limits>
#include <cmath>
#include <utility>
namespace csl {
namespace {
template<class... Visitors> struct Overloaded : Visitors... { using Visitors::operator()...; };
bool matrix_matches(const Matrix& m, std::size_t rows, std::size_t cols) {
    return m.rows == rows && m.cols == cols &&
        (cols == 0 || rows <= std::numeric_limits<std::size_t>::max() / cols) &&
        m.values.size() == rows * cols;
}
struct OperationScope { std::vector<SetId> inputs; GeometryClaimScope claim; };
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
Diagnostics check_family_evidence(const OptimalFamily& family, const ProblemId& expected, Assurance assurance) {
    Diagnostics result;
    if (assurance == Assurance::validated)
        result.push_back({DiagnosticCode::unsupported,"assurance","Numerical checks, symbolic arguments and unchecked certificate references are not validated evidence"});
    if (family.identity.problem != expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"family.problem","Family does not belong to expected problem"});
    std::visit(Overloaded{
        [&](const CompleteOptimalFamily& complete) {
            if (complete.relation.coordinates != family.identity.coordinates ||
                complete.completeness.binding != family.identity ||
                complete.optimum.optimum.problem != expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.completeness.binding","Complete-family evidence does not bind the resolved problem, effective request, coordinates, strategy and ordered lineage"});
            if (complete.assurance != assurance)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.completeness.assurance","Claimed assurance differs from the request"});
            // The numerical coverage procedure and its acceptance thresholds have not
            // been reviewed. Neither a symbolic note nor a residual is a substitute.
            result.push_back({DiagnosticCode::unsupported,"family.completeness","Complete-family publication is disabled until reviewed coverage evidence is implemented"});
        },
        [&](const PartialOptimalFamily& partial) {
            if (partial.relation.coordinates != family.identity.coordinates ||
                partial.optimum.optimum.problem != expected ||
                partial.optimal_subset.every_history_optimal.problem != expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.partial","Partial-family evidence does not bind the joint relation and problem"});
            if (partial.known_scope.description.empty() || partial.optimal_subset.procedure.empty() ||
                std::holds_alternative<Unestablished>(partial.optimal_subset.every_history_optimal.support) ||
                std::holds_alternative<NumericalCheck>(partial.optimal_subset.every_history_optimal.support))
                result.push_back({DiagnosticCode::invalid_claim,"family.partial.optimality","An inner subset is not known optimal without scoped optimal-membership support"});
        },
        [&](const CandidateFamily& candidate) {
            if (candidate.relation.coordinates != family.identity.coordinates || candidate.feasibility.problem != expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate","Candidate relation does not bind the joint coordinates and problem"});
            std::visit(Overloaded{
                [&](const OuterCandidateEvidence& relation) { if (relation.enclosure.problem != expected)
                    result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.outer","Outer evidence is bound to another problem"}); },
                [&](const FeasibleCandidateEvidence& relation) { if (relation.feasibility.problem != expected)
                    result.push_back({DiagnosticCode::evidence_mismatch,"family.candidate.inner","Feasible-candidate evidence is bound to another problem"}); },
                [&](const HeuristicRelationEvidence& relation) { if (relation.method.empty())
                    result.push_back({DiagnosticCode::invalid_claim,"family.candidate.heuristic","Heuristic relation must name its method"}); }
            },candidate.relation_to_target);
        }
    },family.outcome);
    return result;
}
Diagnostics check_synthesis_result(const SynthesisResult& result,const FamilyIdentity& expected) {
    Diagnostics diagnostics=check_outcome_evidence(result.outcome,expected.problem,expected.request.assurance);
    auto add=[&](DiagnosticCode code,std::string field,std::string explanation) {
        diagnostics.push_back({code,std::move(field),std::move(explanation)});
    };
    for (const auto* bound : {&result.objective.lower,&result.objective.upper})
        if (*bound && ((*bound)->evidence.problem!=expected.problem || !std::isfinite((*bound)->value)))
            add(DiagnosticCode::evidence_mismatch,"result.objective","A retained bound has the wrong problem or a nonfinite value");
    if (result.objective.lower && result.objective.upper && result.objective.lower->value>result.objective.upper->value)
        add(DiagnosticCode::invalid_claim,"result.objective","Lower bound exceeds upper bound");
    for (const auto& incumbent:result.incumbents)
        if (incumbent.problem!=expected.problem || !std::isfinite(incumbent.original_objective))
            add(DiagnosticCode::evidence_mismatch,"result.incumbents","An incumbent has the wrong problem or a nonfinite objective");
    if (result.family) {
        auto identity=result.family->identity;
        identity.lineage.clear();
        if (identity!=expected)
            add(DiagnosticCode::evidence_mismatch,"family.identity","Family identity differs from the prepared problem, request, coordinates or strategy");
        auto family_diagnostics=check_family_evidence(*result.family,expected.problem,expected.request.assurance);
        diagnostics.insert(diagnostics.end(),family_diagnostics.begin(),family_diagnostics.end());
        if (result.family->target()==FamilyTarget::exact_optimal_relation &&
            (result.termination!=Termination::completed || result.outcome.value!=MathematicalOutcome::optimal))
            add(DiagnosticCode::invalid_claim,"family.complete","Only a completed, supported optimal outcome may carry a complete family");
        if (result.family->target()!=FamilyTarget::candidate_relaxation &&
            result.outcome.value!=MathematicalOutcome::optimal && result.outcome.value!=MathematicalOutcome::undetermined)
            add(DiagnosticCode::invalid_claim,"family.outcome","A nonoptimal mathematical outcome cannot carry an optimal-family product");
        if (expected.request.target!=FamilyTarget::exact_optimal_relation &&
            result.family->target()==FamilyTarget::exact_optimal_relation)
            add(DiagnosticCode::invalid_claim,"family.target","A result cannot upgrade the requested family target");
    }
    if (result.termination==Termination::operation_rejected) {
        if (!std::holds_alternative<ScopedRequestRejection>(result.stop))
            add(DiagnosticCode::invalid_claim,"result.stop","operation_rejected requires ScopedRequestRejection");
        else {
            const auto& rejected=std::get<ScopedRequestRejection>(result.stop);
            if (rejected.request.request.value.empty() || rejected.request.port.empty() || rejected.diagnostics.empty())
                add(DiagnosticCode::invalid_claim,"result.stop.rejection","Scoped rejection needs the exact request identity, port and provider diagnostic");
        }
    } else if (std::holds_alternative<ScopedRequestRejection>(result.stop))
        add(DiagnosticCode::invalid_claim,"result.stop","ScopedRequestRejection requires operation_rejected termination");
    if ((result.termination==Termination::cancelled || result.termination==Termination::deadline_expired ||
        result.termination==Termination::resource_limit) && std::holds_alternative<ScopedOperationStopped>(result.stop)) {
        const auto reason=std::get<ScopedOperationStopped>(result.stop).stop.reason;
        if ((result.termination==Termination::cancelled && reason!=StopReason::cancelled) ||
            (result.termination==Termination::deadline_expired && reason!=StopReason::deadline_expired) ||
            (result.termination==Termination::resource_limit && reason!=StopReason::resource_limit))
            add(DiagnosticCode::invalid_claim,"result.stop.reason","Execution termination and scoped stop reason differ");
    }
    return diagnostics;
}
Diagnostics check_resources(const ResourcePolicy& r) {
    if (r.total_threads == 0 || r.outer_workers == 0 || r.threads_per_worker == 0 ||
        r.outer_workers > r.total_threads / r.threads_per_worker)
        return {{DiagnosticCode::invalid_input,"resources","Positive worker/thread counts must fit the single total thread budget"}};
    return {};
}
}
