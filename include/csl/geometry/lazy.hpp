#pragma once

#include <csl/geometry/contracts.hpp>
#include <csl/registry/provider.hpp>

namespace csl::geometry::lazy {

// A snapshot of the immutable operation stored by this module. Nested input
// handles retain their source payloads after the caller releases its handles.
struct ExpressionDescription {
    GeometryOperation operation;
    GeometryEvidence creation_evidence;
    std::vector<std::string> coordinate_labels;
};

std::variant<ExpressionDescription, Diagnostics> inspect_expression(const SetHandle&);

registry::Registration<registry::GeometryPort> make_expression_registration();

// The selected leaf support provider is copied into the registration. Its
// registry may be destroyed after preparation; each leaf query is admitted
// against that immutable provider before execution.
registry::Registration<registry::GeometryPort> make_support_registration(
    registry::PreparedProvider<registry::GeometryPort> leaf_support);

} // namespace csl::geometry::lazy
