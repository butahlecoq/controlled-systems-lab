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

// Stagewise outer propagation for 2 to 64 states. The 2D frame is identity
// and the 4D frame is a single shear block. Other dimensions use successive
// two-coordinate shear blocks and an identity coordinate if the count is odd.
// Universal, singleton and H state constraints are supported when every full
// outer parallelotope is contained; failed containment is inconclusive.
// Singular dynamics are supported because the frame is independent of A.
FinitePlanParallelotopeOutcome finite_plan_parallelotope(const FixedPlanRequest &request,
                                                         const ExecutionContext &context = {});

} // namespace csl::reachability
