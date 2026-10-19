#pragma once

#include <csl/registry/registry.hpp>

namespace csl::geometry::approximation {

// These proofs are derived from the native elementary-set definitions, never
// from a provider's unverified inclusion assertion.
enum class StructuralBasis { identical_set, empty_subset, universal_superset, h_constraint_containment,
    h_point_containment, v_h_containment, h_v_containment, generator_axis_cover };
struct EnclosedApproximation { OperationResult result; StructuralBasis basis; };
struct HeuristicApproximation { OperationResult result; };
using RunOutcome = std::variant<EnclosedApproximation, HeuristicApproximation,
    registry::Rejection, OperationStopped, Unsupported>;

// Selects the separate ApproximationPort, runs its frozen request, then admits
// only relations with independently checkable evidence. Equivalent conversions
// belong to ConversionPort. No provider declaration alone proves inclusion.
RunOutcome run_registered(const registry::Registry<registry::ApproximationPort>&,
    registry::Method, const ApproximationRequest&, const ExecutionContext&);

enum class ObjectiveSense { minimize, maximize };
enum class BoundSide { none, lower, upper, both };
// Direction for an extremum over the same fixed objective on nested sets.
// This does not establish a feasible trajectory or an optimizer-family relation.
BoundSide objective_bound_side(SetRelation, ObjectiveSense) noexcept;

} // namespace csl::geometry::approximation
