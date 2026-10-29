#include <csl/controllers/continuous_policy.hpp>
#include <csl/optimization/linear_program.hpp>

#include <algorithm>
#include <chrono>
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

struct SynthesisInequality {
    Vector coefficients;
    double upper_bound;
};

std::optional<std::size_t> checked_add(std::size_t left, std::size_t right) {
    if (right > std::numeric_limits<std::size_t>::max() - left) return std::nullopt;
    return left + right;
}

std::optional<std::size_t> checked_multiply(std::size_t left, std::size_t right) {
    if (left != 0 && right > std::numeric_limits<std::size_t>::max() / left) return std::nullopt;
    return left * right;
}

Diagnostic unsupported(std::string field, std::string message) {
    return {DiagnosticCode::unsupported, std::move(field), std::move(message)};
}

OneStageAffineSynthesisResult inconclusive(AffineSynthesisInconclusiveReason reason,
        std::optional<AffineObservationPolicy> candidate = {},
        std::optional<ContinuousPolicyEvidence> evaluation = {},
        std::optional<ProgramResult> solve = {}) {
    return AffineSynthesisInconclusive{reason, std::move(candidate), std::move(evaluation), std::move(solve)};
}

std::optional<OperationStopped> stop_requested(const ExecutionContext& context) {
    if (context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Cancelled during affine-policy synthesis."};
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired, "Deadline expired during affine-policy synthesis."};
    return std::nullopt;
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

std::variant<JointUncertaintyLayout, Diagnostic> joint_layout_for(
        const model::LinearSystem& system) {
    const auto dimensions = system.dimensions();
    JointUncertaintyLayout layout{0, {0, dimensions.state}, {}, {}};
    layout.total_dimension = dimensions.state;
    const auto append_slice = [&](std::size_t size) -> std::optional<CoordinateSlice> {
        const auto end = checked_add(layout.total_dimension, size);
        if (!end) return std::nullopt;
        const CoordinateSlice slice{layout.total_dimension, size};
        layout.total_dimension = *end;
        return slice;
    };
    layout.external_by_stage.reserve(system.horizon());
    for (std::size_t stage = 0; stage < system.horizon(); ++stage) {
        const auto slice = append_slice(dimensions.external);
        if (!slice) return invalid("controllers.joint_uncertainty.dimension", "Joint uncertainty dimension overflowed.");
        layout.external_by_stage.push_back(*slice);
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
            const auto slice = append_slice(error_dimension);
            if (!slice) return invalid("controllers.joint_uncertainty.dimension", "Joint uncertainty dimension overflowed.");
            errors.push_back(*slice);
        }
    }
    return layout;
}

bool same_layout(const JointUncertaintyLayout& left, const JointUncertaintyLayout& right) {
    const auto same_slices = [](const auto& first, const auto& second) {
        if (first.size() != second.size()) return false;
        for (std::size_t index = 0; index < first.size(); ++index)
            if (first[index].offset != second[index].offset ||
                first[index].dimension != second[index].dimension) return false;
        return true;
    };
    if (left.total_dimension != right.total_dimension ||
        left.initial_state.offset != right.initial_state.offset ||
        left.initial_state.dimension != right.initial_state.dimension ||
        !same_slices(left.external_by_stage, right.external_by_stage) ||
        left.errors_by_channel_sample.size() != right.errors_by_channel_sample.size()) return false;
    for (std::size_t channel = 0; channel < left.errors_by_channel_sample.size(); ++channel)
        if (!same_slices(left.errors_by_channel_sample[channel], right.errors_by_channel_sample[channel]))
            return false;
    return true;
}

}

