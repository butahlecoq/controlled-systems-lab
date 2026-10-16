#include <csl/geometry/approximation.hpp>
#include <csl/sets/data.hpp>

namespace csl::geometry::approximation {
namespace {
Diagnostics error(DiagnosticCode code, const char* field, const char* message) {
    return {{code,field,message}};
}
bool same_metadata(const SetMetadata& left,const SetMetadata& right) {
    return left.dimension==right.dimension && left.representation==right.representation &&
        left.convex==right.convex && left.polyhedral==right.polyhedral && left.bounded==right.bounded;
}
std::optional<StructuralBasis> structural_basis(const ApproximationRequest& request,
                                                 const OperationResult& result) {
    if(request.input.id==result.output.id && request.input.payload==result.output.payload &&
       same_metadata(request.input.metadata,result.output.metadata))
        return StructuralBasis::identical_set;
    const auto reference=sets::from_handle(request.input);
    const auto native=sets::from_handle(result.output);
    if(const auto* source=std::get_if<sets::SetData>(&reference);
       source && std::holds_alternative<sets::SetData>(native) &&
       source->metadata()->coordinate_labels==
           std::get<sets::SetData>(native).metadata()->coordinate_labels) {
        const auto* data=std::get_if<sets::SetData>(&native);
        const auto representation=data->representation();
        if(request.direction==SetRelation::inner &&
            (std::holds_alternative<sets::EmptyRepresentation>(representation) ||
             (std::holds_alternative<sets::VRepresentation>(representation) &&
              std::get<sets::VRepresentation>(representation).vertices.rows()==0)))
            return StructuralBasis::empty_subset;
        if(request.direction==SetRelation::outer &&
            std::holds_alternative<sets::UniversalRepresentation>(representation))
            return StructuralBasis::universal_superset;
    }
    return std::nullopt;
}
bool within_budget(const SetHandle& output,std::size_t budget) {
    const auto native=sets::from_handle(output);
    const auto* data=std::get_if<sets::SetData>(&native);
    if(!data)return false;
    const auto representation=data->representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
        return h->inequalities.rows()<=budget &&
            h->equalities.rows()<=budget-h->inequalities.rows();
    if(const auto* v=std::get_if<sets::VRepresentation>(&representation))
        return v->vertices.rows()<=budget && v->rays.rows()<=budget-v->vertices.rows();
    if(std::holds_alternative<sets::SingletonRepresentation>(representation))return budget>=1;
    return true; // Empty and universal have no stored primitives.
}
registry::Rejection reject(const registry::Method& method,const char* field,const char* message) {
    return {{registry::ApproximationPort::name,method,{}},error(DiagnosticCode::unsupported,field,message)};
}
}

RunOutcome run_registered(const registry::Registry<registry::ApproximationPort>& registry,
                          registry::Method method,const ApproximationRequest& request,
                          const ExecutionContext& context) {
    if(request.direction==SetRelation::equivalent)
        return reject(method,"approximation.direction","Equivalent conversion belongs to ConversionPort.");
    if(request.identity.problem.value.empty() || request.identity.request.value.empty() ||
       request.identity.ideal_output.value.empty() || request.input.id.value.empty() ||
       !request.input.payload || request.output.value.empty())
        return reject(method,"approximation.request","A complete reference, input and output representation are required.");
    registry::Requirements requirements;
    requirements.output.representation=request.output;
    requirements.output.assurance=request.assurance;
    requirements.output.relation=request.direction;
    auto prepared=registry::prepare_pipeline(registry::select(registry,std::move(method),request,requirements));
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))return *rejected;
    auto workspace=std::get<registry::PreparedPipeline<registry::ApproximationPort>>(std::move(prepared)).create();
    auto outcome=std::get<0>(workspace)->run(context);
    if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
    if(const auto* unsupported=std::get_if<Unsupported>(&outcome))return *unsupported;
    auto result=std::get<OperationResult>(std::move(outcome));
    if(result.relation!=request.direction)
        return Unsupported{error(DiagnosticCode::evidence_mismatch,"approximation.relation",
            "Provider result differs from the requested relation.")};
    if(auto diagnostics=check_geometry_evidence(result.evidence,request);!diagnostics.empty())
        return Unsupported{std::move(diagnostics)};
    if(result.evidence.error_bound)
        return Unsupported{error(DiagnosticCode::unsupported,"approximation.error_bound",
            "No independent approximation error-bound verifier is available.")};
    if(result.output.id.value.empty() || !result.output.payload ||
       result.output.metadata.dimension!=request.input.metadata.dimension ||
       result.output.metadata.representation!=request.output)
        return Unsupported{error(DiagnosticCode::evidence_mismatch,"approximation.output",
            "Output identity, payload, dimension or representation differs from the request.")};
    if(!within_budget(result.output,request.size_budget))
        return Unsupported{error(DiagnosticCode::unsupported,"approximation.budget",
            "Native output exceeds the requested primitive budget, or output size is unavailable.")};
    if(request.direction==SetRelation::heuristic)return HeuristicApproximation{std::move(result)};
    if(const auto basis=structural_basis(request,result)) {
        result.evidence.support=SymbolicArgument{"CSL native elementary-set identity/inclusion check",
            "Same immutable set, empty subset, or universal superset over the same ambient coordinates."};
        return EnclosedApproximation{std::move(result),*basis};
    }
    return Unsupported{error(DiagnosticCode::unsupported,"approximation.inclusion",
        "Requested enclosure has no independently checkable inclusion evidence.")};
}

BoundSide objective_bound_side(SetRelation relation,ObjectiveSense sense) noexcept {
    switch(relation) {
    case SetRelation::equivalent: return BoundSide::both;
    case SetRelation::heuristic: return BoundSide::none;
    case SetRelation::inner: return sense==ObjectiveSense::minimize?BoundSide::upper:BoundSide::lower;
    case SetRelation::outer: return sense==ObjectiveSense::minimize?BoundSide::lower:BoundSide::upper;
    }
    return BoundSide::none;
}
} // namespace csl::geometry::approximation
