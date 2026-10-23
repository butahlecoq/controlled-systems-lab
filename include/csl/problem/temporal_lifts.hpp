#pragma once

#include <csl/problem/resolved_problem.hpp>

namespace csl::problem {

struct UnconstrainedFirstAction {};
struct RateLimitedFirstAction {
    Vector previous_control;
    AdmissibleSet increment_set;
};
// With UnconstrainedFirstAction, the transform uses p0=0 and D0=U0, so
// stage-zero absolute bounds apply without an added rate condition. With
// RateLimitedFirstAction, increment_set supplies u0-p0 in D0.
using SlewInitialCondition = std::variant<UnconstrainedFirstAction, RateLimitedFirstAction>;

struct SlewMemoryRequest {
    SlewInitialCondition first_action;
    // D1,...,D(T-1), one increment set per remaining stage.
    std::vector<AdmissibleSet> later_increments;
};

struct SlewCoordinateMap {
    JointCoordinates original;
    JointCoordinates lifted;
    Vector initial_memory;
    // Original x coordinates select the physical block of each lifted state.
    std::vector<std::size_t> original_state_to_lifted_state;
    // Original u[t] is the memory block p[t+1] in the lifted state history.
    std::vector<std::size_t> original_control_to_lifted_memory;
    // Each lifted increment coordinate is associated with the original control
    // coordinate whose difference from p[t] it represents.
    std::vector<std::size_t> lifted_increment_to_original_control;
};

struct SlewMemoryLift {
    Problem problem;
    SlewCoordinateMap coordinates;
};

struct ControlHistory {
    std::vector<Vector> states;
    std::vector<Vector> controls;
};

struct LiftedControlHistory {
    std::vector<Vector> augmented_states;
    std::vector<Vector> increments;
};

using SlewLiftResult = std::variant<SlewMemoryLift, Diagnostic, OperationStopped>;
using HistoryMapResult = std::variant<ControlHistory, LiftedControlHistory, Diagnostic>;

// Rewrites a nominal full-history control problem with one-step slew limits as
// z[t+1] = [A[t] B[t]; 0 I] z[t] + [B[t]; I] v[t] + [a[t]; 0],
// where z[t]=(x[t],u[t-1]) and v[t]=u[t]-u[t-1].
SlewLiftResult lift_one_step_slew(const Problem&, const SlewMemoryRequest&);

// These maps are inverse on histories related by the memory equations.
HistoryMapResult lift_history(const SlewCoordinateMap&, const ControlHistory&);
// Recovery checks, but does not certify, histories against the initial-memory
// and p[t+1]=p[t]+v[t] equations using the caller's numerical policy.
HistoryMapResult recover_history(const SlewCoordinateMap&, const LiftedControlHistory&,
    double absolute_tolerance, double relative_tolerance);

} // namespace csl::problem
