#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/plot_data.hpp>
#include <csl/execution/observability.hpp>

#include <limits>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace ob = csl::execution::observability;

template<class T, class... Rest>
T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

struct Fixture {
    problem::ResolvedProblem problem;
    ar::RunStatistics run;
    std::vector<verification::TrajectoryReport> reports;
};

ar::ResolvedConfiguration configuration(const problem::ResolvedProblem& problem) {
    (void)problem;
    ar::ConfigurationInput input;
    input.collection = {false, ar::CollectionMode::summary, 0, 0, 0, 0};
    const ar::PinAvailability pin = ar::Unavailable{ar::MissingReason::not_instrumented, {}};
    input.modules = {
        {"lp", {{"fuel-test-lp"}, "1", pin}, {}},
        {"strategy", {{"fuel-test-strategy"}, "1", pin}, {}}};
    input.numerical = {1e-9, 1e-9};
    input.resources = {1, 1, 1, {}};
    input.output = {ar::OutputKind::synthesis, Assurance::numerical,
        FamilyTarget::exact_optimal_relation, {"csl.polyhedron.h"}, {2, 0.01, {}, {}}};
    input.selector = {{"fuel-test-selector"}, "1", {}};
    input.strategy = {{"fuel-test-strategy"}, {"fuel-test-lp"}, {}, {}, {}, {}, {},
        {"fuel-test-selector"}, {"csl.polyhedron.h"}};
    input.workspace = ar::WorkspacePolicy::fresh;
    return take(ar::resolve_configuration(std::move(input)));
}

Fixture fixture() {
    Matrix a{4, 4, {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1}};
    Matrix b{4, 2, {0,0, 0,0, 0,0, 0,0}};
    Matrix e{4, 0, {}};
    auto model = std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{4, 2, 0}, TimeDomain::discrete,
            LinearStage{std::move(a), std::move(b), std::move(e), {0,0,0,0}}}, {}});
    Problem authored;
    authored.id = {"fuel-plot-analytic-two-step"};
    authored.model = std::move(model);
    authored.times = {0.0, 0.5, 2.0};
    authored.initial = KnownInitial{{1.0, 2.0, -0.5, -1.5}};
    authored.controls = ContinuousDomain{{UniversalSet{2}, UniversalSet{2}}};
    authored.states = {UniversalSet{4}, UniversalSet{4}, UniversalSet{4}};
    authored.information = InformationPattern::nominal_open_loop;
    authored.objective = LinearTerminal{{0,0,0,0}, 0};
    auto resolved = take(problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));

    const auto config = configuration(resolved);
    const ar::RunId run_id{"fuel-plot-run"};
    const auto collection_plan = take(ob::make_collection_plan(
        {resolved, config, run_id, {}, {}, 0}));
    const auto collection = take(ob::merge_observations(collection_plan, {}));
    const Witness witness{resolved.identity(),
        {{1.0,2.0,-0.5,-1.5}, {1.0,2.0,-0.5,-1.5}, {1.0,2.0,-0.5,-1.5}},
        {{0.25,-0.3}, {0.25,-0.3}}, 0.0};
    WitnessBatch batch{{witness, witness}, 2, {"fuel-test-selector"}, {}, {}, {}, 0.01};
    ar::RunRecord record{resolved.identity(), {4,2,0}, 2, config, run_id,
        ar::UnsupportedFinal{{{DiagnosticCode::unsupported, "fixture", "analytic plot fixture"}}},
        collection,
        {ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}}, true, ar::MemoryAccounting::unlimited},
        {}, {}, ar::ProblemProvenance::problem_revalidated};
    record.selection = WitnessSelection{std::move(batch), Termination::completed,
        "two selected observations, one duplicate"};
    auto run = take(ar::publish_run({resolved, std::move(record)}));

    std::vector<verification::TrajectoryReport> reports;
    for (const auto& selected : run.description().selection->batch.witnesses) {
        verification::TrajectoryRequest request{selected};
        reports.push_back(verification::verify_trajectory(resolved, request));
    }
    return {std::move(resolved), std::move(run), std::move(reports)};
}

ar::PlotMetadata fuel_metadata() {
    const auto target = [](double value, std::string source) {
        return ar::CoordinateAnnotation::ReferencedValue{value, std::move(source)};
    };
    ar::PlotMetadata metadata;
    metadata.time_unit = "s";
    metadata.states = {
        {"oxidizer flow", "kg/s", target(1.2, "source.x_target[0]"), std::nullopt},
        {"oxidizer working-stock balance", "kg", std::nullopt,
            std::pair{target(-5.0, "source.x_bounds[1].lower"), target(10.0, "source.x_bounds[1].upper")}},
        {"fuel flow", "kg/s", target(0.8, "source.x_target[2]"), std::nullopt},
        {"fuel working-stock balance", "kg", std::nullopt,
            std::pair{target(-8.0, "source.x_bounds[3].lower"), target(12.0, "source.x_bounds[3].upper")}}};
    metadata.controls = {
        {"oxidizer flow adjustment", "kg/s", std::nullopt,
            std::pair{target(-1.0, "source.u_bounds[0].lower"), target(1.0, "source.u_bounds[0].upper")}},
        {"fuel flow adjustment", "kg/s", std::nullopt,
            std::pair{target(-1.0, "source.u_bounds[1].lower"), target(1.0, "source.u_bounds[1].upper")}}};
    return metadata;
}
}

