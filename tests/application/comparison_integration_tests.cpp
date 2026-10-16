#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/application/comparison.hpp>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/observability.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/problem/validator.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>

#include <type_traits>
#include <utility>
#include <memory>
#include <string>
#include <vector>

using namespace csl;

namespace {
template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

SetHandle interval(std::string id) {
    const sets::Description description{SetId{std::move(id)}, 1, {"u"}};
    const sets::HRepresentation representation{
        take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
        take(numeric::snapshot_vector(Vector{1, 0})),
        take(numeric::snapshot(Matrix{0, 1, {}})),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description, representation)).as_handle();
}

problem::ResolvedProblem source(std::string profile) {
    Matrix a{1, 1, {1}}, b{1, 1, {1}}, e{1, 0, {}};
    const LinearStage transition{std::move(a), std::move(b), std::move(e), {0}};
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{1, 1, 0}, TimeDomain::discrete, transition}, {}});
    Problem authored;
    authored.id = {"application-paired-" + profile};
    authored.model = model;
    authored.times = {0, 1, 2};
    authored.initial = KnownInitial{{0}};
    authored.controls = ContinuousDomain{{interval("u0"), interval("u1")}};
    authored.states = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};
    authored.information = InformationPattern::nominal_open_loop;
    if (profile == "ts01_exact_integrator") {
        QuadraticTerminal objective;
        objective.Q = Matrix{1, 1, {2}};
        objective.linear = {-2};
        objective.offset = 1;
        authored.objective = objective;
    } else {
        authored.objective = LinearTerminal{{0}, 3};
    }
    return take(problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

template<class Port> registry::PreparedProvider<Port> selected(
    registry::Registration<Port> entry, std::string representation) {
    registry::Registry<Port> providers;
    const registry::Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(providers.add(std::move(entry)));
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
        std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(
        registry::select_provider(providers, method, requirements)));
}

struct Modules {
    std::shared_ptr<registry::Registry<registry::GeometryPort>> projections;
    std::shared_ptr<registry::Registry<registry::GeometryPort>> affines;
    std::shared_ptr<registry::Registry<registry::ConversionPort>> conversions;
    std::shared_ptr<registry::Registry<registry::LPPort>> lps;
    std::shared_ptr<registry::Registry<registry::ConvexPort>> convexes;
    registry::StrategyRegistry strategies;
    registry::Registry<registry::SelectorPort> selectors;
    registry::PreparedProvider<registry::LPPort> membership;

    Modules(std::shared_ptr<registry::Registry<registry::GeometryPort>> projection_registry,
        std::shared_ptr<registry::Registry<registry::GeometryPort>> affine_registry,
        std::shared_ptr<registry::Registry<registry::ConversionPort>> conversion_registry,
        std::shared_ptr<registry::Registry<registry::LPPort>> lp_registry,
        std::shared_ptr<registry::Registry<registry::ConvexPort>> convex_registry,
        registry::PreparedProvider<registry::LPPort> prepared_membership)
        : projections(std::move(projection_registry)), affines(std::move(affine_registry)),
          conversions(std::move(conversion_registry)), lps(std::move(lp_registry)),
          convexes(std::move(convex_registry)), membership(std::move(prepared_membership)) {}
};

