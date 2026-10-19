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

enum class SampleCoverage { directions_only };
struct SupportSample { Vector direction; SupportResult answer; };
struct SupportSamples {
    GeometryReference reference;
    SampleCoverage coverage{SampleCoverage::directions_only};
    std::vector<SupportSample> samples;
};
using SampleOutcome = std::variant<SupportSamples, Unsupported, OperationStopped>;

// Finite directions are diagnostics, not a materialized set or a global
// inclusion certificate. No partial batch is published on a stop or refusal.
SampleOutcome sample_support(const registry::PreparedProvider<registry::GeometryPort>& provider,
    const SetHandle& input, const std::vector<Vector>& directions,
    const GeometryRequestIdentity& identity, const ExecutionContext& context);

} // namespace csl::geometry::lazy
