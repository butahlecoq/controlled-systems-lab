#pragma once

#include <csl/controllers/observed_replay.hpp>
#include <csl/evidence/contracts.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/contracts.hpp>
#include <csl/execution/contracts.hpp>
#include <csl/sets/data.hpp>
#include <cstddef>
#include <optional>
#include <span>
#include <string>
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

class JointHUncertainty {
public:
    JointHUncertainty(const JointHUncertainty&) = default;
    JointHUncertainty& operator=(const JointHUncertainty&) = default;
    JointHUncertainty(JointHUncertainty&&) noexcept = default;
    JointHUncertainty& operator=(JointHUncertainty&&) noexcept = default;
    const sets::SetData& set() const noexcept { return set_; }
    const JointUncertaintyLayout& layout() const noexcept { return layout_; }

private:
    JointHUncertainty(sets::SetData set, JointUncertaintyLayout layout)
        : set_(std::move(set)), layout_(std::move(layout)) {}
    sets::SetData set_;
    JointUncertaintyLayout layout_;
    friend std::variant<JointHUncertainty, Diagnostic> make_joint_h_uncertainty(
        const model::LinearSystem&, sets::SetData);
};

using JointHUncertaintyResult = std::variant<JointHUncertainty, Diagnostic>;
JointHUncertaintyResult make_joint_h_uncertainty(
    const model::LinearSystem&, sets::SetData joint_domain);

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

enum class SafetyFamily { state, action };

struct HPolicyConstraintEvidence {
    SafetyFamily family;
    std::size_t stage;
    std::size_t row;
    double upper_bound;
    std::optional<double> maximum_activity_upper_bound;
    std::optional<double> observed_activity;
    std::optional<Vector> joint_coordinates;
    std::optional<ReplayRecord> trajectory;
    std::optional<PrimalResiduals> dual_primal_check;
    ProgramResult dual_support_solve;
    std::optional<PrimalResiduals> primal_support_check;
    std::optional<ProgramResult> primal_support_solve;
    std::optional<std::string> primal_support_unavailable;
};

struct HContinuousPolicyRequest {
    ProgramIdentity program_namespace;
    JointHUncertainty domain;
    AffineObservationPolicy policy;
    std::vector<LinearSafetyConstraints> state_safety;
    std::vector<LinearSafetyConstraints> action_safety;
    double feasibility_tolerance{1e-9};
};

struct HContinuousPolicyEvidence {
    Assurance assurance{Assurance::numerical};
    NumericalFeasibility feasibility{NumericalFeasibility::inconclusive};
    double feasibility_tolerance{};
    std::optional<Vector> domain_witness;
    std::optional<ReplayRecord> domain_witness_trajectory;
    std::optional<PrimalResiduals> domain_primal_check;
    std::optional<ProgramResult> domain_feasibility_solve;
    std::vector<HPolicyConstraintEvidence> constraints;
};

using HContinuousPolicyResult = std::variant<
    HContinuousPolicyEvidence, Diagnostic, OperationStopped>;

// Numerically checks an affine policy over a joint H-polytope using a dual
// support LP per safety row and a primal LP when a counterexample is needed.
// Unbounded support, incomplete solver evidence, and tolerance-band results
// remain inconclusive.
HContinuousPolicyResult evaluate_h_continuous_policy(
    const model::LinearSystem&, const HContinuousPolicyRequest&,
    LPWorkspace&, const ExecutionContext&);

struct OneStageAffineSynthesisRequest {
    ProgramIdentity feasibility_program;
    JointVUncertainty domain;
    std::vector<ObservationComponentRef> action_features;
    std::vector<LinearSafetyConstraints> state_safety;
    std::vector<LinearSafetyConstraints> action_safety;
    double feasibility_tolerance{1e-9};
};

enum class AffineSynthesisInconclusiveReason {
    solver_reported_infeasible_without_certificate,
    solver_did_not_establish_feasibility,
    malformed_solver_result,
    candidate_violates_safety,
    candidate_within_tolerance_band
};

struct SynthesizedAffinePolicy {
    AffineObservationPolicy policy;
    ContinuousPolicyEvidence evaluation;
    ProgramResult feasibility_solve;
};

struct AffineSynthesisInconclusive {
    AffineSynthesisInconclusiveReason reason;
    std::optional<AffineObservationPolicy> candidate;
    std::optional<ContinuousPolicyEvidence> evaluation;
    std::optional<ProgramResult> feasibility_solve;
};

using OneStageAffineSynthesisResult = std::variant<
    SynthesizedAffinePolicy, AffineSynthesisInconclusive,
    Diagnostic, OperationStopped>;

// Synthesizes an action affine in the named before-decision observations for
// one transition. A successful result is numerically checked over every point
// of the authored joint V-hull. LP workspace/provider choice belongs to the
// caller; a numerical infeasibility status is not a no-policy proof.
OneStageAffineSynthesisResult synthesize_one_stage_affine_policy(
    const model::LinearSystem&, const OneStageAffineSynthesisRequest&,
    LPWorkspace&, const ExecutionContext&);

} // namespace csl::controllers
