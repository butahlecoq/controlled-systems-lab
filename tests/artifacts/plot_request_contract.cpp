#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/plot_request.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/polyhedral_support.hpp>
#include <csl/numeric/data.hpp>
#include <csl/problem/validator.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

#include <memory>
#include <stop_token>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace geo = csl::geometry::polyhedral;
namespace reg = csl::registry;
namespace sets = csl::sets;

template<class T, class... Rest>
T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

sets::SetData h_set(std::string id, std::size_t dimension, Matrix a, Vector b,
    Matrix e = {0, 0, {}}, Vector f = {}, std::vector<std::string> labels = {}) {
    return take(sets::make_h({std::move(id), dimension, std::move(labels)},
        {take(numeric::snapshot(a)), take(numeric::snapshot_vector(b)),
         take(numeric::snapshot(e)), take(numeric::snapshot_vector(f))}));
}

sets::SetData box4(std::string id = "fuel-like-box") {
    return h_set(std::move(id), 4,
        {8, 4, {1,0,0,0, -1,0,0,0, 0,1,0,0, 0,-1,0,0,
                  0,0,1,0, 0,0,-1,0, 0,0,0,1, 0,0,0,-1}},
        {2,0,1,1,2,0,1,1}, {0,4,{}}, {},
        {"oxidizer flow", "oxidizer stock", "fuel flow", "fuel stock"});
}

sets::SetData line4() {
    return h_set("fuel-like-line", 4,
        {2, 4, {1,0,0,0, -1,0,0,0}}, {1,1},
        {3, 4, {-2,1,0,0, -3,0,1,0, -4,0,0,1}}, {0,0,0},
        {"oxidizer flow", "oxidizer stock", "fuel flow", "fuel stock"});
}

sets::SetData box4_v() {
    Matrix vertices{16, 4, Vector(64)};
    for (std::size_t mask = 0; mask < 16; ++mask) {
        vertices.values[mask * 4] = (mask & 1) ? 2.0 : 0.0;
        vertices.values[mask * 4 + 1] = (mask & 2) ? 1.0 : -1.0;
        vertices.values[mask * 4 + 2] = (mask & 4) ? 2.0 : 0.0;
        vertices.values[mask * 4 + 3] = (mask & 8) ? 1.0 : -1.0;
    }
    return take(sets::make_v({{"fuel-like-box-v"}, 4,
        {"oxidizer flow", "oxidizer stock", "fuel flow", "fuel stock"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(Matrix{0,4,{}}))}));
}

ar::PlotData plot_data() {
    ar::PlotData data;
    data.problem = {"fuel-like-analytic-fixture"};
    data.run = {"fuel-like-run"};
    data.strategy = {"fixture-strategy"};
    data.strategy_version = "1";
    data.state_axis.kind = ar::PlotAxis::Kind::stage;
    data.state_axis.points = {0.0, 1.0};
    data.control_axis.kind = ar::PlotAxis::Kind::stage;
    data.control_axis.points = {0.0};
    data.control_axis.interval_ends = {1.0};
    data.states.coordinates = {
        {"oxidizer flow", "kg/s", {}, {}},
        {"oxidizer working-stock balance", "kg", {}, {}},
        {"fuel flow", "kg/s", {}, {}},
        {"fuel working-stock balance", "kg", {}, {}}};
    data.controls.coordinates.resize(1);
    ar::PlotEvidence evidence{
        verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass,
        verification::CheckStatus::numerical_pass,
        verification::CheckStatus::unsupported,
        verification::CheckStatus::unsupported,
        verification::CheckStatus::unsupported, {}};
    data.paths.push_back({data.run, 0, data.strategy, "1",
        {{1.0, 2.0, 3.0, -0.5}, {1.5, 1.0, 2.5, -1.5}},
        {{0.0}}, 5.0, std::move(evidence)});
    return data;
}

