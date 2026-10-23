#include <csl/controllers/continuous_policy.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <string>
#include <tuple>
#include <utility>

namespace csl::controllers {
namespace {

Diagnostic invalid(std::string field, std::string message) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(message)};
}

bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(),
        [](double value) { return std::isfinite(value); });
}

bool valid_matrix(const Matrix& matrix) {
    if (matrix.rows != 0 && matrix.cols > std::numeric_limits<std::size_t>::max() / matrix.rows)
        return false;
    return matrix.values.size() == matrix.rows * matrix.cols && finite(matrix.values);
}

Vector multiply(const Matrix& matrix, std::span<const double> values) {
    Vector result(matrix.rows, 0.0);
    for (std::size_t row = 0; row < matrix.rows; ++row)
        for (std::size_t column = 0; column < matrix.cols; ++column)
            result[row] += matrix.values[row * matrix.cols + column] * values[column];
    return result;
}

bool precedes(ObservationPoint left, ObservationPoint right) {
    if (left.stage.value != right.stage.value) return left.stage.value < right.stage.value;
    return left.timing == ObservationTiming::before_decision &&
        right.timing == ObservationTiming::after_decision;
}

const AffineStagePolicy* rule_for(const AffineObservationPolicy& policy, StageIndex stage) {
    const auto rules = policy.stages();
    if (stage.value >= rules.size()) return nullptr;
    return &rules[stage.value];
}

std::optional<Vector> history_values(const AffineStagePolicy& rule,
        std::span<const ReleasedObservation> history) {
    Vector values;
    values.reserve(rule.released_inputs.size());
    for (const auto& reference : rule.released_inputs) {
        const auto found = std::find_if(history.begin(), history.end(), [&](const auto& item) {
            return item.channel.value == reference.channel.value &&
                item.sample.value == reference.sample.value;
        });
        if (found == history.end() || reference.component >= found->value.values.size())
            return std::nullopt;
        values.push_back(found->value.values[reference.component]);
    }
    return values;
}

ReplayInputs replay_inputs(const JointUncertaintyLayout& layout, const Vector& coordinates) {
    const auto take = [&](CoordinateSlice slice) {
        return Vector(coordinates.begin() + static_cast<std::ptrdiff_t>(slice.offset),
            coordinates.begin() + static_cast<std::ptrdiff_t>(slice.offset + slice.dimension));
    };
    ReplayInputs result;
    result.initial_state = take(layout.initial_state);
    result.external.reserve(layout.external_by_stage.size());
    for (const auto slice : layout.external_by_stage) result.external.push_back(take(slice));
    result.measurement_errors.resize(layout.errors_by_channel_sample.size());
    for (std::size_t channel = 0; channel < layout.errors_by_channel_sample.size(); ++channel) {
        for (const auto slice : layout.errors_by_channel_sample[channel])
            result.measurement_errors[channel].push_back(take(slice));
    }
    return result;
}

bool valid_safety(const LinearSafetyConstraints& safety, std::size_t dimension) {
    return valid_matrix(safety.inequalities) &&
        safety.inequalities.cols == dimension &&
        safety.inequalities.rows == safety.upper_bounds.size() && finite(safety.upper_bounds);
}

Vector slacks(const LinearSafetyConstraints& safety, std::span<const double> point) {
    Vector result;
    result.reserve(safety.inequalities.rows);
    for (std::size_t row = 0; row < safety.inequalities.rows; ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < safety.inequalities.cols; ++column)
            value += safety.inequalities.values[row * safety.inequalities.cols + column] * point[column];
        result.push_back(safety.upper_bounds[row] - value);
    }
    return result;
}

} // namespace

