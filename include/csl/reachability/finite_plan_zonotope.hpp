#pragma once

#include <csl/geometry/contracts.hpp>
#include <csl/reachability/fixed_plan_disturbance.hpp>
#include <csl/sets/generator_sets.hpp>

namespace csl::reachability {

struct FinitePlanZonotopeTrace {
    static constexpr SetRelation relation = SetRelation::outer;
    // Every stage is an outer zonotope for the reachable states of this fixed
    // open-loop plan. Generator factors are independent between stages.
    struct Stage {
        Vector center;
        Matrix generators;
        std::vector<sets::FactorId> factors;
    };
    std::vector<Stage> stages;
    Assurance assurance{Assurance::numerical};
};

using FinitePlanZonotopeOutcome =
    std::variant<FinitePlanZonotopeTrace, Unsupported, OperationStopped>;

struct FinitePlanZonotopeLimits {
    std::size_t max_generators_per_stage;
};

// Propagates a fixed plan with general-dimensional zonotopes. Bounded initial
// and disturbance V sets are enclosed by coordinate boxes; each affine stage
// propagates generator columns and adds diagonal generators for floating-point
// rounding. Universal, singleton or H state constraints are supported when
// the complete outer zonotope is contained; failed containment is inconclusive,
// not a reachable violation. Other constraints and unbounded sets return
// Unsupported. The trace is a numerical outer enclosure, not a control-feasibility
// or optimizer-completeness certificate. The caller
// supplies a maximum generator count per stage; exceeding it returns Unsupported.
FinitePlanZonotopeOutcome finite_plan_zonotope(const FixedPlanRequest &request,
                                               FinitePlanZonotopeLimits limits,
                                               const ExecutionContext &context = {});

// One-step all-control affine image. The entire control zonotope is mapped
// through B as an independent existential geometric input, not a disturbance
// policy or finite action catalogue. A fresh stage index is required per step.
std::variant<FinitePlanZonotopeTrace::Stage, Unsupported, OperationStopped>
propagate_existential_control_zonotope(const model::DynamicsStage &,
                                       const FinitePlanZonotopeTrace::Stage &current,
                                       const FinitePlanZonotopeTrace::Stage &controls,
                                       std::size_t generator_limit, const ExecutionContext &,
                                       std::size_t stage);

} // namespace csl::reachability