std::shared_ptr<const OptimalFamily> verified_one_state_family() {
    auto control_set = h_set("fuel-family-control", 1,
        {2, 1, {1, -1}}, {1, 0}, {0, 1, {}}, {}, {"u"}).as_handle();
    Dynamics dynamics{{1,1,0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,0,{}}, {0}}};
    Problem input{{"fuel-family-fixture"},
        std::make_shared<const SystemModel>(SystemModel{std::move(dynamics), {}}),
        {0,1,2}, KnownInitial{{0}}, ContinuousDomain{{control_set, control_set}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, QuadraticTerminal{{1,1,{2}}, {-2}, 1}};
    auto problem = take(problem::resolve(input,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));

    FamilyRequest family;
    family.profile = synthesis::strategy_ts01::profile_id;
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {synthesis::strategy_ts01::strategy_id};
    configuration.representation = family.representation;
    registry::StrategyRequest request{std::move(problem), std::move(configuration), std::move(family), {}, {}};
    registry::StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(synthesis::strategy_ts01::make_registration()).has_value());
    registry::Requirements requirements;
    requirements.output.representation = request.family.representation;
    requirements.output.family = request.family.target;
    requirements.output.completeness = registry::Completeness::established;
    auto prepared = take(strategies.prepare(request, requirements));
    auto workspace = prepared.create();
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    auto result = take(workspace->run(context));
    REQUIRE(result.family.has_value());
    return std::make_shared<const OptimalFamily>(std::move(*result.family));
}

ar::PlotProjectionSource const* source_ptr(const std::shared_ptr<const ar::PlotProjectionSource>& source) {
    return source.get();
}

std::shared_ptr<const ar::PlotProjectionSource> set_source(const sets::SetData& data) {
    ar::StateRelationCoordinates map{{{0,1,2,3}, {0,1,2,3}}};
    auto result = ar::make_reachable_set_source(data.as_handle(), {"fuel-like-analytic-fixture"}, std::move(map));
    REQUIRE(std::holds_alternative<std::shared_ptr<const ar::PlotProjectionSource>>(result));
    return std::get<std::shared_ptr<const ar::PlotProjectionSource>>(std::move(result));
}

reg::PreparedProvider<reg::GeometryPort> h_projection_provider() {
    reg::Registry<reg::GeometryPort> registry;
    auto entry = geo::make_projection_registration({geo::ProjectionOutput::h, 256});
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    reg::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    return take(reg::prepare_provider(reg::select_provider(registry, method, requirements)));
}

reg::PreparedProvider<reg::GeometryPort> support_provider() {
    reg::Registry<reg::GeometryPort> registry;
    auto entry = geo::make_support_registration();
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    return take(reg::prepare_provider(reg::select_provider(registry, method)));
}

bool contains_h2(const SetHandle& handle, const std::array<double, 2>& point) {
    const auto imported = sets::from_handle(handle);
    if (!std::holds_alternative<sets::SetData>(imported)) return false;
    const auto& data = std::get<sets::SetData>(imported);
    const auto representation = data.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) return false;
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        double value = 0;
        for (std::size_t col = 0; col < 2; ++col) value += h->inequalities(row, col) * point[col];
        if (value > h->upper_bounds[row]) return false;
    }
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double value = 0;
        for (std::size_t col = 0; col < 2; ++col) value += h->equalities(row, col) * point[col];
        if (value != h->equality_values[row]) return false;
    }
    return true;
}

