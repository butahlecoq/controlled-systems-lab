#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <variant>

namespace csl {
struct LinearStage { Matrix A, B, E; Vector offset; };
using Coefficients = std::variant<LinearStage, std::vector<LinearStage>>;
enum class TimeDomain { discrete, continuous };
struct Dynamics { Dimensions dimensions; TimeDomain time_domain; Coefficients stages; };
// after_decision(k) follows transition k; before_decision(T) is terminal only.
enum class ObservationTiming { before_decision, after_decision };
struct ObservationPoint { StageIndex stage; ObservationTiming timing; };
struct ObservationStage { Matrix state_map, control_map, external_map, error_map; Vector offset; };
// Indexed records follow authored sample order, not global transition index.
using ObservationCoefficients = std::variant<ObservationStage, std::vector<ObservationStage>>;
struct ObservationSample {
    StageIndex state_stage;
    ObservationPoint measured_at, available_at;
    std::optional<StageIndex> input_stage;
};
struct Observation { ObservationCoefficients coefficients; std::vector<ObservationSample> schedule; };
struct SystemModel { Dynamics dynamics; std::vector<Observation> observations; };
Diagnostics check_model_shape(const Dynamics&, std::size_t horizon);
} // namespace csl
