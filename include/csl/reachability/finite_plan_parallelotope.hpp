#pragma once

#include <csl/geometry/contracts.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>

namespace csl::reachability {

struct ParallelotopeStage {
  Vector lower;
  Vector upper;
};

struct FinitePlanParallelotopeTrace {
  static constexpr SetRelation relation = SetRelation::outer;
  // x = frame * y; each coordinate box in y is one physical parallelotope.
  Matrix frame;
  std::vector<ParallelotopeStage> stages;
  Assurance assurance{Assurance::numerical};
};

using FinitePlanParallelotopeOutcome =
    std::variant<FinitePlanParallelotopeTrace, Unsupported, OperationStopped>;

// Stagewise outer propagation in a fixed, non-axis-aligned four-state frame.
// The frame and its integer inverse are fixed by this first TwoPoints profile;
// singular dynamics are supported because the frame is not derived from A.
FinitePlanParallelotopeOutcome
finite_plan_parallelotope(const FixedPlanRequest &request,
                          const ExecutionContext &context = {});

} // namespace csl::reachability
