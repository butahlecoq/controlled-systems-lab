#pragma once

#include <csl/reachability/fixed_plan_disturbance.hpp>

namespace csl::reachability {

struct FinitePlanEllipsoidTrace {
  struct Stage {
    Vector center;
    // Semiaxes of an axis-aligned ellipsoid. Its coordinate projections are
    // wider than the stage's axis-aligned box by sqrt(state_dimension).
    Vector radii;
  };
  std::vector<Stage> stages;
  Assurance assurance{Assurance::numerical};
};

using FinitePlanEllipsoidOutcome =
    std::variant<FinitePlanEllipsoidTrace, Unsupported, OperationStopped>;

// Stagewise outer propagation for bounded finite V disturbances and universal
// state constraints. Each affine image is bounded by ellipsoid support values;
// its resulting coordinate box is enclosed by a fresh axis-aligned ellipsoid.
// This is numerical evidence, not a validated-arithmetic certificate.
FinitePlanEllipsoidOutcome finite_plan_ellipsoid(
    const FixedPlanRequest& request, const ExecutionContext& context = {});

} // namespace csl::reachability
