#include <csl/controllers/continuous_policy.hpp>
#include <nlohmann/json.hpp>

#include <chrono>
#include <array>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {
using namespace csl;
using namespace csl::controllers;
using namespace csl::model;
using nlohmann::json;
using Clock = std::chrono::steady_clock;

constexpr std::string_view schema = "csl.ext04-continuous-policy-trial/1";
constexpr std::string_view timing_scope =
    "batch of public evaluate_continuous_policy calls and literal per-generator trajectory, "
    "action-bound, and status checks; retains numeric outcomes from each batch's final call; "
    "fixture construction and JSONL serialization excluded";

using Observed = std::array<std::array<double, 6>, 4>;

struct Fixture {
    LinearSystem system;
    ContinuousPolicyRequest request;
};

Fixture make_fixture() {
    SystemModel authored;
    authored.dynamics.dimensions = {2, 1, 0};
    authored.dynamics.time_domain = TimeDomain::discrete;
    authored.dynamics.stages.emplace<LinearStage>(LinearStage{
        {2, 2, {1, 1, 0, 1}}, {2, 1, {0.5, 1}}, {2, 0, {}}, {0, 0}});
    Observation observation;
    observation.coefficients.emplace<ObservationStage>(ObservationStage{
        {1, 2, {1, 0}}, {1, 1, {0}}, {1, 0, {}}, {1, 0, {}}, {0}});
    observation.schedule.push_back({{0},
        {{0}, ObservationTiming::before_decision},
        {{0}, ObservationTiming::before_decision}, std::nullopt});
    authored.observations.push_back(std::move(observation));
    auto system_result = snapshot(authored, Vector{0, 1});
    if (!std::holds_alternative<LinearSystem>(system_result))
        throw std::runtime_error("fixture system rejected");
    auto system = std::get<LinearSystem>(std::move(system_result));

    auto domain_result = make_joint_v_uncertainty(system, {
        {0, 0}, {0, 1}, {1, 0}, {1, 1}});
    if (!std::holds_alternative<JointVUncertainty>(domain_result))
        throw std::runtime_error("fixture joint set rejected");
    AffineStagePolicy rule{{0}, {{{0}, {0}, 0}},
        {2, 1, {1, 0}}, {0, 0}, {1, 1, {0}}, {1, 2, {1, 0}}, {0}};
    auto policy_result = make_affine_observation_policy(system, {rule});
    if (!std::holds_alternative<AffineObservationPolicy>(policy_result))
        throw std::runtime_error("fixture policy rejected");
    ContinuousPolicyRequest request{
        PolicyCoverage::all_joint_uncertainty,
        std::get<JointVUncertainty>(std::move(domain_result)),
        std::get<AffineObservationPolicy>(std::move(policy_result)),
        {}, {{{1, 1, {1}}, {1.25}}}, std::nullopt, 1e-9};
    return {std::move(system), std::move(request)};
}

Observed verify(const ContinuousPolicyResult& result) {
    if (!std::holds_alternative<ContinuousPolicyEvidence>(result))
        throw std::runtime_error("continuous policy evaluation did not return evidence");
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    if (evidence.assurance != Assurance::numerical ||
        evidence.feasibility != NumericalFeasibility::within_tolerance ||
        evidence.trajectories.size() != 4)
        throw std::runtime_error("literal feasibility evidence differs");
    constexpr double expected[][4] = {
        {0, 0, 0, 0}, {0, 1, 1, 1}, {1, 0, 1.5, 1}, {1, 1, 2.5, 2}};
    Observed observed{};
    for (std::size_t index = 0; index < evidence.trajectories.size(); ++index) {
        const auto& trajectory = evidence.trajectories[index].trajectory;
        if (trajectory.inputs.initial_state != Vector{expected[index][0], expected[index][1]} ||
            trajectory.decisions.size() != 1 ||
            trajectory.decisions[0].action != Vector{expected[index][0]} ||
            trajectory.states.back() != Vector{expected[index][2], expected[index][3]})
            throw std::runtime_error("literal generator trajectory differs");
        if (evidence.trajectories[index].action_slacks.size() != 1 ||
            evidence.trajectories[index].action_slacks[0] !=
                Vector{1.25 - expected[index][0]})
            throw std::runtime_error("literal action safety margin differs");
        observed[index] = {trajectory.inputs.initial_state[0], trajectory.inputs.initial_state[1],
            trajectory.decisions[0].action[0], trajectory.states.back()[0],
            trajectory.states.back()[1], evidence.trajectories[index].action_slacks[0][0]};
    }
    return observed;
}

} // namespace

int main(int argc, char** argv) try {
    if (argc != 2 || (std::string_view(argv[1]) != "smoke" &&
                     std::string_view(argv[1]) != "measure"))
        throw std::runtime_error("expected smoke or measure");
    const bool smoke = std::string_view(argv[1]) == "smoke";
    auto fixture = make_fixture();
    if (smoke) {
        verify(evaluate_continuous_policy(fixture.system, fixture.request));
        std::cout << "continuous-policy smoke passed\n";
        return 0;
    }

    constexpr int repetitions = 7;
    constexpr int batch = 5000;
    for (int round = -1; round < repetitions; ++round) {
        Observed observed{};
        const auto start = Clock::now();
        for (int call = 0; call < batch; ++call)
            observed = verify(evaluate_continuous_policy(fixture.system, fixture.request));
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now() - start).count();
        json row{{"schema", schema}, {"round", round + 1}, {"warmup", round == -1},
            {"batch", batch}, {"elapsed_ns", elapsed}, {"status", "passed"},
            {"assurance", "numerical"}, {"feasibility", "within_tolerance"},
            {"generators_per_call", 4}, {"feasibility_tolerance", 1e-9},
            {"fixture_reused", true}, {"outer_workers", 1},
            {"timing_scope", timing_scope}, {"result", json::array()}};
        for (const auto& generator : observed)
            row["result"].push_back({{"initial", {generator[0], generator[1]}},
                {"action", {generator[2]}}, {"terminal", {generator[3], generator[4]}},
                {"action_margin", generator[5]}});
        std::cout << row.dump() << '\n';
    }
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