JointVUncertaintyResult make_joint_v_uncertainty(const model::LinearSystem& system,
        std::vector<Vector> joint_generators) {
    const auto dimensions = system.dimensions();
    const auto horizon = system.horizon();
    JointUncertaintyLayout layout{0, {0, dimensions.state}, {}, {}};
    layout.total_dimension = dimensions.state;
    const auto append_slice = [&](std::size_t size, JointUncertaintyLayout& target) -> CoordinateSlice {
        const auto offset = target.total_dimension;
        if (size > std::numeric_limits<std::size_t>::max() - offset) return {0, 0};
        target.total_dimension += size;
        return {offset, size};
    };
    layout.external_by_stage.reserve(horizon);
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const auto slice = append_slice(dimensions.external, layout);
        if (slice.dimension != dimensions.external) return invalid("controllers.joint_uncertainty.dimension",
            "Joint uncertainty dimension overflowed.");
        layout.external_by_stage.push_back(slice);
    }
    layout.errors_by_channel_sample.resize(system.channel_count());
    for (std::size_t channel = 0; channel < system.channel_count(); ++channel) {
        const auto sample_count = system.sample_count({channel});
        if (const auto* error = std::get_if<Diagnostic>(&sample_count)) return *error;
        auto& errors = layout.errors_by_channel_sample[channel];
        errors.reserve(std::get<std::size_t>(sample_count));
        for (std::size_t sample = 0; sample < std::get<std::size_t>(sample_count); ++sample) {
            const auto observation = system.observation({channel}, {sample});
            if (const auto* error = std::get_if<Diagnostic>(&observation)) return *error;
            const auto error_dimension = std::get<model::ObservationRecord>(observation).maps.error_map.cols();
            const auto slice = append_slice(error_dimension, layout);
            if (slice.dimension != error_dimension) return invalid("controllers.joint_uncertainty.dimension",
                "Joint uncertainty dimension overflowed.");
            errors.push_back(slice);
        }
    }
    if (joint_generators.empty())
        return invalid("controllers.joint_uncertainty.generators", "Supply at least one generator for the joint uncertainty polytope.");
    for (const auto& generator : joint_generators) {
        if (generator.size() != layout.total_dimension || !finite(generator))
            return invalid("controllers.joint_uncertainty.generators",
                "Every joint generator must be finite and match the complete initial/input/error coordinate dimension.");
    }
    return JointVUncertainty{std::move(joint_generators), std::move(layout)};
}

AffineObservationPolicyResult make_affine_observation_policy(const model::LinearSystem& system,
        std::vector<AffineStagePolicy> stages) {
    const auto dimensions = system.dimensions();
    if (stages.size() != system.horizon())
        return invalid("controllers.policy.stages", "Supply exactly one affine policy rule per decision stage.");
    for (std::size_t stage = 0; stage < stages.size(); ++stage) {
        auto& rule = stages[stage];
        if (rule.decision.value != stage)
            return invalid("controllers.policy.stages", "Policy rules must contain every decision stage in order.");
        if (!valid_matrix(rule.estimate_from_history) || !valid_matrix(rule.action_from_history) ||
            !valid_matrix(rule.action_from_estimate) || !finite(rule.estimate_offset) || !finite(rule.action_offset))
            return invalid("controllers.policy.coefficients", "Policy matrices and offsets must be finite and structurally valid.");
        if (rule.estimate_from_history.rows != dimensions.state ||
            rule.estimate_from_history.cols != rule.released_inputs.size() ||
            rule.estimate_offset.size() != dimensions.state ||
            rule.action_from_history.rows != dimensions.control ||
            rule.action_from_history.cols != rule.released_inputs.size() ||
            rule.action_from_estimate.rows != dimensions.control ||
            rule.action_from_estimate.cols != dimensions.state ||
            rule.action_offset.size() != dimensions.control)
            return invalid("controllers.policy.coefficients", "Policy coefficient dimensions must match state, action, and named history dimensions.");
        std::vector<std::tuple<std::size_t, std::size_t, std::size_t>> seen;
        for (const auto& reference : rule.released_inputs) {
            const auto count = system.sample_count(reference.channel);
            if (const auto* error = std::get_if<Diagnostic>(&count)) return *error;
            if (reference.sample.value >= std::get<std::size_t>(count))
                return invalid("controllers.policy.history", "Policy references an observation sample outside the schedule.");
            const auto identity = std::tuple{reference.channel.value, reference.sample.value,
                reference.component};
            if (std::find(seen.begin(), seen.end(), identity) != seen.end())
                return invalid("controllers.policy.history", "Each observation component may appear once in a stage history map.");
            seen.push_back(identity);
            const auto observation = system.observation(reference.channel, reference.sample);
            if (const auto* error = std::get_if<Diagnostic>(&observation)) return *error;
            const auto record = std::get<model::ObservationRecord>(observation);
            const ObservationPoint decision{{stage}, ObservationTiming::before_decision};
            if (precedes(decision, record.metadata.sample.available_at))
                return invalid("controllers.policy.nonanticipativity", "A policy rule cannot read an observation before its declared availability event.");
            if (reference.component >= record.maps.state_map.rows())
                return invalid("controllers.policy.history", "Policy observation component is outside the sample output dimension.");
        }
    }
    return AffineObservationPolicy{std::move(stages)};
}