struct Spy {
    int created{};
    int applied{};
};
class SpyWorkspace final : public SetOperatorWorkspace {
    Spy& spy_;
public:
    explicit SpyWorkspace(Spy& spy) : spy_(spy) {}
    OperationOutcome apply(const OperationRequest&, const ExecutionContext&) override {
        ++spy_.applied;
        return Unsupported{{{DiagnosticCode::unsupported, "spy", "not used by trajectory request"}}};
    }
};
reg::PreparedProvider<reg::GeometryPort> spy_provider(Spy& spy) {
    reg::Registry<reg::GeometryPort> registry;
    reg::Registration<reg::GeometryPort> entry{
        {{"test.geometry.spy"}, "1"},
        [](const OperationRequest& request, const reg::Requirements&) -> reg::Capability {
            return reg::Offer{{{"test.projection"}, request.assurance, request.required_relation, {}, {}}};
        },
        [&spy](const OperationRequest&) {
            ++spy.created;
            return std::make_unique<SpyWorkspace>(spy);
        }, {}};
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    return take(reg::prepare_provider(reg::select_provider(registry, method)));
}
}

TEST_CASE("ordinary selected-witness pair plots never call the geometry provider") {
    auto data = plot_data();
    Spy spy;
    auto provider = spy_provider(spy);
    const auto outcome = ar::make_plot(data,
        ar::PlotRequest::trajectory_pair({1,3}), provider);
    REQUIRE(std::holds_alternative<ar::PlotTrajectoryPair>(outcome));
    const auto& plotted = std::get<ar::PlotTrajectoryPair>(outcome);
    CHECK(plotted.kind == ar::PlotSampleKind::selected_witnesses);
    CHECK(plotted.kind != ar::PlotSampleKind::support_samples);
    REQUIRE(plotted.paths.size() == 1);
    CHECK(plotted.paths[0].points == std::vector<std::array<double,2>>{{2.0,-0.5},{1.0,-1.5}});
    REQUIRE(plotted.terminal_samples.size() == 1);
    CHECK(plotted.terminal_samples[0].point == std::array<double,2>{1.0,-1.5});
    CHECK(spy.created == 0);
    CHECK(spy.applied == 0);
}

TEST_CASE("every ordered pair of distinct 4D fuel coordinates projects to its analytic rectangle") {
    auto data = plot_data();
    auto source = set_source(box4());
    auto provider = h_projection_provider();
    for (std::size_t first = 0; first < 4; ++first) {
        for (std::size_t second = 0; second < 4; ++second) {
            if (first == second) continue;
            const auto request = ar::PlotRequest::set_projection(source, StageIndex{1},
                {first, second}, SetRelation::equivalent, Assurance::numerical,
                {"rectangle-" + std::to_string(first) + "-" + std::to_string(second)},
                {"rectangle-projection"});
            const auto outcome = ar::make_plot(data, request, provider);
            REQUIRE(std::holds_alternative<ar::PlotSetProjection>(outcome));
            const auto& projection = std::get<ar::PlotSetProjection>(outcome);
            CHECK(projection.reference.identity.problem == data.problem);
            CHECK(projection.reference.identity.request == std::get<ar::SetProjectionRequest>(request.source).request);
            CHECK(projection.reference.inputs == std::vector<SetId>{box4().metadata()->id});
            CHECK(projection.relation == SetRelation::equivalent);
            CHECK(std::holds_alternative<Unestablished>(projection.support));
            CHECK(projection.coordinates[0].label == data.states.coordinates[first].label);
            CHECK(projection.coordinates[1].label == data.states.coordinates[second].label);
            CHECK(projection.coordinates[0].unit == data.states.coordinates[first].unit);
            CHECK(projection.coordinates[1].unit == data.states.coordinates[second].unit);
            CHECK(projection.cost.geometry_operation_elapsed.count() >= 0);
            const auto lower = [](std::size_t coordinate) { return coordinate % 2 == 0 ? 0.0 : -1.0; };
            const auto upper = [](std::size_t coordinate) { return coordinate % 2 == 0 ? 2.0 : 1.0; };
            CHECK(contains_h2(projection.projected_relation,
                {lower(first), lower(second)}));
            CHECK(contains_h2(projection.projected_relation,
                {(lower(first) + upper(first)) / 2, (lower(second) + upper(second)) / 2}));
            CHECK(contains_h2(projection.projected_relation,
                {upper(first), upper(second)}));
            CHECK_FALSE(contains_h2(projection.projected_relation,
                {upper(first) + 0.01, (lower(second) + upper(second)) / 2}));
        }
    }
}

