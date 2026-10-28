#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/experiments/replay_artifact.hpp>
#include <csl/verification/trajectory.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <stop_token>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace ex = csl::experiments;
namespace sim = csl::simulation;

sim::Plant fuel_toy() {
    sim::Plant plant;
    plant.identity = {"toy.four-state-fuel", "1", "VIZ-04 analytic fixture; not B04 data"};
    plant.parameters = std::vector<sim::PlantParameter>{{"quadratic_gain", 1.0, "1"}};
    plant.initial_state = Vector{0.0, 0.0, 0.0, 0.0};
    plant.times = std::vector<double>{0.0, 1.0, 2.0};
    plant.time_unit = "s";
    plant.state_units = {"kg/s", "kg", "kg/s", "kg"};
    plant.control_units = {"kg/s", "kg/s"};
    plant.objective_name = "terminal stock sum";
    plant.objective_unit = "kg";
    plant.integration = sim::IntegrationMethod::exact_discrete_map;
    plant.hold = sim::ControlHold::constant_on_interval;
    plant.numerical = NumericalPolicy{1e-12, 1e-12};
    plant.transition = [](std::span<const double> state, std::span<const double> control,
        std::span<const sim::PlantParameter> parameters, double, double) {
        const double gain = parameters[0].value;
        return Vector{state[0] + control[0] + gain * control[0] * control[0],
            state[1] + state[0], state[2] + control[1] + 2.0 * gain * control[1] * control[1],
            state[3] + state[2]};
    };
    plant.objective = [](std::span<const double> state, std::span<const sim::PlantParameter>) {
        return state[1] + state[3];
    };
    return plant;
}

ar::PlotEvidence numerical_witness_evidence() {
    return {verification::CheckStatus::numerical_pass, verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass, verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass, verification::CheckStatus::numerical_pass, {}};
}

struct Fixture {
    Problem problem;
    problem::ResolvedProblem resolved;
    ar::PlotData plot;
    std::vector<sim::ReplayRecord> replays;
};

problem::ResolvedProblem resolve(const Problem& source) {
    auto result = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(result));
    return std::get<problem::ResolvedProblem>(std::move(result));
}

Fixture fixture() {
    Problem source;
    source.id = {"four-state-fuel-toy"};
    source.model = std::make_shared<const SystemModel>(SystemModel{{{4, 2, 0}, TimeDomain::discrete,
        std::vector<LinearStage>{
            {{4, 4, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}},
                {4, 2, {1, 0, 0, 0, 0, 1, 0, 0}}, {4, 0, {}}, {0, 0, 0, 0}},
            {{4, 4, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}},
                {4, 2, {1, 0, 0, 0, 0, 1, 0, 0}}, {4, 0, {}}, {0, 0, 0, 0}}}}, {}});
    source.times = {0.0, 1.0, 2.0};
    source.initial = KnownInitial{{0.0, 0.0, 0.0, 0.0}};
    source.controls = ContinuousDomain{{UniversalSet{2}, UniversalSet{2}}};
    source.states = {UniversalSet{4}, UniversalSet{4}, UniversalSet{4}};
    source.information = InformationPattern::nominal_open_loop;
    source.objective = ResidualNormTerminal{{2, 4, {1, 0, 0, 0, 0, 0, 1, 0}}, {1, 1}};
    const auto resolved = resolve(source);
    const auto plant = fuel_toy();
    const std::vector<Vector> first_controls{{0.0, 0.0}, {1.0, 1.0}};
    const std::vector<Vector> second_controls{{0.5, 0.5}, {0.5, 0.5}};
    const auto first = sim::replay(plant, first_controls);
    const auto second = sim::replay(plant, second_controls);

    ar::PlotData plot;
    plot.problem = source.id;
    plot.run = {"fuel-toy-run"};
    plot.strategy = {"linear-toy-strategy"};
    plot.strategy_version = "1";
    plot.state_axis = {ar::PlotAxis::Kind::physical_time, {0.0, 1.0, 2.0}, {}, "s"};
    plot.control_axis = {ar::PlotAxis::Kind::physical_time, {0.0, 1.0}, {1.0, 2.0}, "s"};
    plot.states.coordinates = {{"flow A", "kg/s", {}, {}}, {"stock A", "kg", {}, {}},
        {"flow B", "kg/s", {}, {}}, {"stock B", "kg", {}, {}}};
    plot.controls.coordinates = {{"control A", "kg/s", {}, {}}, {"control B", "kg/s", {}, {}}};
    plot.paths = {
        {plot.run, 0, plot.strategy, plot.strategy_version,
            {{0.0, 0.0, 0.0, 0.0}, {0.0, 0.0, 0.0, 0.0}, {1.0, 0.0, 1.0, 0.0}},
            first_controls, 0.0, numerical_witness_evidence()},
        {plot.run, 1, plot.strategy, plot.strategy_version,
            {{0.0, 0.0, 0.0, 0.0}, {0.5, 0.0, 0.5, 0.0}, {1.0, 0.0, 1.0, 0.0}},
            second_controls, 0.0, numerical_witness_evidence()},
    };
    return {source, resolved, std::move(plot), {first, second}};
}
}

