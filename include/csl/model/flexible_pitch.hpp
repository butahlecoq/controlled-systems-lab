#pragma once

#include <csl/model/catalogue.hpp>
#include <csl/model/discretization.hpp>

namespace csl::model::catalogue {

struct FlexiblePitchBendingMode {
    double frequency, input_gain, pitch_force, lateral_force;
};

struct FlexiblePitchSloshMode {
    double frequency_squared, damping;
    double pitch_acceleration, lateral_acceleration;
    double lateral_feedback, pitch_feedback, pitch_position;
};

// Coefficients of source equation (3), not a calibrated vehicle parameter set.
// Physical state order is theta, theta_rate, y, Vy, then (s, s_rate) per
// bending mode and (beta, beta_rate) per liquid-filled tank.
struct FlexiblePitchParameters {
    double pitch_stiffness, pitch_lateral_velocity, pitch_input;
    double lateral_pitch, lateral_velocity_damping, lateral_input;
    double bending_decrement;
    std::vector<FlexiblePitchBendingMode> bending;
    std::vector<FlexiblePitchSloshMode> slosh;
};

struct FlexiblePitchDescriptor {
    Matrix mass, implicit_state, implicit_input;
    LinearStage rates;
    double minimum_scaled_pivot, maximum_relative_residual;
};

struct FlexiblePitchCase {
    DiscreteReachabilityCase reachability;
    FlexiblePitchParameters parameters;
    FlexiblePitchDescriptor descriptor;
    DiscretizationReceipt discretization;
};

template<class T> using FlexiblePitchResult = std::variant<T, Diagnostics>;

std::span<const CaseInfo> flexible_pitch_cases() noexcept;
FlexiblePitchResult<FlexiblePitchCase> make_flexible_pitch_case(std::string_view id);
FlexiblePitchResult<FlexiblePitchParameters> flexible_pitch_parameters(std::string_view id);

// Assemble E*x_dot=A_tilde*x+B_tilde*delta, then solve the checked descriptor.
// Singular or numerically unresolved E never yields an explicit rate model.
FlexiblePitchResult<FlexiblePitchDescriptor>
assemble_flexible_pitch(const FlexiblePitchParameters&);

} // namespace csl::model::catalogue
