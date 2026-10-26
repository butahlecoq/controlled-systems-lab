#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/artifacts/stage_projection_capture.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>

namespace {
using namespace csl;
namespace ar = csl::artifacts;
namespace geo = csl::geometry::polyhedral;
namespace reg = csl::registry;

template<class T, class... Rest>
T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

sets::SetData cube(std::string id) {
    Matrix a{6, 3, {1,0,0, -1,0,0, 0,1,0, 0,-1,0, 0,0,1, 0,0,-1}};
    Vector b{1,0,1,0,1,0};
    return take(sets::make_h({{std::move(id)}, 3, {"x", "y", "z"}},
        {take(numeric::snapshot(a)), take(numeric::snapshot_vector(b)),
         take(numeric::snapshot(Matrix{0,3,{}})), take(numeric::snapshot_vector({}))}));
}

reg::PreparedProvider<reg::GeometryPort> projection_provider() {
    reg::Registry<reg::GeometryPort> registry;
    auto entry = geo::make_projection_registration({geo::ProjectionOutput::h, 64});
    const auto method = reg::Method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    reg::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    return take(reg::prepare_provider(reg::select_provider(registry, method, requirements)));
}

ar::StageProjectionInput available_stage(std::size_t stage, const sets::SetData& set) {
    ar::StageProjectionSet source;
    source.relation = set.as_handle();
    source.owner = {{"fuel-analytic-fixture"}, set.metadata()->id};
    source.relation_coordinates = {0, 1, 2};
    return {{stage}, static_cast<double>(stage), std::move(source)};
}

ar::StageProjectionCaptureRequest request(std::vector<ar::StageProjectionInput> stages) {
    return {{"fuel-analytic-fixture"}, {"capture"},
        {{"oxidizer flow", "kg/s", {}, {}}, {"oxidizer stock", "kg", {}, {}},
            {"fuel flow", "kg/s", {}, {}}},
        {{{ar::CoordinateName{"oxidizer flow"}, ar::CoordinateOrdinal{2}}}},
        std::move(stages), SetRelation::equivalent, Assurance::numerical};
}
}

TEST_CASE("stage projection capture returns one projection or explicit gap per pair and stage") {
    const auto initial = cube("fuel-initial");
    const auto terminal = cube("fuel-terminal");
    auto input = request({available_stage(0, initial), available_stage(1, terminal),
        {{2}, 2.0, ar::StageProjectionGap{ar::StageProjectionGap::Kind::missing,
            "route stopped before R2", {}}}});
    const auto outcome = ar::capture_stage_projections(input, projection_provider());
    REQUIRE(std::holds_alternative<ar::StageProjectionBatchCapture>(outcome));
    const auto& batch = std::get<ar::StageProjectionBatchCapture>(outcome);
    REQUIRE(batch.records.size() == 3);
    CHECK(batch.required_relation == SetRelation::equivalent);
    CHECK(batch.requested_assurance == Assurance::numerical);
    CHECK(batch.records[0].stage.value == 0);
    CHECK(batch.records[0].pair.first == 0);
    CHECK(batch.records[0].pair.second == 2);
    REQUIRE(std::holds_alternative<ar::PlotSetProjection>(batch.records[0].outcome));
    const auto& projection = std::get<ar::PlotSetProjection>(batch.records[0].outcome);
    CHECK(projection.coordinates[0].label == "oxidizer flow");
    CHECK(projection.coordinates[1].label == "fuel flow");
    CHECK(projection.projected_relation.metadata.dimension == 2);
    CHECK(projection.reference.identity.problem.value == "fuel-analytic-fixture");
    CHECK(projection.reference.identity.request.value == "capture/pair/0/stage/0");
    REQUIRE(projection.reference.inputs.size() == 1);
    CHECK(projection.reference.inputs.front() == initial.metadata()->id);
    REQUIRE(batch.records[0].source_assurance.has_value());
    CHECK(*batch.records[0].source_assurance == Assurance::numerical);
    CHECK(projection.cost.geometry_operation_elapsed.count() >= 0);
    REQUIRE(std::holds_alternative<ar::StageProjectionUnavailable>(batch.records[2].outcome));
    CHECK(std::get<ar::StageProjectionUnavailable>(batch.records[2].outcome).kind ==
        ar::StageProjectionGap::Kind::missing);

    auto inconsistent = input;
    inconsistent.state_coordinates[0].label = "changed route label";
    const auto routed_name = ar::capture_stage_projections(inconsistent, projection_provider());
    CHECK(std::holds_alternative<ar::ArtifactError>(routed_name));
}

TEST_CASE("stage projection capture preserves ordered pairs and rejects invalid references") {
    const auto initial = cube("fuel-initial");
    auto input = request({available_stage(0, initial)});
    input.coordinate_pairs = {
        {ar::CoordinateOrdinal{0}, ar::CoordinateOrdinal{2}},
        {ar::CoordinateOrdinal{2}, ar::CoordinateOrdinal{0}}};
    const auto outcome = ar::capture_stage_projections(input, projection_provider());
    REQUIRE(std::holds_alternative<ar::StageProjectionBatchCapture>(outcome));
    const auto& batch = std::get<ar::StageProjectionBatchCapture>(outcome);
    REQUIRE(batch.records.size() == 2);
    CHECK(batch.records[0].pair.first == 0);
    CHECK(batch.records[0].pair.second == 2);
    CHECK(batch.records[1].pair.first == 2);
    CHECK(batch.records[1].pair.second == 0);

    input.coordinate_pairs.push_back(input.coordinate_pairs.front());
    const auto duplicate = ar::capture_stage_projections(input, projection_provider());
    CHECK(std::holds_alternative<ar::ArtifactError>(duplicate));

    input.coordinate_pairs = {{ar::CoordinateName{"unknown"}, ar::CoordinateOrdinal{0}}};
    const auto unknown = ar::capture_stage_projections(input, projection_provider());
    CHECK(std::holds_alternative<ar::ArtifactError>(unknown));

    input.coordinate_pairs = {{ar::CoordinateOrdinal{1}, ar::CoordinateOrdinal{1}}};
    const auto repeated = ar::capture_stage_projections(input, projection_provider());
    CHECK(std::holds_alternative<ar::ArtifactError>(repeated));

    input.coordinate_pairs = {{ar::CoordinateOrdinal{8}, ar::CoordinateOrdinal{0}}};
    const auto out_of_range = ar::capture_stage_projections(input, projection_provider());
    CHECK(std::holds_alternative<ar::ArtifactError>(out_of_range));
}
