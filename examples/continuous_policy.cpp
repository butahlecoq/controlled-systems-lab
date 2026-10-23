#include <csl/controllers/continuous_policy.hpp>

#include <iostream>
#include <stdexcept>
#include <utility>

int main() try {
    using namespace csl;
    using namespace csl::controllers;

    SystemModel authored;
    authored.dynamics.dimensions = {2, 1, 0};
    authored.dynamics.time_domain = TimeDomain::discrete;
    authored.dynamics.stages.emplace<LinearStage>(LinearStage{
        {2,2,{1,1,0,1}}, {2,1,{0.5,1}}, {2,0,{}}, {0,0}});
    Observation observation;
    observation.coefficients.emplace<ObservationStage>(ObservationStage{
        {1,2,{1,0}}, {1,1,{0}}, {1,0,{}}, {1,0,{}}, {0}});
    observation.schedule.push_back({{0},
        {{0}, ObservationTiming::before_decision},
        {{0}, ObservationTiming::before_decision}, std::nullopt});
    authored.observations.push_back(std::move(observation));
    const auto system_result = model::snapshot(authored, Vector{0, 1});
    if (const auto* error = std::get_if<Diagnostic>(&system_result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    const auto& system = std::get<model::LinearSystem>(system_result);

    const auto domain_result = make_joint_v_uncertainty(system, {
        {0, 0}, {0, 1}, {1, 0}, {1, 1}
    });
    if (const auto* error = std::get_if<Diagnostic>(&domain_result))
        throw std::runtime_error(error->field + ": " + error->explanation);

    const AffineStagePolicy rule{{0}, {{{0}, {0}, 0}},
        {2,1,{1,0}}, {0,0}, {1,1,{0}}, {1,2,{1,0}}, {0}};
    const auto policy_result = make_affine_observation_policy(system, {rule});
    if (const auto* error = std::get_if<Diagnostic>(&policy_result))
        throw std::runtime_error(error->field + ": " + error->explanation);

    const ContinuousPolicyRequest request{
        PolicyCoverage::all_joint_uncertainty,
        std::get<JointVUncertainty>(domain_result),
        std::get<AffineObservationPolicy>(policy_result),
        {},
        {{{1,1,{1}}, {1.25}}},
        std::nullopt,
        1e-9
    };
    const auto result = evaluate_continuous_policy(system, request);
    if (const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    if (const auto* stopped = std::get_if<OperationStopped>(&result))
        throw std::runtime_error(stopped->diagnostics);
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    if (evidence.feasibility != NumericalFeasibility::within_tolerance ||
        evidence.trajectories.size() != 4)
        throw std::runtime_error("Expected all four generator trajectories to satisfy the action bound.");

    std::cout << "scope=all_joint_uncertainty assurance=numerical generators="
              << evidence.trajectories.size() << '\n';
    for (const auto& trajectory : evidence.trajectories) {
        const auto& initial = trajectory.trajectory.states.front();
        const auto& terminal = trajectory.trajectory.states.back();
        const auto& action = trajectory.trajectory.decisions.front().action;
        std::cout << "initial=" << initial[0] << ',' << initial[1]
                  << " action=" << action[0]
                  << " terminal=" << terminal[0] << ',' << terminal[1] << '\n';
    }
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
