#pragma once

#include <csl/core/outcomes.hpp>

#include <csl/model/contracts.hpp>

#include <csl/numeric/data.hpp>

namespace csl::model {

template<class T> using Result = std::variant<T, Diagnostic>;
template<class T> using EvaluationResult = std::variant<T, Diagnostic, OperationStopped>;
struct ObservationIndex { std::size_t value; };
struct SampleIndex { std::size_t value; };

struct DynamicsStage {
    numeric::MatrixView A, B, E;
    numeric::VectorView offset;
};
struct ObservationMaps {
    numeric::MatrixView state_map, control_map, external_map, error_map;
    numeric::VectorView offset;
};
struct ObservationMetadata {
    ObservationSample sample;
    double state_time, measured_time, available_time;
};
struct ObservationRecord { ObservationMaps maps; ObservationMetadata metadata; };
struct ObservationValue { Vector values; ObservationMetadata metadata; };

namespace detail { struct SystemStorage; }
// Immutable retaining handle. Snapshot copies authored buffers, including rvalues.
class LinearSystem {
public:
    LinearSystem(const LinearSystem&) = default;
    LinearSystem& operator=(const LinearSystem&) = default;
    Dimensions dimensions() const noexcept;
    std::size_t horizon() const noexcept;
    Result<double> time(StageIndex) const;
    Result<DynamicsStage> stage(StageIndex) const;
    std::size_t channel_count() const noexcept;
    Result<std::size_t> sample_count(ObservationIndex) const;
    Result<ObservationRecord> observation(ObservationIndex, SampleIndex) const;
    EvaluationResult<Vector> step(StageIndex, std::span<const double> state,
        std::span<const double> control, std::span<const double> external) const;
    // Values must come from the declared sample sources; no trajectory is retained.
    EvaluationResult<ObservationValue> observe(ObservationIndex, SampleIndex,
        std::span<const double> state, std::span<const double> control,
        std::span<const double> external, std::span<const double> error) const;
private:
    explicit LinearSystem(std::shared_ptr<const detail::SystemStorage>);
    std::shared_ptr<const detail::SystemStorage> storage_;
    friend Result<LinearSystem> snapshot(const SystemModel&, std::span<const double>);
};

Result<LinearSystem> snapshot(const SystemModel&, std::span<const double> times);

} // namespace csl::model
