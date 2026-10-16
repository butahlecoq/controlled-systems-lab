#pragma once

#include <csl/model/linear_system.hpp>
#include <functional>
#include <span>

namespace csl::controllers {

// One explicitly sampled physical trajectory. Errors are indexed [channel][sample]
// in the authored observation schedule, including zero-dimensional samples.
struct ReplayInputs {
    Vector initial_state;
    std::vector<Vector> external;
    std::vector<std::vector<Vector>> measurement_errors;
};

struct ReleasedObservation {
    model::ObservationIndex channel;
    model::SampleIndex sample;
    ObservationPoint released_at;
    model::ObservationValue value;
};

// The estimate is a caller-defined state hypothesis, not a verified state.
using Estimator = std::function<Vector(StageIndex, std::span<const ReleasedObservation>)>;
using Controller = std::function<Vector(StageIndex, std::span<const ReleasedObservation>,
    std::span<const double> estimate)>;

struct DecisionEvidence {
    StageIndex stage;
    std::vector<ReleasedObservation> available;
    Vector estimate;
    Vector action;
};

struct ReplayRecord {
    ReplayInputs inputs;
    std::vector<Vector> states;
    std::vector<DecisionEvidence> decisions;
    std::vector<ReleasedObservation> released;
};

using ReplayResult = std::variant<ReplayRecord, Diagnostic, OperationStopped>;

// At before(k), release due observations, estimate from that history, then
// choose u_k. Apply the supplied external sample, advance state and release
// after(k) observations. before(T) releases terminal observations only.
// This is sampled replay; it makes no all-disturbance or optimality claim.
ReplayResult replay_observed_policy(const model::LinearSystem&, const ReplayInputs&,
    const Estimator&, const Controller&);

} // namespace csl::controllers
