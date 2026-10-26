#pragma once

#include <csl/artifacts/comparison_manifest.hpp>
#include <csl/artifacts/plot_data.hpp>
#include <csl/artifacts/plot_request.hpp>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/problem/contracts.hpp>
#include <csl/simulation/nonlinear_replay.hpp>

#include <array>

namespace csl::experiments {

enum class ReplayPolicyClass { nominal_reference, frozen_coefficient_regulator, selected_linear_witness };

struct ReplayClaimScope {
    verification::CheckStatus nonlinear_feasibility{verification::CheckStatus::not_checked};
    verification::CheckStatus nonlinear_objective_quality{verification::CheckStatus::not_checked};
    verification::CheckStatus nonlinear_global_optimality{verification::CheckStatus::not_checked};
};

struct WitnessReplay {
    artifacts::PlotPath linear;
    simulation::ReplayRecord nonlinear;
    ReplayPolicyClass policy_class{ReplayPolicyClass::selected_linear_witness};
    ReplayClaimScope claims;
};

struct ReplayComparison {
    artifacts::RunRecordRef source_run;
    ProblemId problem;
    artifacts::PlotAxis state_axis;
    artifacts::PlotCoordinates state_coordinates, control_coordinates;
    TerminalObjective linear_objective;
    std::optional<std::string> linear_objective_unit;
    std::vector<WitnessReplay> witnesses;
};

// Associates one ordered replay record with each selected linear path. Replays
// are separate evidence and never change the linear objective or its claims.
artifacts::ArtifactResult<ReplayComparison> associate_replays(
    const Problem&, const artifacts::PlotData&, artifacts::RunRecordRef,
    std::span<const simulation::ReplayRecord>,
    std::optional<std::string> linear_objective_unit = {});

struct ReplayTrajectoryPath {
    std::size_t source_ordinal{};
    double linear_objective{};
    verification::CheckStatus linear_optimality{verification::CheckStatus::not_checked};
    simulation::ReplayStatus replay_status{simulation::ReplayStatus::unavailable};
    std::optional<double> plant_objective;
    std::string plant_objective_unit;
    std::vector<std::string> missing_prerequisites;
    std::vector<std::array<double, 2>> points;
    ReplayPolicyClass policy_class{ReplayPolicyClass::selected_linear_witness};
    ReplayClaimScope claims;
};

struct ReplayTrajectoryPair {
    artifacts::RunRecordRef source_run;
    ProblemId problem;
    artifacts::PlotAxis state_axis;
    std::array<artifacts::CoordinateAnnotation, 2> coordinates;
    std::vector<ReplayTrajectoryPath> paths;
};

// Projects selected coordinates from full replay states. These are trajectories,
// not reachable-set boundaries. The renderer performs no simulation or geometry.
artifacts::ArtifactResult<ReplayTrajectoryPair> project_replay_trajectories(
    const ReplayComparison&, artifacts::CoordinatePair,
    std::array<artifacts::CoordinateAnnotation, 2> coordinate_labels);

artifacts::ArtifactResult<problem::ResolvedContent> encode_replay_comparison(
    const ReplayComparison&, artifacts::EncodeLimits = {});
artifacts::ArtifactResult<problem::ResolvedContent> decode_replay_comparison(
    std::string_view, artifacts::DecodeLimits = {});

} // namespace csl::experiments