TEST_CASE("a lower-dimensional 4D relation projects to the hand-derived line") {
    auto data = plot_data();
    auto source = set_source(line4());
    auto provider = h_projection_provider();
    const auto request = ar::PlotRequest::set_projection(source, StageIndex{1}, {1,3},
        SetRelation::equivalent, Assurance::numerical, {"line-projection"}, {"line-pair"});
    const auto outcome = ar::make_plot(data, request, provider);
    REQUIRE(std::holds_alternative<ar::PlotSetProjection>(outcome));
    const auto& projection = std::get<ar::PlotSetProjection>(outcome);
    CHECK(contains_h2(projection.projected_relation, {-2.0,-4.0}));
    CHECK(contains_h2(projection.projected_relation, {0.0,0.0}));
    CHECK(contains_h2(projection.projected_relation, {2.0,4.0}));
    CHECK_FALSE(contains_h2(projection.projected_relation, {0.0,1.0}));
    CHECK_FALSE(contains_h2(projection.projected_relation, {3.0,6.0}));
}

TEST_CASE("support queries return explicitly tagged finite 2D support samples") {
    auto data = plot_data();
    const auto relation = box4_v();
    auto map = ar::StateRelationCoordinates{{{0,1,2,3},{0,1,2,3}}};
    auto source_result = ar::make_reachable_set_source(relation.as_handle(), data.problem, std::move(map));
    REQUIRE(std::holds_alternative<std::shared_ptr<const ar::PlotProjectionSource>>(source_result));
    auto source = std::get<std::shared_ptr<const ar::PlotProjectionSource>>(std::move(source_result));
    auto provider = support_provider();
    std::vector<ar::SupportSampleDirection> directions{
        {{{1.0,0.0}}, {"support-east"}, {"support-east-value"}},
        {{{-1.0,0.0}}, {"support-west"}, {"support-west-value"}},
        {{{0.0,1.0}}, {"support-north"}, {"support-north-value"}},
        {{{0.0,-1.0}}, {"support-south"}, {"support-south-value"}}};
    const auto request = ar::PlotRequest::support_samples(source, StageIndex{1}, {2,3},
        std::move(directions), Assurance::numerical);
    const auto outcome = ar::make_plot(data, request, provider);
    REQUIRE(std::holds_alternative<ar::PlotSupportSamples>(outcome));
    const auto& samples = std::get<ar::PlotSupportSamples>(outcome);
    CHECK(samples.kind == ar::PlotSampleKind::support_samples);
    REQUIRE(samples.samples.size() == 4);
    CHECK(std::get<double>(samples.samples[0].value) == 2.0);
    REQUIRE(samples.samples[0].point.has_value());
    CHECK((*samples.samples[0].point)[0] == 2.0);
    CHECK(std::get<double>(samples.samples[1].value) == 0.0);
    REQUIRE(samples.samples[1].point.has_value());
    CHECK((*samples.samples[1].point)[0] == 0.0);
    CHECK(std::get<double>(samples.samples[2].value) == 1.0);
    REQUIRE(samples.samples[2].point.has_value());
    CHECK((*samples.samples[2].point)[1] == 1.0);
    CHECK(std::get<double>(samples.samples[3].value) == 1.0);
    REQUIRE(samples.samples[3].point.has_value());
    CHECK((*samples.samples[3].point)[1] == -1.0);
    CHECK(std::holds_alternative<SymbolicArgument>(samples.samples[0].support));
    CHECK(samples.samples[0].reference.identity.request == RequestId{"support-east"});
    CHECK(samples.cost.geometry_operation_elapsed.count() >= 0);

    auto h_source = set_source(box4());
    const auto unsupported = ar::PlotRequest::support_samples(h_source, StageIndex{1}, {2,3},
        {{{{1.0,0.0}}, {"unsupported-h-support"}, {"unsupported-h-support-value"}}},
        Assurance::numerical);
    const auto unsupported_outcome = ar::make_plot(data, unsupported, provider);
    REQUIRE(std::holds_alternative<ar::PlotRequestFailure>(unsupported_outcome));
    CHECK(std::holds_alternative<reg::Rejection>(
        std::get<ar::PlotRequestFailure>(unsupported_outcome).cause));
    CHECK_FALSE(std::get<ar::PlotRequestFailure>(unsupported_outcome).cost.has_value());

    const auto duplicate_ids = ar::PlotRequest::support_samples(source, StageIndex{1}, {2,3},
        {{{{1.0,0.0}}, {"duplicate-sample"}, {"first-output"}},
         {{{0.0,1.0}}, {"duplicate-sample"}, {"second-output"}}}, Assurance::numerical);
    const auto duplicate_outcome = ar::make_plot(data, duplicate_ids, provider);
    REQUIRE(std::holds_alternative<ar::PlotRequestFailure>(duplicate_outcome));
    CHECK(std::holds_alternative<ar::ArtifactError>(
        std::get<ar::PlotRequestFailure>(duplicate_outcome).cause));
    CHECK_FALSE(std::get<ar::PlotRequestFailure>(duplicate_outcome).cost.has_value());
}