Modules modules() {
    auto lp = take(adapters::lp::make_highs_registration());
    auto convex = take(adapters::convex::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
    auto projections = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto affines = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto conversions = std::make_shared<registry::Registry<registry::ConversionPort>>();
    auto lps = std::make_shared<registry::Registry<registry::LPPort>>();
    auto convexes = std::make_shared<registry::Registry<registry::ConvexPort>>();
    const registry::Method pm{projection.identity.id, {}}, am{affine.identity.id, {}},
        cm{converter.identity.id, {}}, lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    REQUIRE_FALSE(projections->add(projection));
    REQUIRE_FALSE(affines->add(affine));
    REQUIRE_FALSE(conversions->add(converter));
    REQUIRE_FALSE(lps->add(lp));
    REQUIRE_FALSE(convexes->add(convex));
    registry::Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"};
    h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"};
    v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(registry::check_providers(
        registry::select_provider(*projections, pm, h), registry::select_provider(*affines, am, v),
        registry::select_provider(*conversions, cm, h), registry::select_provider(*lps, lm, program),
        registry::select_provider(*convexes, qm, program)));
    auto membership = take(registry::prepare_provider(registry::select_provider(*lps, lm, program)));
    Modules result{std::move(projections), std::move(affines), std::move(conversions),
        std::move(lps), std::move(convexes), std::move(membership)};
    REQUIRE_FALSE(result.strategies.add(synthesis::strategy_a::make_registration(std::move(providers))));
    REQUIRE_FALSE(result.strategies.add(synthesis::strategy_b::make_registration(*result.lps, *result.convexes)));
    auto selector = synthesis::witness_selector::make_registration(result.membership);
    REQUIRE_FALSE(result.selectors.add(std::move(selector)));
    return result;
}

application::ComparisonRequest request_for(const problem::ResolvedProblem& problem,
    std::string profile) {
    FamilyRequest family;
    family.profile = std::move(profile);
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration reach_back;
    reach_back.strategy = {"csl.synthesis.reach-back"};
    reach_back.lp = {"csl.lp.highs"};
    reach_back.convex = {"csl.convex.highs"};
    reach_back.representation = family.representation;
    StrategyConfiguration direct_joint = reach_back;
    direct_joint.strategy = {"csl.synthesis.strategy-b"};
    return {problem, family, {reach_back, direct_joint}};
}

void check_complete_family_encoder_boundary(const problem::ResolvedProblem& problem,
    const application::PreparedComparison& prepared, const application::StrategyExecution& strategy_execution,
    std::size_t strategy_index, const WitnessRequest& witnesses) {
    namespace ar = artifacts;
    namespace ob = csl::execution::observability;
    const auto& synthesis_result = std::get<SynthesisResult>(strategy_execution.outcome);
    REQUIRE(synthesis_result.family);
    const auto expected = prepared.expected_synthesis_identity(strategy_index);
    const ar::Unavailable uninstrumented{ar::MissingReason::not_instrumented, {}};
    const ar::PinAvailability pin = uninstrumented;
    ar::ConfigurationInput input;
    input.collection = {false, ar::CollectionMode::detail, 0, 0, 0, 0};
    input.modules = {
        {"strategy", {expected.strategy, expected.strategy_version, pin}, {}},
        {"lp", {prepared.strategies()[strategy_index].lp, "1", pin}, {}},
        {"convex", {prepared.strategies()[strategy_index].convex, "1", pin}, {}}};
    input.numerical = prepared.family().numerical;
    input.resources = {1, 1, 1, {}};
    input.output = {ar::OutputKind::synthesis, prepared.family().assurance,
        prepared.family().target, prepared.family().representation, witnesses};
    input.selector = {{csl::synthesis::witness_selector::selector_id}, "1", {}};
    input.strategy = prepared.strategies()[strategy_index];
    const auto configuration = take(ar::resolve_configuration(std::move(input)));
    const ar::RunId run{"application-comparison-encoder"};
    const auto statistics = take(ob::merge_observations(
        take(ob::make_collection_plan({problem, configuration, run, {}, {}, 0})), {}));
    const auto encoded = application::encode_strategy_run(problem, strategy_execution,
        configuration, run, statistics,
        {uninstrumented, uninstrumented, uninstrumented, uninstrumented, true,
            ar::MemoryAccounting::unlimited});
    REQUIRE(std::holds_alternative<ar::ArtifactError>(encoded));
    const auto& error = std::get<ar::ArtifactError>(encoded);
    CHECK(error.code == ar::ArtifactErrorCode::unsupported);
    CHECK(error.path == "run.final.family.completeness.support");
}

void compare_profile(const std::string& profile) {
    const auto problem = source(profile);
    const auto request = request_for(problem, profile);
    auto registered = modules();
    auto admission = application::prepare_comparison(request, registered.strategies);
    REQUIRE(std::holds_alternative<application::PreparedComparison>(admission));
    const auto& prepared = std::get<application::PreparedComparison>(admission);
    registry::Requirements selection_requirements;
    selection_requirements.output.representation = {"csl.witness-batch.v1"};
    const WitnessRequest witness_request{2, 0, {{1, -1}, {-1, 1}}, 31};
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    const auto execution = application::run_comparison(prepared, registered.selectors,
        {synthesis::witness_selector::selector_id, {}}, witness_request, selection_requirements,
        context, registered.membership);

    for (std::size_t i = 0; i < execution.strategies.size(); ++i) {
        const auto& strategy = execution.strategies[i];
        REQUIRE(std::holds_alternative<SynthesisResult>(strategy.outcome));
        const auto& result = std::get<SynthesisResult>(strategy.outcome);
        REQUIRE(result.family);
        REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
        REQUIRE(std::holds_alternative<WitnessSelection>(strategy.selection));
        const auto& selected = std::get<WitnessSelection>(strategy.selection);
        REQUIRE(selected.batch.returned_count() == 2);
        REQUIRE(selected.batch.source_family == result.family->identity());
        CHECK(selected.batch.witnesses[0].controls == std::vector<Vector>{{0}, {1}});
        CHECK(selected.batch.witnesses[1].controls == std::vector<Vector>{{1}, {0}});
        CHECK(selected.batch.witnesses[0].states == std::vector<Vector>{{0}, {0}, {1}});
        CHECK(selected.batch.witnesses[1].states == std::vector<Vector>{{0}, {1}, {1}});
        const double expected_objective = profile == "ts01_exact_integrator" ? 0.0 : 3.0;
        CHECK(selected.batch.witnesses[0].original_objective == expected_objective);
        CHECK(selected.batch.witnesses[1].original_objective == expected_objective);
        REQUIRE(strategy.verification.size() == selected.batch.witnesses.size());
        const auto expected = prepared.expected_synthesis_identity(i);
        REQUIRE(expected.lineage);
        for (std::size_t j = 0; j < strategy.verification.size(); ++j) {
            const auto& report = strategy.verification[j];
            CHECK(report.input.expected_synthesis);
            CHECK(report.input.expected_synthesis->request == expected.request);
            CHECK(report.input.expected_synthesis->strategy == expected.strategy);
            CHECK(report.input.expected_synthesis->strategy_version == expected.strategy_version);
            CHECK(report.input.expected_synthesis->lineage == *expected.lineage);
            CHECK(report.bindings == verification::CheckStatus::numerical_pass);
            CHECK(report.feasibility == verification::CheckStatus::numerical_pass);
            CHECK(report.objective == verification::CheckStatus::numerical_pass);
            CHECK(report.optimality == verification::CheckStatus::unsupported);
            CHECK(report.completeness == verification::CheckStatus::unsupported);
            CHECK(report.validated == verification::CheckStatus::unsupported);
        }
    }
    check_complete_family_encoder_boundary(problem, prepared, execution.strategies[0],
        0, witness_request);
}
}

TEST_CASE("application preparation retains provider registries after module assembly returns") {
    const auto problem = source("ts01_exact_integrator");
    auto request = request_for(problem, "ts01_exact_integrator");
    auto registered = modules();
    auto admission = application::prepare_comparison(request, registered.strategies);
    REQUIRE(std::holds_alternative<application::PreparedComparison>(admission));
    const auto& prepared = std::get<application::PreparedComparison>(admission);
    CHECK(prepared.problem().identity() == problem.identity());
    CHECK(prepared.strategies().size() == 2);
    const auto workspaces = prepared.create();
    CHECK(workspaces[0] != nullptr);
    CHECK(workspaces[1] != nullptr);
}
TEST_CASE("application composes and verifies paired T-S01 complete families") {
    compare_profile("ts01_exact_integrator");
}

TEST_CASE("application composes and verifies paired T-S02 complete families") {
    compare_profile("ts02_constant_integrator");
}
