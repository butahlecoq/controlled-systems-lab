#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/stage_projection_batch.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <fstream>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace geo = csl::geometry::polyhedral;
namespace reg = csl::registry;

template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

reg::PreparedProvider<reg::GeometryPort> provider() {
    reg::Registry<reg::GeometryPort> registry;
    auto entry = geo::make_projection_registration({geo::ProjectionOutput::v, 64});
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    reg::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    return take(reg::prepare_provider(reg::select_provider(registry, method, requirements)));
}

sets::SetData cube() {
    Matrix vertices{8, 3, {-1,-1,-1, -1,-1,1, -1,1,-1, -1,1,1,
                            1,-1,-1, 1,-1,1, 1,1,-1, 1,1,1}};
    Matrix rays{0, 3, {}};
    return take(sets::make_v({{"cube"}, 3, {"x", "y", "z"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

sets::SetData line_with_interior_vertex() {
    Matrix vertices{3, 3, {0,0,0, 1e16,0,1e16+2, 1e16+2,0,1e16+4}};
    Matrix rays{0, 3, {}};
    return take(sets::make_v({{"line"}, 3, {"x", "y", "z"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

sets::SetData point_with_duplicate_vertices() {
    Matrix vertices{3, 3, {5,0,7, 5,0,7, 5,0,7}};
    Matrix rays{1, 3, {0,1,0}};
    return take(sets::make_v({{"point"}, 3, {"x", "y", "z"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

sets::SetData empty_v_with_ray() {
    Matrix vertices{0, 3, {}};
    Matrix rays{1, 3, {1,0,0}};
    return take(sets::make_v({{"empty"}, 3, {"x", "y", "z"}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))}));
}

ar::StageProjectionSet projection_source(const sets::SetData& set) {
    ar::StageProjectionSet source;
    source.relation = set.as_handle();
    source.owner = {{"fuel"}, set.metadata()->id};
    source.relation_coordinates = {0, 1, 2};
    return source;
}
}

TEST_CASE("stage projection batch JSON binds source identity and retains 2D geometry") {
    const auto source_set = cube();
    const auto line_set = line_with_interior_vertex();
    const auto point_set = point_with_duplicate_vertices();
    const auto empty_set = empty_v_with_ray();
    ar::StageProjectionSet source;
    source.relation = source_set.as_handle();
    source.owner = {{"fuel"}, source_set.metadata()->id};
    source.relation_coordinates = {0, 1, 2};
    ar::StageProjectionCaptureRequest request{{"fuel"}, {"stage-batch"},
        {{"oxidizer flow", "kg/s", {}, {}}, {"oxidizer stock", "kg", {}, {}}, {"fuel flow", "kg/s", {}, {}}},
        {{{ar::CoordinateOrdinal{0}, ar::CoordinateOrdinal{2}}}},
        {{{0}, 0.0, source}, {{1}, 1.0, projection_source(line_set)},
            {{2}, 2.0, projection_source(point_set)}, {{3}, 3.0, projection_source(empty_set)}},
        SetRelation::equivalent, Assurance::numerical};
    const auto capture = ar::capture_stage_projections(request, provider());
    REQUIRE(std::holds_alternative<ar::StageProjectionBatchCapture>(capture));

    ar::StageProjectionBatchIdentity identity{{"run-1"}, "fuel-route", "csl.run-statistics/7", std::string(64, 'a'),
        request.state_coordinates, {{0, 2}}, {ar::PlotAxis::Kind::stage, {0.0, 1.0, 2.0, 3.0}, {}, {}}, {}};
    identity.trajectory_series.push_back({{"run-1"}, {0, 2}, {{-1.0, -1.0}, {1.0, 1.0}, {5.0, 7.0}, {0.0, 0.0}}, "selected witness only"});
    const auto encoded = ar::encode_stage_projection_batch_json(identity,
        std::get<ar::StageProjectionBatchCapture>(capture));
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto& json = std::get<std::string>(encoded);
    std::ifstream fixture(CSL_STAGE_PROJECTION_BATCH_FIXTURE);
    REQUIRE(fixture.good());
    const std::string expected((std::istreambuf_iterator<char>(fixture)), std::istreambuf_iterator<char>());
    CHECK(json == expected);
    CHECK(json.find("csl.stage-projection-batch/1") != std::string::npos);
    CHECK(json.find("fuel-route") != std::string::npos);
    CHECK(json.find("conv_vertices_plus_cone_rays") != std::string::npos);
    CHECK(json.find("\"kind\": \"polygon\"") != std::string::npos);
    CHECK(json.find("\"kind\": \"segment\"") != std::string::npos);
    CHECK(json.find("\"kind\": \"point\"") != std::string::npos);
}

TEST_CASE("stage projection batch JSON rejects reordered pairs and bad source hashes") {
    ar::StageProjectionBatchCapture empty{{"fuel"}, {"capture"}, SetRelation::equivalent,
        Assurance::numerical, {}};
    ar::StageProjectionBatchIdentity identity{{"run"}, "route", "record/1", std::string(64, 'a'),
        {{"x", {}}, {"y", {}}}, {{0, 1}}, {ar::PlotAxis::Kind::stage, {0.0}, {}, {}}, {}};
    auto encoded = ar::encode_stage_projection_batch_json(identity, empty);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(encoded));
    CHECK(std::get<ar::ArtifactError>(encoded).path == "records");
    identity.stage_axis.points = {0.0, 2.0, 4.0};
    encoded = ar::encode_stage_projection_batch_json(identity, empty);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(encoded));
    CHECK(std::get<ar::ArtifactError>(encoded).path == "stage_axis.points");
    identity.stage_axis.points = {0.0};
    identity.source_record_sha256 = "not-a-digest";
    encoded = ar::encode_stage_projection_batch_json(identity, empty);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(encoded));
    CHECK(std::get<ar::ArtifactError>(encoded).path == "identity");
}

TEST_CASE("stage projection batch records and binds optional 2D materialization evidence") {
    const auto set = cube();
    auto source = projection_source(set);
    source.owner.problem = {"materialization"};
    ar::StageProjectionCaptureRequest request{{"materialization"}, {"stage-batch"},
        {{"x", {}, {}, {}}, {"y", {}, {}, {}}, {"z", {}, {}, {}}},
        {{{ar::CoordinateOrdinal{0}, ar::CoordinateOrdinal{2}}}},
        {{{0}, 0.0, source}}, SetRelation::equivalent, Assurance::numerical};
    auto captured = ar::capture_stage_projections(request, provider());
    REQUIRE(std::holds_alternative<ar::StageProjectionBatchCapture>(captured));
    auto batch = std::get<ar::StageProjectionBatchCapture>(std::move(captured));
    auto& success = std::get<ar::StageProjectionSuccess>(batch.records.front().outcome);
    const auto& projection = success.projection.projected_relation;
    ar::StageProjectionSuccess::Materialization materialization;
    materialization.relation = projection;
    materialization.evidence.reference.identity = {
        batch.problem, {"stage-batch/materialize"}, {projection.id.value}};
    materialization.evidence.reference.inputs = {projection.id};
    materialization.evidence.scope = GeometryClaimScope::set_relation;
    materialization.evidence.support = Unestablished{};
    materialization.evidence.assumptions = {"equivalent 2D view"};
    materialization.provider = success.projection.provider;
    success.materialization = materialization;

    ar::StageProjectionBatchIdentity identity{{"run"}, "route", "record/1", std::string(64, 'a'),
        request.state_coordinates, {{0, 2}}, {ar::PlotAxis::Kind::stage, {0.0}, {}, {}}, {}};
    const auto encoded = ar::encode_stage_projection_batch_json(identity, batch);
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto document = nlohmann::json::parse(std::get<std::string>(encoded));
    const auto& evidence = document["records"][0]["outcome"]["evidence"];
    REQUIRE(evidence.size() == 2);
    CHECK(evidence[1]["input_set_ids"] == nlohmann::json::array({projection.id.value}));
    CHECK(evidence[1]["ideal_output_id"] == projection.id.value);
    CHECK(evidence[1]["provider"]["id"] == success.projection.provider.actual->id.value);

    success.materialization->evidence.reference.inputs = {{"wrong-input"}};
    const auto rejected = ar::encode_stage_projection_batch_json(identity, batch);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(rejected));
    CHECK(std::get<ar::ArtifactError>(rejected).path == "records.outcome.materialization");
}