TEST_CASE("4D selected linear witnesses retain separate nonlinear replay and 2D projections") {
    auto source = fixture();
    for (auto& path : source.plot.paths) {
        verification::TrajectoryRequest request;
        request.witness = {source.resolved.identity(), path.states, path.controls, path.objective};
        const auto verified = verification::verify_trajectory(source.resolved, request);
        REQUIRE(verified.bindings == verification::CheckStatus::numerical_pass);
        REQUIRE(verified.feasibility == verification::CheckStatus::numerical_pass);
        REQUIRE(verified.objective == verification::CheckStatus::numerical_pass);
        REQUIRE(verified.recomputed_objective == doctest::Approx(0.0));
        // This objective is a norm, so zero is an exact global lower bound
        // and both independently verified histories attain it.
        path.evidence = {verified.bindings, verified.feasibility, verified.objective,
            verification::CheckStatus::numerical_pass, verified.completeness,
            verified.validated, verified.residuals};
    }
    REQUIRE_FALSE(source.plot.paths[0].evidence.residuals.empty());
    const auto expected_linear_residual = source.plot.paths[0].evidence.residuals.front();
    const ar::RunRecordRef run_ref{source.plot.run, problem::ContentDigest{}};
    const auto associated = ex::associate_replays(source.problem, source.plot, run_ref, source.replays, "kg/s");
    REQUIRE(std::holds_alternative<ex::ReplayComparison>(associated));
    const auto& comparison = std::get<ex::ReplayComparison>(associated);
    REQUIRE(comparison.witnesses.size() == 2);
    CHECK(comparison.witnesses[0].linear.objective == comparison.witnesses[1].linear.objective);
    CHECK(comparison.witnesses[0].nonlinear.original_objective == doctest::Approx(0.0));
    CHECK(comparison.witnesses[1].nonlinear.original_objective == doctest::Approx(1.75));
    CHECK(comparison.witnesses[0].nonlinear.objective_unit == "kg");
    CHECK(comparison.witnesses[0].linear.evidence.optimality == verification::CheckStatus::numerical_pass);
    CHECK(comparison.linear_objective_unit == std::optional<std::string>{"kg/s"});

    std::ifstream fixture_file(CSL_VIZ04_REPLAY_FIXTURE);
    REQUIRE(fixture_file.good());
    const auto saved_example = nlohmann::json::parse(fixture_file);
    CHECK(saved_example["linear_objective_unit"] == "kg/s");
    CHECK(saved_example["linear_objective_convention"]["kind"] == "residual_norm");
    CHECK(saved_example["linear_objective_convention"]["target"] == std::vector<double>{1.0, 1.0});
    REQUIRE(saved_example["witnesses"].size() == comparison.witnesses.size());
    for (std::size_t i = 0; i < comparison.witnesses.size(); ++i) {
        CHECK(saved_example["witnesses"][i]["replay"]["states"] == comparison.witnesses[i].nonlinear.states);
        CHECK(saved_example["witnesses"][i]["replay"]["controls"] == comparison.witnesses[i].nonlinear.controls);
        CHECK(saved_example["witnesses"][i]["linear_objective"] == comparison.witnesses[i].linear.objective);
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["bindings"] == "numerical_pass");
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["feasibility"] == "numerical_pass");
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["objective"] == "numerical_pass");
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["optimality"] == "numerical_pass");
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["completeness"] == "unsupported");
        CHECK(saved_example["witnesses"][i]["linear_evidence"]["validated"] == "unsupported");
    }
    CHECK(saved_example["witnesses"][0]["replay"]["plant"]["version"] == "1");
    CHECK(saved_example["witnesses"][0]["replay"]["state_units"] ==
        std::vector<std::string>{"kg/s", "kg", "kg/s", "kg"});
    CHECK(saved_example["witnesses"][0]["replay"]["control_units"] ==
        std::vector<std::string>{"kg/s", "kg/s"});
    CHECK(saved_example["witnesses"][0]["replay"]["integration"] == "exact_discrete_map");
    CHECK(saved_example["witnesses"][0]["replay"]["control_hold"] == "constant_on_interval");
    CHECK(saved_example["witnesses"][0]["replay"]["times"] == std::vector<double>{0.0, 1.0, 2.0});

    const auto flow = ex::project_replay_trajectories(comparison, {0, 2},
        {ar::CoordinateAnnotation{"flow A", "kg/s", {}, {}},
         ar::CoordinateAnnotation{"flow B", "kg/s", {}, {}}});
    REQUIRE(std::holds_alternative<ex::ReplayTrajectoryPair>(flow));
    const auto& flow_pair = std::get<ex::ReplayTrajectoryPair>(flow);
    CHECK(flow_pair.paths.size() == 2);
    CHECK(flow_pair.paths[0].points.size() == 3);
    CHECK(flow_pair.paths[0].points.back() == std::array<double, 2>{2.0, 3.0});
    CHECK(flow_pair.paths[1].points.back() == std::array<double, 2>{1.5, 2.0});
    CHECK(flow_pair.state_axis.kind == ar::PlotAxis::Kind::physical_time);
    CHECK(flow_pair.state_axis.unit == "s");

    const auto stock = ex::project_replay_trajectories(comparison, {1, 3},
        {ar::CoordinateAnnotation{"stock A", "kg", {}, {}},
         ar::CoordinateAnnotation{"stock B", "kg", {}, {}}});
    REQUIRE(std::holds_alternative<ex::ReplayTrajectoryPair>(stock));
    CHECK(std::get<ex::ReplayTrajectoryPair>(stock).paths[0].points.back() == std::array<double, 2>{0.0, 0.0});
    CHECK(std::get<ex::ReplayTrajectoryPair>(stock).paths[1].points.back() == std::array<double, 2>{0.75, 1.0});

    const auto encoded = ex::encode_replay_comparison(comparison);
    REQUIRE(std::holds_alternative<problem::ResolvedContent>(encoded));
    const auto& content = std::get<problem::ResolvedContent>(encoded);
    const std::string wire(reinterpret_cast<const char*>(content.bytes().data()), content.bytes().size());
    CHECK(wire.find("csl.viz04-replay-comparison/1") != std::string::npos);
    CHECK(wire.find("linear_objective_convention") != std::string::npos);
    CHECK(wire.find("replay_time_ns") != std::string::npos);
    const auto encoded_json = nlohmann::json::parse(wire);
    CHECK(encoded_json["witnesses"][0]["policy_class"] == "selected_linear_witness");
    CHECK(encoded_json["witnesses"][0]["claims"]["nonlinear_feasibility"] == "not_checked");
    CHECK(encoded_json["witnesses"][0]["claims"]["nonlinear_objective_quality"] == "not_checked");
    CHECK(encoded_json["witnesses"][0]["claims"]["nonlinear_global_optimality"] == "not_checked");
    const auto& saved_residual = encoded_json["witnesses"][0]["linear_evidence"]["residuals"][0];
    CHECK(saved_residual["field"] == expected_linear_residual.field);
    CHECK(saved_residual["violation"] == expected_linear_residual.measure.violation);
    CHECK(saved_residual["scale"] == expected_linear_residual.measure.scale);
    CHECK(saved_residual["tolerance"] == expected_linear_residual.tolerance);
    CHECK(saved_residual["satisfied"] == expected_linear_residual.satisfied);
    const auto decoded = ex::decode_replay_comparison(wire);
    REQUIRE(std::holds_alternative<problem::ResolvedContent>(decoded));
    CHECK(std::get<problem::ResolvedContent>(decoded).digest() == content.digest());
    const auto limited = ex::decode_replay_comparison(wire, {wire.size(), 1, 64, 1024});
    REQUIRE(std::holds_alternative<ar::ArtifactError>(limited));
    CHECK(std::get<ar::ArtifactError>(limited).code == ar::ArtifactErrorCode::limit);
    auto malformed_json = encoded_json;
    malformed_json["witnesses"][0] = nullptr;
    const auto malformed = ex::decode_replay_comparison(malformed_json.dump());
    REQUIRE(std::holds_alternative<ar::ArtifactError>(malformed));
    CHECK(std::get<ar::ArtifactError>(malformed).code == ar::ArtifactErrorCode::invalid_input);
    auto unnamed_unavailable = encoded_json;
    unnamed_unavailable["witnesses"][0]["replay"]["status"] = "unavailable";
    unnamed_unavailable["witnesses"][0]["replay"]["original_objective"] = nullptr;
    unnamed_unavailable["witnesses"][0]["replay"]["missing_prerequisites"] = nlohmann::json::array();
    const auto missing_reason = ex::decode_replay_comparison(unnamed_unavailable.dump());
    REQUIRE(std::holds_alternative<ar::ArtifactError>(missing_reason));
    CHECK(std::get<ar::ArtifactError>(missing_reason).code == ar::ArtifactErrorCode::invalid_input);
}

