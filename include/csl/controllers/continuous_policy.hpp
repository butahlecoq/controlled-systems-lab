#pragma once

#include <csl/controllers/observed_replay.hpp>
#include <csl/evidence/contracts.hpp>
#include <csl/model/linear_system.hpp>
#include <cstddef>
#include <optional>
#include <span>
#include <utility>
#include <variant>
#include <vector>

namespace csl::controllers {

struct CoordinateSlice {
    std::size_t offset;
    std::size_t dimension;
};

struct JointUncertaintyLayout {
    std::size_t total_dimension;
    CoordinateSlice initial_state;
    std::vector<CoordinateSlice> external_by_stage;
    std::vector<std::vector<CoordinateSlice>> errors_by_channel_sample;
};

class JointVUncertainty {
public:
    JointVUncertainty(const JointVUncertainty&) = default;
    JointVUncertainty& operator=(const JointVUncertainty&) = default;
    JointVUncertainty(JointVUncertainty&&) noexcept = default;
    JointVUncertainty& operator=(JointVUncertainty&&) noexcept = default;
    std::span<const Vector> generators() const noexcept { return generators_; }
    const JointUncertaintyLayout& layout() const noexcept { return layout_; }

private:
    JointVUncertainty(std::vector<Vector> generators, JointUncertaintyLayout layout)
        : generators_(std::move(generators)), layout_(std::move(layout)) {}

    std::vector<Vector> generators_;
    JointUncertaintyLayout layout_;
    friend std::variant<JointVUncertainty, Diagnostic> make_joint_v_uncertainty(
        const model::LinearSystem&, std::vector<Vector>);
};

using JointVUncertaintyResult = std::variant<JointVUncertainty, Diagnostic>;
JointVUncertaintyResult make_joint_v_uncertainty(
    const model::LinearSystem&, std::vector<Vector> joint_generators);

struct ObservationComponentRef {
    model::ObservationIndex channel;
    model::SampleIndex sample;
    std::size_t component;
};

struct AffineStagePolicy {
    StageIndex decision;
    std::vector<ObservationComponentRef> released_inputs;
    Matrix estimate_from_history;
    Vector estimate_offset;
    Matrix action_from_history;
    Matrix action_from_estimate;
    Vector action_offset;
};

class AffineObservationPolicy {
public:
    AffineObservationPolicy(const AffineObservationPolicy&) = default;
    AffineObservationPolicy& operator=(const AffineObservationPolicy&) = default;
    AffineObservationPolicy(AffineObservationPolicy&&) noexcept = default;
    AffineObservationPolicy& operator=(AffineObservationPolicy&&) noexcept = default;
    std::span<const AffineStagePolicy> stages() const noexcept { return stages_; }

private:
    explicit AffineObservationPolicy(std::vector<AffineStagePolicy> stages)
        : stages_(std::move(stages)) {}

    std::vector<AffineStagePolicy> stages_;
    friend std::variant<AffineObservationPolicy, Diagnostic>
        make_affine_observation_policy(const model::LinearSystem&,
            std::vector<AffineStagePolicy>);
};

using AffineObservationPolicyResult = std::variant<AffineObservationPolicy, Diagnostic>;
AffineObservationPolicyResult make_affine_observation_policy(
    const model::LinearSystem&, std::vector<AffineStagePolicy> stages);

struct LinearSafetyConstraints {
    Matrix inequalities;
    Vector upper_bounds;
};

enum class PolicyCoverage { selected_joint_witness, all_joint_uncertainty };
enum class NumericalFeasibility { within_tolerance, violation_found, inconclusive };

struct JointWitness {
    Vector convex_weights;
};

struct ContinuousPolicyRequest {
    PolicyCoverage scope;
    JointVUncertainty domain;
    AffineObservationPolicy policy;
    std::vector<LinearSafetyConstraints> state_safety;
    std::vector<LinearSafetyConstraints> action_safety;
    std::optional<JointWitness> witness;
    double feasibility_tolerance{1e-9};
};

struct ContinuousGeneratorEvidence {
    std::optional<std::size_t> generator_index;
    std::optional<Vector> witness_weights;
    Vector joint_coordinates;
    ReplayRecord trajectory;
    std::vector<Vector> state_slacks;
    std::vector<Vector> action_slacks;
};

struct ContinuousPolicyEvidence {
    PolicyCoverage scope;
    Assurance assurance{Assurance::numerical};
    NumericalFeasibility feasibility{NumericalFeasibility::inconclusive};
    double feasibility_tolerance{};
    std::vector<ContinuousGeneratorEvidence> trajectories;
};

using ContinuousPolicyResult =
    std::variant<ContinuousPolicyEvidence, Diagnostic, OperationStopped>;

ContinuousPolicyResult evaluate_continuous_policy(
    const model::LinearSystem&, const ContinuousPolicyRequest&);

} // namespace csl::controllers