TEST_CASE("two-step plot data keeps state points, control intervals and witness evidence aligned") {
    auto source = fixture();
    const auto result = ar::prepare_plot_data(source.problem, source.run, source.reports, fuel_metadata());
    REQUIRE(std::holds_alternative<ar::PlotData>(result));
    const auto& plot = std::get<ar::PlotData>(result);
    CHECK(plot.problem == source.problem.identity());
    CHECK(plot.state_axis.kind == ar::PlotAxis::Kind::physical_time);
    CHECK(plot.state_axis.points == std::vector<double>{0.0, 0.5, 2.0});
    CHECK(plot.control_axis.kind == ar::PlotAxis::Kind::physical_time);
    CHECK(plot.control_axis.points == std::vector<double>{0.0, 0.5});
    CHECK(plot.control_axis.interval_ends == std::vector<double>{0.5, 2.0});
    CHECK(plot.control_hold == ar::ControlHold::left);
    REQUIRE(plot.paths.size() == 2);
    CHECK(plot.paths[0].states.size() == 3);
    CHECK(plot.paths[0].controls.size() == 2);
    CHECK(plot.paths[0].source_ordinal == 0);
    CHECK(plot.paths[1].source_ordinal == 1);
    CHECK(plot.paths[0].evidence.feasibility == verification::CheckStatus::numerical_pass);
    CHECK(plot.paths[0].evidence.objective == verification::CheckStatus::numerical_pass);
    CHECK(plot.paths[0].evidence.optimality == verification::CheckStatus::unsupported);
    CHECK_FALSE(plot.family_evidence.current_process_verified);
    CHECK(plot.selection.requested == 2);
    CHECK(plot.selection.returned == 2);
    CHECK(plot.selection.distinct == 1);
    CHECK(plot.selection.duplicates == 1);
    CHECK(plot.selection.distinctness_tolerance == doctest::Approx(0.01));
}

TEST_CASE("fuel annotations preserve source order units bounds targets and negative stock") {
    auto source = fixture();
    auto metadata = fuel_metadata();
    const auto result = ar::prepare_plot_data(source.problem, source.run, source.reports, metadata);
    REQUIRE(std::holds_alternative<ar::PlotData>(result));
    const auto& plot = std::get<ar::PlotData>(result);
    REQUIRE(plot.states.coordinates.size() == 4);
    CHECK(plot.states.coordinates[0].label == "oxidizer flow");
    CHECK(plot.states.coordinates[0].unit == "kg/s");
    CHECK(plot.states.coordinates[0].target->value == doctest::Approx(1.2));
    CHECK(plot.states.coordinates[1].label == "oxidizer working-stock balance");
    CHECK(plot.states.coordinates[2].label == "fuel flow");
    CHECK(plot.states.coordinates[3].label == "fuel working-stock balance");
    CHECK(plot.paths[0].states[0][2] == doctest::Approx(-0.5));
    CHECK(plot.paths[0].states[0][3] == doctest::Approx(-1.5));
    REQUIRE(plot.controls.coordinates.size() == 2);
    CHECK(plot.controls.coordinates[0].bounds->first.value == doctest::Approx(-1.0));
    CHECK(plot.controls.coordinates[1].bounds->second.value == doctest::Approx(1.0));
}

TEST_CASE("plot data falls back to stage axes when a physical-time unit is absent") {
    auto source = fixture();
    auto metadata = fuel_metadata();
    metadata.time_unit.reset();
    const auto result = ar::prepare_plot_data(source.problem, source.run, source.reports, metadata);
    REQUIRE(std::holds_alternative<ar::PlotData>(result));
    const auto& plot = std::get<ar::PlotData>(result);
    CHECK(plot.state_axis.kind == ar::PlotAxis::Kind::stage);
    CHECK(plot.state_axis.points == std::vector<double>{0.0, 1.0, 2.0});
    CHECK(plot.control_axis.kind == ar::PlotAxis::Kind::stage);
    CHECK(plot.control_axis.interval_ends == std::vector<double>{1.0, 2.0});
}

TEST_CASE("plot data rejects report, problem, and source-metadata mismatches") {
    auto source = fixture();
    auto wrong_problem_reports = source.reports;
    wrong_problem_reports[0].problem.value = "foreign-problem";
    auto result = ar::prepare_plot_data(source.problem, source.run, wrong_problem_reports);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code == ar::ArtifactErrorCode::identity);

    auto wrong_subject = source.reports;
    wrong_subject[0].input.witness.problem.value = "foreign-problem";
    result = ar::prepare_plot_data(source.problem, source.run, wrong_subject);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code == ar::ArtifactErrorCode::identity);

    auto wrong_history = source.reports;
    wrong_history[0].input.witness.states.pop_back();
    result = ar::prepare_plot_data(source.problem, source.run, wrong_history);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).path == "reports[0].input.witness");

    auto missing_report = source.reports;
    missing_report.pop_back();
    result = ar::prepare_plot_data(source.problem, source.run, missing_report);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).path == "reports");

    auto malformed = fuel_metadata();
    malformed.states[0].target->source.clear();
    result = ar::prepare_plot_data(source.problem, source.run, source.reports, malformed);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).path == "metadata.states[0].target");

}
