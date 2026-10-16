#include <csl/geometry/contracts.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <utility>

namespace csl {
namespace {
using contracts_detail::Overloaded;
using contracts_detail::matrix_matches;
struct OperationScope { std::vector<SetId> inputs; GeometryClaimScope claim; };
OperationScope operation_scope(const GeometryOperation& operation) {
    return std::visit(Overloaded{
        [](const AffineImage& op) { return OperationScope{{op.input.id},GeometryClaimScope::set_relation}; },
        [](const MinkowskiSum& op) { return OperationScope{{op.left.id,op.right.id},GeometryClaimScope::set_relation}; },
        [](const DependentSum& op) { return OperationScope{{op.left.id,op.right.id},GeometryClaimScope::set_relation}; },
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
}
Diagnostics check_operation_shape(const OperationRequest& request) {
    const bool valid = std::visit(Overloaded{
        [](const AffineImage& op) {
            return matrix_matches(op.map,op.map.rows,op.input.metadata.dimension) && op.offset.size() == op.map.rows;
        },
        [](const MinkowskiSum& op) { return op.left.metadata.dimension == op.right.metadata.dimension; },
        [](const DependentSum& op) { return op.left.metadata.dimension == op.right.metadata.dimension; },
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
} // namespace csl