JointVUncertaintyResult make_joint_v_uncertainty(const model::LinearSystem& system,
        std::vector<Vector> joint_generators) {
    auto layout_result = joint_layout_for(system);
    if (const auto* error = std::get_if<Diagnostic>(&layout_result)) return *error;
    auto layout = std::get<JointUncertaintyLayout>(std::move(layout_result));
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
    const auto expected_layout = joint_layout_for(system);
    if (const auto* error = std::get_if<Diagnostic>(&expected_layout)) return *error;
    if (!same_layout(request.domain.layout(), std::get<JointUncertaintyLayout>(expected_layout)))
        return invalid("controllers.policy.domain", "Joint uncertainty coordinates were authored for a different system layout.");
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

OneStageAffineSynthesisResult synthesize_one_stage_affine_policy(
        const model::LinearSystem& system, const OneStageAffineSynthesisRequest& request,
        LPWorkspace& lp, const ExecutionContext& context) {
    if (const auto stopped = stop_requested(context)) return *stopped;
    if (system.horizon() != 1)
        return unsupported("controllers.synthesis.horizon", "Affine policy synthesis currently supports exactly one transition.");
    const auto expected_layout = joint_layout_for(system);
    if (const auto* error = std::get_if<Diagnostic>(&expected_layout)) return *error;
    if (!same_layout(request.domain.layout(), std::get<JointUncertaintyLayout>(expected_layout)))
        return invalid("controllers.synthesis.domain", "Joint uncertainty coordinates were authored for a different system layout.");
    if (request.feasibility_program.problem.value.empty() || request.feasibility_program.program.value.empty())
        return invalid("controllers.synthesis.program_identity", "The generated LP requires a nonempty caller-supplied program identity.");
    if (!std::isfinite(request.feasibility_tolerance) || request.feasibility_tolerance < 0.0)
        return invalid("controllers.synthesis.tolerance", "Feasibility tolerance must be finite and nonnegative.");
    if (!std::isfinite(context.numerical.absolute_tolerance) || context.numerical.absolute_tolerance < 0.0 ||
        !std::isfinite(context.numerical.relative_tolerance) || context.numerical.relative_tolerance < 0.0)
        return invalid("controllers.synthesis.numerical", "LP tolerances must be finite and nonnegative.");
    const double synthesis_margin = 4.0 * std::max({request.feasibility_tolerance,
        context.numerical.absolute_tolerance, context.numerical.relative_tolerance});
    if (!std::isfinite(synthesis_margin))
        return invalid("controllers.synthesis.tolerance", "Synthesis margin overflowed.");
    if (request.action_features.empty())
        return invalid("controllers.synthesis.features", "At least one before-decision observation component is required.");

    const auto dimensions = system.dimensions();
    if ((!request.state_safety.empty() && request.state_safety.size() != 2) ||
        (!request.action_safety.empty() && request.action_safety.size() != 1))
        return invalid("controllers.synthesis.safety", "One-stage synthesis accepts two state-safety slices and one action-safety slice.");
    for (const auto& safety : request.state_safety)
        if (!valid_safety(safety, dimensions.state))
            return invalid("controllers.synthesis.state_safety", "State rows must be finite and match the model state dimension.");
    for (const auto& safety : request.action_safety)
        if (!valid_safety(safety, dimensions.control))
            return invalid("controllers.synthesis.action_safety", "Action rows must be finite and match the model control dimension.");

    const auto feature_stride = checked_add(request.action_features.size(), 1);
    const auto parameter_count = feature_stride
        ? checked_multiply(dimensions.control, *feature_stride) : std::nullopt;
    const auto estimate_feature_count = checked_multiply(dimensions.state, request.action_features.size());
    const auto action_feature_count = checked_multiply(dimensions.control, request.action_features.size());
    const auto action_estimate_count = checked_multiply(dimensions.control, dimensions.state);
    if (!parameter_count || !estimate_feature_count || !action_feature_count || !action_estimate_count)
        return unsupported("controllers.synthesis.dimensions", "Policy coefficient extent overflowed.");

    std::size_t rows_per_generator = 0;
    if (!request.state_safety.empty()) {
        const auto state_rows = checked_add(request.state_safety.front().inequalities.rows,
            request.state_safety.back().inequalities.rows);
        if (!state_rows) return unsupported("controllers.synthesis.dimensions", "Safety row extent overflowed.");
        rows_per_generator = *state_rows;
    }
    if (!request.action_safety.empty()) {
        const auto rows = checked_add(rows_per_generator,
            request.action_safety.front().inequalities.rows);
        if (!rows) return unsupported("controllers.synthesis.dimensions", "Safety row extent overflowed.");
        rows_per_generator = *rows;
    }
    auto inequality_count = checked_multiply(request.domain.generators().size(), rows_per_generator);
    if (!inequality_count) return unsupported("controllers.synthesis.dimensions", "Generated safety row count overflowed.");
    if (*inequality_count == 0) inequality_count = 1;
    const auto doubled_parameters = checked_multiply(*parameter_count, 2);
    const auto column_count = doubled_parameters
        ? checked_add(*doubled_parameters, *inequality_count) : std::nullopt;
    const auto maximum_nonzeros_per_row = doubled_parameters
        ? checked_add(*doubled_parameters, 1) : std::nullopt;
    const auto maximum_nonzeros = maximum_nonzeros_per_row
        ? checked_multiply(*inequality_count, *maximum_nonzeros_per_row) : std::nullopt;
    const auto dense_coefficients = checked_multiply(*inequality_count, *parameter_count);
    const auto coefficient_bytes = dense_coefficients
        ? checked_multiply(*dense_coefficients, sizeof(double)) : std::nullopt;
    const auto row_metadata_bytes = checked_multiply(*inequality_count, sizeof(SynthesisInequality));
    const auto sparse_entry_bytes = maximum_nonzeros
        ? checked_multiply(*maximum_nonzeros, sizeof(std::size_t) + sizeof(double)) : std::nullopt;
    const auto row_offsets = checked_add(*inequality_count, 1);
    const auto offset_bytes = row_offsets
        ? checked_multiply(*row_offsets, sizeof(std::size_t)) : std::nullopt;
    const auto variable_bytes = column_count
        ? checked_multiply(*column_count, sizeof(double) + sizeof(Interval)) : std::nullopt;
    const auto constraint_bytes = checked_multiply(*inequality_count, sizeof(Interval));
    const auto upper_bound_bytes = checked_multiply(*inequality_count, sizeof(double));
    if (!column_count || !maximum_nonzeros || !coefficient_bytes || !row_metadata_bytes || !sparse_entry_bytes ||
        !offset_bytes || !variable_bytes || !constraint_bytes || !upper_bound_bytes)
        return unsupported("controllers.synthesis.dimensions", "Feasibility LP storage extent overflowed.");
    std::size_t estimated_bytes = 0;
    for (const auto bytes : {*coefficient_bytes, *row_metadata_bytes, *sparse_entry_bytes, *offset_bytes,
             *variable_bytes, *constraint_bytes, *upper_bound_bytes}) {
        const auto total = checked_add(estimated_bytes, bytes);
        if (!total) return unsupported("controllers.synthesis.dimensions", "Feasibility LP storage extent overflowed.");
        estimated_bytes = *total;
    }
    if (context.resources && context.resources->memory_bytes && estimated_bytes > *context.resources->memory_bytes)
        return OperationStopped{StopReason::resource_limit,
            "The generated affine-policy feasibility LP exceeds the declared memory budget."};

    AffineStagePolicy placeholder{{0}, request.action_features,
        Matrix{dimensions.state, request.action_features.size(),
            Vector(*estimate_feature_count, 0.0)},
        Vector(dimensions.state, 0.0),
        Matrix{dimensions.control, request.action_features.size(),
            Vector(*action_feature_count, 0.0)},
        Matrix{dimensions.control, dimensions.state,
            Vector(*action_estimate_count, 0.0)},
        Vector(dimensions.control, 0.0)};
    const auto checked_placeholder = make_affine_observation_policy(system, {placeholder});
    if (const auto* error = std::get_if<Diagnostic>(&checked_placeholder)) return *error;

    const auto dynamics = system.stage({0});
    if (const auto* error = std::get_if<Diagnostic>(&dynamics)) return *error;
    const auto& stage = std::get<model::DynamicsStage>(dynamics);

    std::vector<SynthesisInequality> inequalities;
    inequalities.reserve(*inequality_count);
    const auto append_inequality = [&](Vector coefficients, double upper_bound) -> bool {
        if (coefficients.size() != *parameter_count || !finite(coefficients) || !std::isfinite(upper_bound)) return false;
        inequalities.push_back({std::move(coefficients), upper_bound});
        return true;
    };

    const Estimator zero_estimator = [state_dimension = dimensions.state](StageIndex,
            std::span<const ReleasedObservation>) { return Vector(state_dimension, 0.0); };
    const Controller zero_controller = [control_dimension = dimensions.control](StageIndex,
            std::span<const ReleasedObservation>, std::span<const double>) {
        return Vector(control_dimension, 0.0);
    };

    for (const auto& generator : request.domain.generators()) {
        if (const auto stopped = stop_requested(context)) return *stopped;
        const auto baseline = replay_observed_policy(system,
            replay_inputs(request.domain.layout(), generator), zero_estimator, zero_controller);
        if (const auto* error = std::get_if<Diagnostic>(&baseline)) return *error;
        if (const auto* stopped = std::get_if<OperationStopped>(&baseline)) return *stopped;
        const auto& record = std::get<ReplayRecord>(baseline);
        const auto history = history_values(placeholder, record.decisions.front().available);
        if (!history)
            return invalid("controllers.synthesis.features", "A requested observation feature was not released before the decision.");

        if (!request.state_safety.empty()) {
            const auto initial_margins = slacks(request.state_safety.front(), record.states.front());
            for (const auto margin : initial_margins)
                if (!append_inequality(Vector(*parameter_count, 0.0), margin - synthesis_margin))
                    return invalid("controllers.synthesis.state_safety", "Initial-state row arithmetic produced a nonfinite value.");
        }

        if (!request.action_safety.empty()) {
            const auto& safety = request.action_safety.front();
            for (std::size_t row = 0; row < safety.inequalities.rows; ++row) {
                Vector coefficients(*parameter_count, 0.0);
                for (std::size_t control = 0; control < dimensions.control; ++control) {
                    const double factor = safety.inequalities.values[row * dimensions.control + control];
                    const auto base = control * *feature_stride;
                    for (std::size_t feature = 0; feature < history->size(); ++feature)
                        coefficients[base + feature] = factor * (*history)[feature];
                    coefficients[base + history->size()] = factor;
                }
                if (!append_inequality(std::move(coefficients), safety.upper_bounds[row] - synthesis_margin))
                    return invalid("controllers.synthesis.action_safety", "Action-row coefficient arithmetic produced a nonfinite value.");
            }
        }

        if (!request.state_safety.empty()) {
            const auto& safety = request.state_safety.back();
            for (std::size_t row = 0; row < safety.inequalities.rows; ++row) {
                Vector coefficients(*parameter_count, 0.0);
                Vector input_effect(dimensions.control, 0.0);
                double fixed = 0.0;
                for (std::size_t state = 0; state < dimensions.state; ++state) {
                    const double factor = safety.inequalities.values[row * dimensions.state + state];
                    fixed += factor * record.states.back()[state];
                    for (std::size_t control = 0; control < dimensions.control; ++control)
                        input_effect[control] += factor * stage.B(state, control);
                }
                for (std::size_t control = 0; control < dimensions.control; ++control) {
                    const auto base = control * *feature_stride;
                    for (std::size_t feature = 0; feature < history->size(); ++feature)
                        coefficients[base + feature] = input_effect[control] * (*history)[feature];
                    coefficients[base + history->size()] = input_effect[control];
                }
                if (!append_inequality(std::move(coefficients), safety.upper_bounds[row] - fixed - synthesis_margin))
                    return invalid("controllers.synthesis.state_safety", "Terminal-row coefficient arithmetic produced a nonfinite value.");
            }
        }
    }

    if (inequalities.empty()) inequalities.push_back({Vector(*parameter_count, 0.0), 0.0});

    SparseMatrix matrix{inequalities.size(), *column_count, {0}, {}, {}};
    Vector upper_bounds;
    upper_bounds.reserve(inequalities.size());
    for (std::size_t row = 0; row < inequalities.size(); ++row) {
        const auto& inequality = inequalities[row];
        for (std::size_t column = 0; column < *parameter_count; ++column)
            if (inequality.coefficients[column] != 0.0) {
                matrix.column_indices.push_back(column);
                matrix.values.push_back(inequality.coefficients[column]);
            }
        for (std::size_t column = 0; column < *parameter_count; ++column)
            if (inequality.coefficients[column] != 0.0) {
                matrix.column_indices.push_back(*parameter_count + column);
                matrix.values.push_back(-inequality.coefficients[column]);
            }
        matrix.column_indices.push_back(*doubled_parameters + row);
        matrix.values.push_back(1.0);
        matrix.row_offsets.push_back(matrix.values.size());
        upper_bounds.push_back(inequality.upper_bound);
    }
    std::vector<Interval> variables(*column_count, Interval{0.0, std::nullopt});
    std::vector<Interval> rows;
    rows.reserve(upper_bounds.size());
    for (const auto value : upper_bounds) rows.push_back({value, value});
    auto made_program = optimization::make_linear_program({request.feasibility_program,
        Vector(*column_count, 0.0), 0.0, std::move(matrix), std::move(variables), std::move(rows)});
    if (const auto* errors = std::get_if<Diagnostics>(&made_program))
        return errors->empty() ? unsupported("controllers.synthesis.program", "Could not construct the feasibility LP.") : errors->front();
    auto program = std::get<LinearProgram>(std::move(made_program));

    if (const auto stopped = stop_requested(context)) return *stopped;
    const auto outcome = lp.solve(program, context);
    if (const auto* unsupported_result = std::get_if<Unsupported>(&outcome)) {
        const auto message = unsupported_result->diagnostics.empty()
            ? "The selected LP provider does not support the generated feasibility program."
            : unsupported_result->diagnostics.front().explanation;
        return unsupported("controllers.synthesis.lp", message);
    }
    const auto& solved = std::get<ProgramResult>(outcome);
    if (solved.outcome.subject != program.identity())
        return inconclusive(AffineSynthesisInconclusiveReason::malformed_solver_result, {}, {}, solved);
    if (solved.termination == Termination::cancelled)
        return OperationStopped{StopReason::cancelled, solved.raw_diagnostics};
    if (solved.termination == Termination::deadline_expired)
        return OperationStopped{StopReason::deadline_expired, solved.raw_diagnostics};
    if (solved.termination == Termination::resource_limit)
        return OperationStopped{StopReason::resource_limit, solved.raw_diagnostics};
    if (solved.termination == Termination::numerical_failure)
        return OperationStopped{StopReason::numerical_failure, solved.raw_diagnostics};
    if (solved.termination != Termination::completed)
        return unsupported("controllers.synthesis.lp", "The selected LP provider rejected the generated feasibility request.");
    if (solved.outcome.value == MathematicalOutcome::infeasible)
        return inconclusive(AffineSynthesisInconclusiveReason::solver_reported_infeasible_without_certificate, {}, {}, solved);
    if (solved.outcome.value != MathematicalOutcome::optimal || !solved.primal)
        return inconclusive(AffineSynthesisInconclusiveReason::solver_did_not_establish_feasibility, {}, {}, solved);

    if (solved.primal->size() != *column_count || !finite(*solved.primal))
        return inconclusive(AffineSynthesisInconclusiveReason::malformed_solver_result, {}, {}, solved);
    const auto primal_check = optimization::evaluate_primal(program, *solved.primal,
        context.numerical, {{"csl.controllers.affine-synthesis.primal"}, "1"});
    if (std::holds_alternative<Diagnostics>(primal_check))
        return inconclusive(AffineSynthesisInconclusiveReason::malformed_solver_result, {}, {}, solved);
    const auto& residuals = std::get<optimization::PrimalEvaluation>(primal_check).residuals;
    const auto within = [&](ResidualMeasure residual) {
        return std::isfinite(residual.violation) && std::isfinite(residual.scale) &&
            residual.violation <= context.numerical.absolute_tolerance +
                context.numerical.relative_tolerance * residual.scale;
    };
    if (!within(residuals.rows) || !within(residuals.variables))
        return inconclusive(AffineSynthesisInconclusiveReason::malformed_solver_result, {}, {}, solved);

    Matrix action_from_history{dimensions.control, request.action_features.size(),
        Vector(*action_feature_count, 0.0)};
    Vector action_offset(dimensions.control, 0.0);
    for (std::size_t control = 0; control < dimensions.control; ++control) {
        const auto base = control * *feature_stride;
        for (std::size_t feature = 0; feature < request.action_features.size(); ++feature)
            action_from_history.values[control * request.action_features.size() + feature] =
                (*solved.primal)[base + feature] - (*solved.primal)[*parameter_count + base + feature];
        action_offset[control] = (*solved.primal)[base + request.action_features.size()] -
            (*solved.primal)[*parameter_count + base + request.action_features.size()];
    }
    AffineStagePolicy rule{{0}, request.action_features,
        Matrix{dimensions.state, request.action_features.size(),
            Vector(dimensions.state * request.action_features.size(), 0.0)},
        Vector(dimensions.state, 0.0), std::move(action_from_history),
        Matrix{dimensions.control, dimensions.state,
            Vector(*action_estimate_count, 0.0)}, std::move(action_offset)};
    auto made_policy = make_affine_observation_policy(system, {std::move(rule)});
    if (std::holds_alternative<Diagnostic>(made_policy))
        return inconclusive(AffineSynthesisInconclusiveReason::malformed_solver_result, {}, {}, solved);
    auto policy = std::get<AffineObservationPolicy>(std::move(made_policy));

    ContinuousPolicyRequest evaluation_request{PolicyCoverage::all_joint_uncertainty,
        request.domain, policy, request.state_safety, request.action_safety, std::nullopt,
        request.feasibility_tolerance};
    auto evaluation = evaluate_continuous_policy(system, evaluation_request);
    if (const auto* error = std::get_if<Diagnostic>(&evaluation)) return *error;
    if (const auto* stopped = std::get_if<OperationStopped>(&evaluation)) return *stopped;
    auto evidence = std::get<ContinuousPolicyEvidence>(std::move(evaluation));
    if (evidence.feasibility == NumericalFeasibility::violation_found)
        return inconclusive(AffineSynthesisInconclusiveReason::candidate_violates_safety,
            std::move(policy), std::move(evidence), solved);
    if (evidence.feasibility == NumericalFeasibility::inconclusive)
        return inconclusive(AffineSynthesisInconclusiveReason::candidate_within_tolerance_band,
            std::move(policy), std::move(evidence), solved);
    return SynthesizedAffinePolicy{std::move(policy), std::move(evidence), solved};
}

} // namespace csl::controllers