TEST_CASE("replay association refuses swapped control order, mismatched axes and bad projections") {
    auto source = fixture();
    const auto swapped = sim::replay(fuel_toy(), std::vector<Vector>{{1.0, 1.0}, {0.0, 0.0}});
    source.replays[1] = swapped;
    const ar::RunRecordRef run_ref{source.plot.run, problem::ContentDigest{}};
    const auto wrong_controls = ex::associate_replays(source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_controls));
    CHECK(std::get<ar::ArtifactError>(wrong_controls).code == ar::ArtifactErrorCode::reference);
    CHECK(std::get<ar::ArtifactError>(wrong_controls).path == "witnesses[1].replay.controls");

    source = fixture();
    source.plot.state_axis.points = {0.0, 1.0, 3.0};
    const auto wrong_axis = ex::associate_replays(source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_axis));
    CHECK(std::get<ar::ArtifactError>(wrong_axis).path.find("replay.times") != std::string::npos);

    source = fixture();
    const auto associated = ex::associate_replays(source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ex::ReplayComparison>(associated));
    const auto invalid_projection = ex::project_replay_trajectories(std::get<ex::ReplayComparison>(associated), {0, 4}, {});
    CHECK(std::holds_alternative<ar::ArtifactError>(invalid_projection));
}

TEST_CASE("replay association rejects the wrong problem and inconsistent plant identity") {
    auto source = fixture();
    const ar::RunRecordRef run_ref{source.plot.run, problem::ContentDigest{}};

    source.problem.id = {"different-linear-problem"};
    const auto wrong_problem = ex::associate_replays(
        source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_problem));
    CHECK(std::get<ar::ArtifactError>(wrong_problem).code == ar::ArtifactErrorCode::identity);
    CHECK(std::get<ar::ArtifactError>(wrong_problem).path == "problem");

    source = fixture();
    source.replays[1].plant.version = "2";
    const auto wrong_plant = ex::associate_replays(
        source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_plant));
    CHECK(std::get<ar::ArtifactError>(wrong_plant).code == ar::ArtifactErrorCode::identity);
    CHECK(std::get<ar::ArtifactError>(wrong_plant).path == "witnesses[1].replay.plant");
}