ContinuousPolicyResult evaluate_continuous_policy(const model::LinearSystem& system,
        const ContinuousPolicyRequest& request) {
    if (!std::isfinite(request.feasibility_tolerance) || request.feasibility_tolerance < 0.0)
        return invalid("controllers.policy.tolerance", "Feasibility tolerance must be finite and nonnegative.");
    const auto horizon = system.horizon();
    const auto dimensions = system.dimensions();
    if (request.domain.layout().external_by_stage.size() != horizon ||
        request.policy.stages().size() != horizon)
        return invalid("controllers.policy.shape", "Joint domain and policy must match the system horizon.");
    if (request.scope != PolicyCoverage::all_joint_uncertainty &&
        request.scope != PolicyCoverage::selected_joint_witness)
        return invalid("controllers.policy.scope", "Coverage scope is unsupported.");
    if ((!request.state_safety.empty() && request.state_safety.size() != horizon + 1) ||
        (!request.action_safety.empty() && request.action_safety.size() != horizon))
        return invalid("controllers.policy.safety", "State safety needs T+1 entries and action safety needs T entries.");
    for (const auto& safety : request.state_safety)
        if (!valid_safety(safety, dimensions.state))
            return invalid("controllers.policy.state_safety", "State safety rows must be finite and match the state dimension.");
    for (const auto& safety : request.action_safety)
        if (!valid_safety(safety, dimensions.control))
            return invalid("controllers.policy.action_safety", "Action safety rows must be finite and match the control dimension.");

    struct EvaluationPoint {
        std::optional<std::size_t> generator_index;
        std::optional<Vector> witness_weights;
        Vector coordinates;
    };
    std::vector<EvaluationPoint> points;
    if (request.scope == PolicyCoverage::all_joint_uncertainty) {
        if (request.witness) return invalid("controllers.policy.scope", "All-joint coverage must not include a selected witness.");
        points.reserve(request.domain.generators().size());
        for (std::size_t i = 0; i < request.domain.generators().size(); ++i)
            points.push_back({i, std::nullopt, request.domain.generators()[i]});
    } else {
        if (!request.witness || request.witness->convex_weights.size() != request.domain.generators().size())
            return invalid("controllers.policy.witness", "Selected-witness scope requires one convex weight per joint generator.");
        const auto& weights = request.witness->convex_weights;
        if (!finite(weights) || std::any_of(weights.begin(), weights.end(), [](double value) { return value < 0.0; }))
            return invalid("controllers.policy.witness", "Witness weights must be finite and nonnegative.");
        const double total = std::accumulate(weights.begin(), weights.end(), 0.0);
        const double weight_tolerance = std::max(request.feasibility_tolerance, 1e-12);
        if (!std::isfinite(total) || std::abs(total - 1.0) > weight_tolerance)
            return invalid("controllers.policy.witness", "Witness weights must sum to one within the declared tolerance.");
        Vector normalized_weights(weights.size());
        for (std::size_t i = 0; i < weights.size(); ++i) normalized_weights[i] = weights[i] / total;
        Vector coordinates(request.domain.layout().total_dimension, 0.0);
        for (std::size_t generator = 0; generator < normalized_weights.size(); ++generator)
            for (std::size_t coordinate = 0; coordinate < coordinates.size(); ++coordinate)
                coordinates[coordinate] += normalized_weights[generator] * request.domain.generators()[generator][coordinate];
        points.push_back({std::nullopt, std::move(normalized_weights), std::move(coordinates)});
    }

    const auto policy = request.policy;
    const Estimator estimator = [&policy](StageIndex stage, std::span<const ReleasedObservation> history) {
        const auto* rule = rule_for(policy, stage);
        if (!rule) return Vector{};
        const auto values = history_values(*rule, history);
        if (!values) return Vector{};
        auto estimate = multiply(rule->estimate_from_history, *values);
        for (std::size_t i = 0; i < estimate.size(); ++i) estimate[i] += rule->estimate_offset[i];
        return estimate;
    };
    const Controller controller = [&policy](StageIndex stage,
            std::span<const ReleasedObservation> history, std::span<const double> estimate) {
        const auto* rule = rule_for(policy, stage);
        if (!rule) return Vector{};
        const auto values = history_values(*rule, history);
        if (!values) return Vector{};
        auto action = multiply(rule->action_from_history, *values);
        const auto estimate_part = multiply(rule->action_from_estimate, estimate);
        for (std::size_t i = 0; i < action.size(); ++i)
            action[i] += estimate_part[i] + rule->action_offset[i];
        return action;
    };

    ContinuousPolicyEvidence evidence{request.scope, Assurance::numerical,
        NumericalFeasibility::within_tolerance, request.feasibility_tolerance, {}};
    evidence.trajectories.reserve(points.size());
    bool near_boundary = false;
    for (auto& point : points) {
        auto replay = replay_observed_policy(system,
            replay_inputs(request.domain.layout(), point.coordinates), estimator, controller);
        if (const auto* error = std::get_if<Diagnostic>(&replay)) return *error;
        if (const auto* stopped = std::get_if<OperationStopped>(&replay)) return *stopped;
        auto trajectory = std::get<ReplayRecord>(std::move(replay));
        std::vector<Vector> state_slacks;
        std::vector<Vector> action_slacks;
        for (std::size_t stage = 0; stage < trajectory.states.size(); ++stage) {
            Vector margins;
            if (!request.state_safety.empty()) margins = slacks(request.state_safety[stage], trajectory.states[stage]);
            state_slacks.push_back(margins);
            for (const auto margin : margins) {
                if (!std::isfinite(margin)) return invalid("controllers.policy.state_safety", "State safety evaluation produced a nonfinite margin.");
                if (margin < -request.feasibility_tolerance) evidence.feasibility = NumericalFeasibility::violation_found;
                else if (margin <= request.feasibility_tolerance) near_boundary = true;
            }
        }
        for (std::size_t stage = 0; stage < trajectory.decisions.size(); ++stage) {
            Vector margins;
            if (!request.action_safety.empty()) margins = slacks(request.action_safety[stage], trajectory.decisions[stage].action);
            action_slacks.push_back(margins);
            for (const auto margin : margins) {
                if (!std::isfinite(margin)) return invalid("controllers.policy.action_safety", "Action safety evaluation produced a nonfinite margin.");
                if (margin < -request.feasibility_tolerance) evidence.feasibility = NumericalFeasibility::violation_found;
                else if (margin <= request.feasibility_tolerance) near_boundary = true;
            }
        }
        evidence.trajectories.push_back({point.generator_index, std::move(point.witness_weights),
            std::move(point.coordinates),
            std::move(trajectory), std::move(state_slacks), std::move(action_slacks)});
    }
    if (evidence.feasibility != NumericalFeasibility::violation_found && near_boundary)
        evidence.feasibility = NumericalFeasibility::inconclusive;
    return evidence;
}

} // namespace csl::controllers
