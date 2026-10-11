#include <csl/contracts.hpp>
#include <limits>
#include <utility>
namespace csl {
Diagnostics check_model_shape(const Dynamics& dynamics, std::size_t horizon) {
    Diagnostics result;
    auto matrix_matches = [](const Matrix& m, std::size_t rows, std::size_t cols) {
        return m.rows == rows && m.cols == cols &&
            (cols == 0 || rows <= std::numeric_limits<std::size_t>::max() / cols) &&
            m.values.size() == rows * cols;
    };
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
    if (family.problem != expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"family.problem","Family does not belong to expected problem"});
    for (const auto* claim : {&family.evidence.feasibility,&family.evidence.optimality,&family.evidence.completeness})
        if (claim->problem != expected)
            result.push_back({DiagnosticCode::evidence_mismatch,"family.evidence","Claim does not belong to expected problem"});
    const auto& coverage = family.evidence.completeness.support;
    if ((family.target != FamilyTarget::exact_optimal_relation && !std::holds_alternative<Unestablished>(coverage)) ||
        std::holds_alternative<NumericalCheck>(coverage))
        result.push_back({DiagnosticCode::invalid_claim,"family.completeness","Partial/relaxed relations or numerical witness checks cannot establish full optimal-family coverage"});
    return result;
}
Diagnostics check_resources(const ResourcePolicy& r) {
    if (r.total_threads == 0 || r.outer_workers == 0 || r.threads_per_worker == 0 ||
        r.outer_workers > r.total_threads / r.threads_per_worker)
        return {{DiagnosticCode::invalid_input,"resources","Positive worker/thread counts must fit the single total thread budget"}};
    return {};
}
}