TEST_CASE("a registry-verified complete optimal family binds its native relation") {
    const auto family = verified_one_state_family();
    REQUIRE(family->registry_verified());
    ar::StateRelationCoordinates map{{{0}, {2}, {4}}};
    auto source = ar::make_optimal_family_source(*family, std::move(map));
    REQUIRE(std::holds_alternative<std::shared_ptr<const ar::PlotProjectionSource>>(source));
    const auto& projected_source = *std::get<std::shared_ptr<const ar::PlotProjectionSource>>(source);
    CHECK(projected_source.coordinates().by_stage ==
        std::vector<std::vector<std::size_t>>{{0}, {2}, {4}});
    CHECK(std::get<FamilyIdentity>(projected_source.owner().identity) == family->identity());
    REQUIRE(projected_source.family_evidence().has_value());
    CHECK(projected_source.family_evidence()->family == family->identity());
    CHECK(projected_source.family_evidence()->registry_verified);
    CHECK(projected_source.relation().id == std::get<CompleteOptimalFamily>(family->outcome()).relation.payload
        ->h_relation_for_recording()->metadata()->id);
}

TEST_CASE("an unverified family is rejected as a projection source") {
    const auto id = ProblemId{"unverified-projection-family"};
    FamilyRequest request;
    request.profile = "unsupported-fixture";
    request.objective = id;
    request.target = FamilyTarget::candidate_relaxation;
    request.representation = {"csl.polyhedron.h"};
    FamilyIdentity identity{id, request, {{1,0,0}, 1}, {"fixture.strategy"}, "1", {}};
    CandidateFamily candidate{{identity.coordinates, request.representation,
        std::make_shared<const JointRelationPayload>()}, HeuristicRelationEvidence{"fixture"}, Unestablished{}};
    auto published = FamilyPublisher::publish(identity, OptimalFamilyOutcome{std::move(candidate)});
    REQUIRE(std::holds_alternative<OptimalFamily>(published));
    auto source = ar::make_optimal_family_source(std::get<OptimalFamily>(published), {{{0},{0}}});
    REQUIRE(std::holds_alternative<Diagnostics>(source));
    CHECK(std::get<Diagnostics>(source).front().code == DiagnosticCode::unsupported);
}

