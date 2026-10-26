#pragma once

#include <csl/model/linear_system.hpp>
#include <csl/sets/data.hpp>
#include <csl/execution/contracts.hpp>
#include <csl/artifacts/run_statistics.hpp>

namespace csl::reachability {

struct FixedPlanRequest {
    model::LinearSystem system;
    sets::SetData initial;
    std::vector<Vector> controls;
    std::vector<sets::SetData> disturbances;
    // One convex H, singleton, universal or empty safe set per state stage.
    std::vector<sets::SetData> admissible_states;
    // Caller-unique across distinct fixed plans over the same initial set.
    RequestId request;
};
struct FixedPlanReachable {
    // Stage zero is the authored initial set. Later stages are complete V
    // candidate descriptions, possibly with redundant points.
    std::vector<sets::SetData> stages;
    Assurance assurance;
};
struct FixedPlanViolation {
    std::size_t stage;
    Vector violating_successor;
};
struct FixedPlanEmpty { std::size_t stage; };
struct FixedPlanTimingSpans {
    // One unique, caller-planned ID for each generated stage V representation.
    std::vector<artifacts::SpanId> stage_materialization;
};
using FixedPlanOutcome = std::variant<FixedPlanReachable, FixedPlanViolation,
    FixedPlanEmpty, Unsupported, OperationStopped>;

// Numerical fixed-plan reference for independent compact V disturbance sets.
// Every x/w pair is propagated. An unsafe successor rejects the whole plan;
// no state-set clipping is performed. max_points bounds each generated stage.
FixedPlanOutcome fixed_plan_disturbance(const FixedPlanRequest& request,
    std::size_t max_points, const ExecutionContext& context = {},
    const FixedPlanTimingSpans* timing_spans = nullptr);

} // namespace csl::reachability
