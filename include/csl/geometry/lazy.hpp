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

} // namespace csl::geometry::lazy
