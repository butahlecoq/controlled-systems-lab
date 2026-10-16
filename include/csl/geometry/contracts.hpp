#pragma once

#include <csl/sets/contracts.hpp>
#include <csl/core/outcomes.hpp>
#include <csl/execution/contracts.hpp>

namespace csl {
enum class SetRelation { equivalent, inner, outer, heuristic };
struct GeometryRequestIdentity {
    ProblemId problem;
    RequestId request; // identifies the complete immutable request, including operands
    ReferenceId ideal_output; // exact mathematical set, support value or containment proposition
    bool operator==(const GeometryRequestIdentity&) const = default;
};
struct GeometryReference {
    GeometryRequestIdentity identity;
    std::vector<SetId> inputs; // ordered, extracted from operation operands
    bool operator==(const GeometryReference&) const = default;
};
enum class GeometryClaimScope { set_relation, support_value, containment };
struct GeometryErrorBound { ModuleId metric; double bound; std::string units; };
struct GeometryEvidence {
    GeometryReference reference;
    GeometryClaimScope scope;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
    std::optional<GeometryErrorBound> error_bound; // justified only by this claim's support
};
struct AffineImage { SetHandle input; Matrix map; Vector offset; }; // y=Mx+b
struct MinkowskiSum { SetHandle left, right; };
// Shared generator FactorIds denote one common scalar across both operands.
// Admission requires factor-bearing representations; this is not MinkowskiSum.
struct DependentSum { SetHandle left, right; };
struct Intersection { SetHandle left, right; };
struct Projection { SetHandle input; std::vector<std::size_t> coordinates; }; // ordered zero-based indices
struct AffinePreimage { SetHandle target; Matrix map; Vector offset; }; // {x: Mx+b in target}
struct SupportQuery { SetHandle input; Vector direction; }; // sup d'x
struct ContainmentQuery { SetHandle subset, superset; };
using GeometryOperation = std::variant<AffineImage, MinkowskiSum, DependentSum, Intersection, Projection,
    AffinePreimage, SupportQuery, ContainmentQuery>;
struct OperationRequest {
    GeometryRequestIdentity identity;
    ModuleId implementation;
    GeometryOperation operation;
    SetRelation required_relation; // set-valued operations only; query values use their own evidence
    Assurance assurance;
};
GeometryReference geometry_reference(const OperationRequest&);
struct OperationResult { SetHandle output; SetRelation relation; GeometryEvidence evidence; };
struct EmptySupport {};
struct UnboundedSupport {};
struct SupportResult { std::variant<double, EmptySupport, UnboundedSupport> value; std::optional<Vector> maximizer; GeometryEvidence evidence; };
enum class ContainmentDecision { contained, not_contained, undetermined };
struct ContainmentResult { ContainmentDecision decision; std::optional<Vector> counterexample; GeometryEvidence evidence; };
struct ConversionRequest { GeometryRequestIdentity identity; SetHandle input; RepresentationId output; Assurance assurance; };
struct ApproximationRequest { GeometryRequestIdentity identity; SetHandle input; RepresentationId output; SetRelation direction; std::size_t size_budget; Assurance assurance; };
using SetTransformOutcome = std::variant<OperationResult, OperationStopped, Unsupported>;
using OperationOutcome = std::variant<OperationResult, SupportResult, ContainmentResult, OperationStopped, Unsupported>;
class SetOperatorWorkspace : public ExclusiveWorkspace {
public: virtual OperationOutcome apply(const OperationRequest&, const ExecutionContext&) = 0;
};
class RepresentationConverterWorkspace : public ExclusiveWorkspace {
public: virtual SetTransformOutcome convert(const ConversionRequest&, const ExecutionContext&) = 0;
};
class SetApproximatorWorkspace : public ExclusiveWorkspace {
public: virtual SetTransformOutcome approximate(const ApproximationRequest&, const ExecutionContext&) = 0;
};
Diagnostics check_operation_shape(const OperationRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const OperationRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const ConversionRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const ApproximationRequest&);
} // namespace csl