TEST_CASE("empty and unbounded 4D sets retain their projected set semantics") {
    auto data = plot_data();
    auto provider = h_projection_provider();
    const auto map = ar::StateRelationCoordinates{{{0,1,2,3},{0,1,2,3}}};
    const auto empty = take(sets::make_empty({{"empty-four-state"},4,{}}));
    auto empty_source_result = ar::make_reachable_set_source(empty.as_handle(), data.problem, map);
    REQUIRE(std::holds_alternative<std::shared_ptr<const ar::PlotProjectionSource>>(empty_source_result));
    auto empty_source = std::get<std::shared_ptr<const ar::PlotProjectionSource>>(std::move(empty_source_result));
    const auto empty_request = ar::PlotRequest::set_projection(empty_source, StageIndex{1}, {0,3},
        SetRelation::equivalent, Assurance::numerical, {"empty-projection"}, {"empty-projection-output"});
    const auto empty_outcome = ar::make_plot(data, empty_request, provider);
    REQUIRE(std::holds_alternative<ar::PlotSetProjection>(empty_outcome));
    CHECK_FALSE(contains_h2(std::get<ar::PlotSetProjection>(empty_outcome).projected_relation, {0.0,0.0}));

    const auto universal = take(sets::make_universal({{"universal-four-state"},4,{}}));
    auto universal_source_result = ar::make_reachable_set_source(universal.as_handle(), data.problem, map);
    REQUIRE(std::holds_alternative<std::shared_ptr<const ar::PlotProjectionSource>>(universal_source_result));
    auto universal_source = std::get<std::shared_ptr<const ar::PlotProjectionSource>>(std::move(universal_source_result));
    const auto universal_request = ar::PlotRequest::set_projection(universal_source, StageIndex{1}, {0,3},
        SetRelation::equivalent, Assurance::numerical, {"universal-projection"}, {"universal-projection-output"});
    const auto universal_outcome = ar::make_plot(data, universal_request, provider);
    REQUIRE(std::holds_alternative<ar::PlotSetProjection>(universal_outcome));
    CHECK(contains_h2(std::get<ar::PlotSetProjection>(universal_outcome).projected_relation, {-100.0,75.0}));
}

TEST_CASE("invalid coordinate pairs and unsupported exact evidence fail before geometry execution") {
    auto data = plot_data();
    auto source = set_source(box4());
    auto provider = h_projection_provider();
    const auto duplicate = ar::PlotRequest::set_projection(source, StageIndex{1}, {2,2},
        SetRelation::equivalent, Assurance::numerical, {"duplicate-pair"}, {"duplicate-output"});
    const auto duplicate_outcome = ar::make_plot(data, duplicate, provider);
    REQUIRE(std::holds_alternative<ar::PlotRequestFailure>(duplicate_outcome));
    CHECK(std::holds_alternative<ar::ArtifactError>(std::get<ar::PlotRequestFailure>(duplicate_outcome).cause));

    const auto out_of_range = ar::PlotRequest::set_projection(source, StageIndex{1}, {0,4},
        SetRelation::equivalent, Assurance::numerical, {"out-of-range"}, {"out-of-range-output"});
    const auto out_of_range_outcome = ar::make_plot(data, out_of_range, provider);
    REQUIRE(std::holds_alternative<ar::PlotRequestFailure>(out_of_range_outcome));
    CHECK(std::holds_alternative<ar::ArtifactError>(std::get<ar::PlotRequestFailure>(out_of_range_outcome).cause));

    const auto exact = ar::PlotRequest::set_projection(source, StageIndex{1}, {0,3},
        SetRelation::equivalent, Assurance::validated, {"validated-exact"}, {"validated-exact-output"});
    const auto exact_outcome = ar::make_plot(data, exact, provider);
    REQUIRE(std::holds_alternative<ar::PlotRequestFailure>(exact_outcome));
    CHECK(std::holds_alternative<reg::Rejection>(std::get<ar::PlotRequestFailure>(exact_outcome).cause));
    CHECK_FALSE(std::get<ar::PlotRequestFailure>(exact_outcome).cost.has_value());
}
