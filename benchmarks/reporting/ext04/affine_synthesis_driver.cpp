#include <csl/controllers/continuous_policy.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/phase_one.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string_view>

namespace {
using namespace csl;
using namespace csl::controllers;
using namespace csl::model;
using nlohmann::json;
using Clock = std::chrono::steady_clock;

constexpr std::string_view schema = "csl.ext04-affine-synthesis-trial/1";
constexpr std::string_view timing_scope =
    "batch of public one-stage affine policy synthesis calls, injected phase-one LP solves, "
    "all-joint evaluator replay, and independent literal dynamics/safety checks; "
    "fixture construction, process startup, JSONL serialization and rendering excluded";
constexpr double tolerance = 1e-9;

void require(bool condition, const char* explanation) {
    if (!condition) throw std::runtime_error(explanation);
}

struct Fixture {
    LinearSystem system;
    OneStageAffineSynthesisRequest request;
    std::unique_ptr<LPWorkspace> workspace;
};

std::unique_ptr<LPWorkspace> make_workspace() {
    auto registered = optimization::phase_one::make_registration();
    require(std::holds_alternative<registry::Registration<registry::LPPort>>(registered),
        "phase-one provider registration failed");
    const auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registered));
    auto seed = optimization::make_linear_program({{{"ext04-affine-synthesis"}, {"workspace-seed"}},
        {0.0}, 0.0, {1, 1, {0, 1}, {0}, {1}}, {Interval{0.0, std::nullopt}},
        {Interval{0.0, 0.0}}});
    require(std::holds_alternative<LinearProgram>(seed), "workspace seed program rejected");
    return adapter.factory(std::get<LinearProgram>(seed));
}

Fixture make_fixture() {
    SystemModel authored;
    authored.dynamics.dimensions = {2, 1, 0};
    authored.dynamics.time_domain = TimeDomain::discrete;
    authored.dynamics.stages.emplace<LinearStage>(LinearStage{
        {2, 2, {1, 1, 0, 1}}, {2, 1, {-1, 0}}, {2, 0, {}}, {0, 0}});
    Observation observation;
    observation.coefficients.emplace<ObservationStage>(ObservationStage{
        {1, 2, {1, 0}}, {1, 1, {0}}, {1, 0, {}}, {1, 1, {1}}, {0}});
    observation.schedule.push_back({{0},
        {{0}, ObservationTiming::before_decision},
        {{0}, ObservationTiming::before_decision}, std::nullopt});
    authored.observations.push_back(std::move(observation));
    const auto system_result = snapshot(authored, Vector{0, 1});
    require(std::holds_alternative<LinearSystem>(system_result), "analytic two-state system rejected");
    auto system = std::get<LinearSystem>(system_result);

    std::vector<Vector> generators;
    for (const auto x1 : {-1.0, 1.0})
        for (const auto x2 : {-0.05, 0.05})
            for (const auto error : {-0.1, 0.1})
                generators.push_back({x1, x2, error});
    auto domain_result = make_joint_v_uncertainty(system, std::move(generators));
    require(std::holds_alternative<JointVUncertainty>(domain_result), "joint uncertainty set rejected");

    OneStageAffineSynthesisRequest request{
        {{"ext04-two-state-synthesis"}, {"affine-observation-feasibility"}},
        std::get<JointVUncertainty>(std::move(domain_result)), {{{0}, {0}, 0}}, {},
        {{{2, 1, {1, -1}}, {1.101, 1.101}}}, tolerance};
    request.state_safety = {{{0, 2, {}}, {}},
        {{4, 2, {1, 0, 0, 1, -1, 0, 0, -1}}, {0.16, 0.051, 0.16, 0.051}}};
    return {std::move(system), std::move(request), make_workspace()};
}

