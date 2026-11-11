#pragma once

#include <csl/reachability/fixed_plan_disturbance.hpp>

namespace csl::reachability::detail {

// Structural facts shared by fixed-plan representation adapters. Callers keep
// their own diagnostic vocabulary and validation order around these predicates.
inline bool has_fixed_plan_horizon_shape(const FixedPlanRequest& request) {
    const auto horizon = request.system.horizon();
    return request.controls.size() == horizon &&
           request.disturbances.size() == horizon &&
           request.admissible_states.size() == horizon + 1;
}

inline bool fixed_plan_initial_matches_model(const FixedPlanRequest& request) {
    return request.initial.metadata()->set.dimension ==
           request.system.dimensions().state;
}

inline bool fixed_plan_safe_dimensions_match_model(
    const FixedPlanRequest& request) {
    const auto state_dimension = request.system.dimensions().state;
    for (const auto& safe : request.admissible_states)
        if (safe.metadata()->set.dimension != state_dimension)
            return false;
    return true;
}

} // namespace csl::reachability::detail