TEST_CASE("selected nonzero path ordinals preserve an unavailable replay with its matching control prefix") {
    auto source = fixture();
    source.plot.paths.resize(1);
    source.plot.paths[0].source_ordinal = 17;
    source.replays = {sim::replay(fuel_toy(), std::vector<Vector>{{0.0, 0.0}})};
    const ar::RunRecordRef run_ref{source.plot.run, problem::ContentDigest{}};
    const auto associated = ex::associate_replays(source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ex::ReplayComparison>(associated));
    const auto& witness = std::get<ex::ReplayComparison>(associated).witnesses.front();
    CHECK(witness.linear.source_ordinal == 17);
    CHECK(witness.nonlinear.status == sim::ReplayStatus::unavailable);
    CHECK(witness.nonlinear.missing_prerequisites == std::vector<std::string>{"controls.complete_history"});
}

TEST_CASE("unrestored historical plant parameters keep replay unavailable and unclaimed") {
    auto source = fixture();
    source.plot.paths.resize(1);
    auto unrestored = fuel_toy();
    unrestored.identity = {"archival-reference", "unrestored", "missing historical plant data fixture"};
    unrestored.parameters.reset();
    source.replays = {sim::replay(unrestored, source.plot.paths[0].controls)};
    const ar::RunRecordRef run_ref{source.plot.run, problem::ContentDigest{}};

    const auto associated = ex::associate_replays(
        source.problem, source.plot, run_ref, source.replays);
    REQUIRE(std::holds_alternative<ex::ReplayComparison>(associated));
    const auto& comparison = std::get<ex::ReplayComparison>(associated);
    const auto& witness = comparison.witnesses.front();
    CHECK(witness.nonlinear.status == sim::ReplayStatus::unavailable);
    CHECK(witness.nonlinear.original_objective == std::nullopt);
    CHECK(witness.nonlinear.missing_prerequisites == std::vector<std::string>{"plant.parameters"});
    CHECK(witness.claims.nonlinear_feasibility == verification::CheckStatus::not_checked);
    CHECK(witness.claims.nonlinear_objective_quality == verification::CheckStatus::not_checked);
    CHECK(witness.claims.nonlinear_global_optimality == verification::CheckStatus::not_checked);

    const auto encoded = ex::encode_replay_comparison(comparison);
    REQUIRE(std::holds_alternative<problem::ResolvedContent>(encoded));
    const auto& content = std::get<problem::ResolvedContent>(encoded);
    const std::string wire(reinterpret_cast<const char*>(content.bytes().data()), content.bytes().size());
    const auto document = nlohmann::json::parse(wire);
    CHECK(document["witnesses"][0]["replay"]["status"] == "unavailable");
    CHECK(document["witnesses"][0]["replay"]["missing_prerequisites"] ==
        std::vector<std::string>{"plant.parameters"});
    CHECK(document["witnesses"][0]["replay"]["original_objective"].is_null());
    CHECK(document["witnesses"][0]["claims"]["nonlinear_global_optimality"] == "not_checked");
}