json checked_result(const OneStageAffineSynthesisResult& result,
        const OneStageAffineSynthesisRequest& request) {
    if (const auto* diagnostic = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(diagnostic->field + ": " + diagnostic->explanation);
    if (const auto* stopped = std::get_if<OperationStopped>(&result))
        throw std::runtime_error("synthesis stopped: " + stopped->diagnostics);
    if (const auto* inconclusive = std::get_if<AffineSynthesisInconclusive>(&result)) {
        const auto detail = inconclusive->feasibility_solve
            ? "; solver=" + inconclusive->feasibility_solve->raw_diagnostics : "";
        throw std::runtime_error("synthesis inconclusive reason=" +
            std::to_string(static_cast<int>(inconclusive->reason)) + detail);
    }
    const auto& synthesized = std::get<SynthesizedAffinePolicy>(result);
    const auto& evidence = synthesized.evaluation;
    require(evidence.scope == PolicyCoverage::all_joint_uncertainty &&
        evidence.assurance == Assurance::numerical &&
        evidence.feasibility == NumericalFeasibility::within_tolerance,
        "all-joint numerical feasibility status differs");
    require(evidence.trajectories.size() == request.domain.generators().size() &&
        evidence.trajectories.size() == 8, "joint generator coverage differs");
    require(synthesized.feasibility_solve.termination == Termination::completed &&
        synthesized.feasibility_solve.outcome.value == MathematicalOutcome::optimal &&
        synthesized.feasibility_solve.primal.has_value(), "LP feasibility result differs");

    require(synthesized.policy.stages().size() == 1, "synthesized policy horizon differs");
    const auto& rule = synthesized.policy.stages().front();
    require(rule.released_inputs.size() == 1 && rule.action_from_history.rows == 1 &&
        rule.action_from_history.cols == 1 && rule.action_offset.size() == 1,
        "synthesized policy shape differs");
    const double gain = rule.action_from_history.values.front();
    const double offset = rule.action_offset.front();
    json rows = json::array();
    for (std::size_t index = 0; index < evidence.trajectories.size(); ++index) {
        const auto& item = evidence.trajectories[index];
        const auto& coordinates = request.domain.generators()[index];
        const double x1 = coordinates[0];
        const double x2 = coordinates[1];
        const double error = coordinates[2];
        const double observation = x1 + error;
        const double action = gain * observation + offset;
        const Vector expected_terminal{x1 + x2 - action, x2};
        require(item.trajectory.states.size() == 2 && item.trajectory.decisions.size() == 1 &&
            item.trajectory.inputs.initial_state == Vector{x1, x2} &&
            item.trajectory.inputs.measurement_errors == std::vector<std::vector<Vector>>{{{error}}} &&
            item.trajectory.released.size() == 1 &&
            item.trajectory.released.front().value.values == Vector{observation} &&
            item.trajectory.decisions.front().action.size() == 1 &&
            std::abs(item.trajectory.decisions.front().action.front() - action) <= 1e-12 &&
            item.trajectory.states.back().size() == 2 &&
            std::abs(item.trajectory.states.back()[0] - expected_terminal[0]) <= 1e-12 &&
            std::abs(item.trajectory.states.back()[1] - expected_terminal[1]) <= 1e-12,
            "independent generator replay differs from policy and plant equations");
        require(std::abs(action) <= 1.101 && std::abs(expected_terminal[0]) <= 0.16 &&
            std::abs(expected_terminal[1]) <= 0.051,
            "independent safety check failed");
        rows.push_back({{"initial", {x1, x2}}, {"measurement_error", error},
            {"observation", observation}, {"action", action},
            {"terminal", expected_terminal},
            {"action_margins", {1.101 - action, 1.101 + action}},
            {"terminal_margins", {0.16 - expected_terminal[0], 0.051 - expected_terminal[1],
                0.16 + expected_terminal[0], 0.051 + expected_terminal[1]}}});
    }
    return {{"policy_gain", gain}, {"policy_offset", offset}, {"generators", std::move(rows)},
        {"assurance", "numerical"}, {"coverage", "all_joint_uncertainty"},
        {"feasibility", "within_tolerance"}, {"solver_outcome", "optimal"}};
}

json fixture_description() {
    return {{"id", "ext04-one-stage-noisy-integrator-v1"},
        {"dynamics", "x_next = [[1,1],[0,1]] x + [[-1],[0]] u"},
        {"observation", "y = x1 + e, measured and available before decision 0"},
        {"initial_generators", {{-1,-0.05},{-1,0.05},{1,-0.05},{1,0.05}}},
        {"measurement_error_vertices", {-0.1,0.1}},
        {"action_bounds", {-1.101,1.101}},
        {"terminal_bounds", {{"x1",{-0.16,0.16}}, {"x2",{-0.051,0.051}}}},
        {"feasibility_tolerance", tolerance},
        {"joint_vertices", 8}};
}

} // namespace

int main(int argc, char** argv) try {
    if (argc != 2 || (std::string_view(argv[1]) != "smoke" &&
                     std::string_view(argv[1]) != "measure"))
        throw std::runtime_error("expected smoke or measure");
    const bool smoke = std::string_view(argv[1]) == "smoke";
    auto fixture = make_fixture();
    require(fixture.workspace != nullptr, "phase-one provider returned a null workspace");
    if (smoke) {
        const auto result = synthesize_one_stage_affine_policy(
            fixture.system, fixture.request, *fixture.workspace, {});
        const auto record = checked_result(result, fixture.request);
        std::cout << record.dump(2) << '\n' << "affine-synthesis smoke passed\n";
        return 0;
    }

    constexpr int repetitions = 7;
    constexpr int batch = 100;
    for (int round = -1; round < repetitions; ++round) {
        json measured_result;
        const auto start = Clock::now();
        for (int call = 0; call < batch; ++call) {
            const auto result = synthesize_one_stage_affine_policy(
                fixture.system, fixture.request, *fixture.workspace, {});
            measured_result = checked_result(result, fixture.request);
        }
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now() - start).count();
        std::cout << json{{"schema", schema}, {"round", round + 1}, {"warmup", round == -1},
            {"batch", batch}, {"elapsed_ns", elapsed}, {"status", "passed"},
            {"fixture", fixture_description()},
            {"timing_scope", timing_scope}, {"workspace_reused", true},
            {"generators_per_call", 8}, {"feasibility_tolerance", tolerance},
            {"result", std::move(measured_result)}}.dump() << '\n';
    }
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
