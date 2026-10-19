#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/lazy.hpp>
#include <csl/geometry/polyhedral_support.hpp>
#include <csl/numeric/data.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

#include <iostream>
#include <chrono>
#include <cmath>
#include <limits>
#include <stop_token>

using namespace csl;
using namespace csl::registry;

namespace {
template<class T, class... Alternatives> T take(std::variant<T, Alternatives...> result) {
    if (!std::holds_alternative<T>(result)) std::visit([](const auto& item) {
        if constexpr (requires { item.diagnostics.begin()->field; })
            for (const auto& diagnostic : item.diagnostics)
                std::cerr << diagnostic.field << ": " << diagnostic.explanation << '\n';
        if constexpr (requires { item.begin(); item.end(); })
            for (const auto& diagnostic : item)
                if constexpr (requires { diagnostic.field; })
                    std::cerr << diagnostic.field << ": " << diagnostic.explanation << '\n';
    }, result);
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T, class Variant> T alternative(Variant result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

SetHandle square() {
    return take(sets::make_v({{"square"}, 2, {"x", "y"}},
        {take(numeric::snapshot(Matrix{4, 2, {0, 0, 1, 0, 0, 1, 1, 1}})),
         take(numeric::snapshot(Matrix{0, 2, {}}))})).as_handle();
}

OperationOutcome create(const OperationRequest& request) {
    Registry<GeometryPort> registry;
    auto entry = geometry::lazy::make_expression_registration();
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.geometry.lazy-v"};
    requirements.output.relation = SetRelation::equivalent;
    auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    auto pipeline = take(provider.prepare(request));
    return std::get<0>(pipeline.create())->run({});
}

PreparedProvider<GeometryPort> leaf_support_provider() {
    Registry<GeometryPort> registry;
    auto entry = geometry::polyhedral::make_support_registration();
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    return take(prepare_provider(select_provider(registry, method)));
}

PreparedProvider<GeometryPort> lazy_support_provider() {
    Registry<GeometryPort> registry;
    auto entry = geometry::lazy::make_support_registration(leaf_support_provider());
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    return take(prepare_provider(select_provider(registry, method)));
}

OperationOutcome support(const SetHandle& input, Vector direction, std::string request_id) {
    auto provider = lazy_support_provider();
    OperationRequest request{{{"p"}, {std::move(request_id)}, {"sampled-support"}},
        {"csl.geometry.lazy-support"}, SupportQuery{input, std::move(direction)},
        SetRelation::equivalent, Assurance::numerical};
    auto pipeline = take(provider.prepare(request));
    return std::get<0>(pipeline.create())->run({});
}
}

TEST_CASE("lazy affine expression retains its source and copied operands") {
    auto source = square();
    Matrix map{2, 2, {2, 0, 0, 1}};
    Vector offset{1, -1};
    OperationRequest request{{{"p"}, {"affine-request"}, {"affine-result"}},
        {"csl.geometry.lazy-expression"}, AffineImage{source, map, offset},
        SetRelation::equivalent, Assurance::numerical};

    const auto output = take<OperationResult>(create(request));
    auto& original = std::get<AffineImage>(request.operation);
    original.map.values[0] = 99;
    original.offset[0] = 99;
    source = {};

    CHECK(output.output.id == SetId{"affine-result"});
    CHECK(output.output.metadata.dimension == 2);
    CHECK(output.output.metadata.representation == RepresentationId{"csl.geometry.lazy-v"});
    CHECK(output.relation == SetRelation::equivalent);
    CHECK(output.evidence.reference.identity == request.identity);
    CHECK(output.evidence.reference.inputs == std::vector<SetId>{{"square"}});
    CHECK(std::holds_alternative<Unestablished>(output.evidence.support));
    auto description = take<geometry::lazy::ExpressionDescription>(
        geometry::lazy::inspect_expression(output.output));
    const auto& affine = std::get<AffineImage>(description.operation);
    CHECK(affine.map.values == Vector{2, 0, 0, 1});
    CHECK(affine.offset == Vector{1, -1});
    CHECK(take(sets::from_handle(affine.input)).metadata()->set.dimension == 2);
}

TEST_CASE("lazy expression rejects forged envelope and validated assurance") {
    OperationRequest request{{{"p"}, {"forgery-image"}, {"forgery-lazy"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {1, 0, 0, 1}}, {0, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto handle = take<OperationResult>(create(request)).output;
    auto forged = handle;
    forged.id = {"different-output"};
    CHECK(std::holds_alternative<Diagnostics>(geometry::lazy::inspect_expression(forged)));
    forged = handle;
    forged.metadata.dimension = 3;
    CHECK(std::holds_alternative<Diagnostics>(geometry::lazy::inspect_expression(forged)));
    request.assurance = Assurance::validated;
    Registry<GeometryPort> registry;
    auto entry = geometry::lazy::make_expression_registration();
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.geometry.lazy-v"};
    requirements.output.relation = SetRelation::equivalent;
    const auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    CHECK(std::holds_alternative<Rejection>(provider.prepare(request)));
}

TEST_CASE("lazy support matches a transformed square and its nested projection") {
    const auto source = square();
    OperationRequest affine{{{"p"}, {"affine"}, {"mapped-square"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{source, {2, 2, {2, 0, 0, 1}}, {1, -1}},
        SetRelation::equivalent, Assurance::numerical};
    const auto mapped = take<OperationResult>(create(affine)).output;
    const auto mapped_answer = alternative<SupportResult>(support(mapped, {1, 1}, "mapped-query"));
    REQUIRE(std::holds_alternative<double>(mapped_answer.value));
    CHECK(std::get<double>(mapped_answer.value) == 3.0);
    CHECK(mapped_answer.maximizer == Vector{3, 0});
    CHECK(mapped_answer.evidence.reference.inputs == std::vector<SetId>{{"mapped-square"}});
    CHECK(std::holds_alternative<Unestablished>(mapped_answer.evidence.support));

    OperationRequest projection{{{"p"}, {"projection"}, {"mapped-x"}},
        {"csl.geometry.lazy-expression"}, Projection{mapped, {0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto projected = take<OperationResult>(create(projection)).output;
    const auto projected_answer = alternative<SupportResult>(support(projected, {1}, "projected-query"));
    REQUIRE(std::holds_alternative<double>(projected_answer.value));
    CHECK(std::get<double>(projected_answer.value) == 3.0);
    CHECK(projected_answer.maximizer == Vector{3});
}

TEST_CASE("finite support directions remain labelled samples") {
    OperationRequest affine{{{"p"}, {"affine"}, {"mapped-square"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {2, 0, 0, 1}}, {1, -1}},
        SetRelation::equivalent, Assurance::numerical};
    const auto mapped = take<OperationResult>(create(affine)).output;
    const auto provider = lazy_support_provider();
    const GeometryRequestIdentity identity{{"p"}, {"two-directions"}, {"sample-only"}};
    const auto samples = alternative<geometry::lazy::SupportSamples>(
        geometry::lazy::sample_support(provider, mapped, {{1, 0}, {0, 1}}, identity, {}));
    CHECK(samples.coverage == geometry::lazy::SampleCoverage::directions_only);
    CHECK(samples.reference == GeometryReference{identity, {{"mapped-square"}}});
    REQUIRE(samples.samples.size() == 2);
    CHECK(samples.samples[0].direction == Vector{1, 0});
    CHECK(std::get<double>(samples.samples[0].answer.value) == 3.0);
    CHECK(samples.samples[1].direction == Vector{0, 1});
    CHECK(std::get<double>(samples.samples[1].answer.value) == 0.0);
}

TEST_CASE("lazy support admission checks the selected leaf provider") {
    OperationRequest expression_request{{{"p"}, {"refused-affine"}, {"refused-lazy"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {1, 0, 0, 1}}, {0, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(expression_request)).output;
    Registry<GeometryPort> leaves;
    auto refusing_leaf = geometry::polyhedral::make_support_registration();
    refusing_leaf.capabilities = [](const OperationRequest&, const Requirements&) -> Capability {
        return Diagnostics{{DiagnosticCode::unsupported, "test.leaf", "Leaf provider refuses the query."}};
    };
    const Method leaf_method{refusing_leaf.identity.id, refusing_leaf.identity.version};
    REQUIRE_FALSE(leaves.add(std::move(refusing_leaf)).has_value());
    const auto leaf_provider = take(prepare_provider(select_provider(leaves, leaf_method)));
    Registry<GeometryPort> lazy_registry;
    auto lazy_entry = geometry::lazy::make_support_registration(leaf_provider);
    const Method lazy_method{lazy_entry.identity.id, lazy_entry.identity.version};
    REQUIRE_FALSE(lazy_registry.add(std::move(lazy_entry)).has_value());
    const auto lazy_provider = take(prepare_provider(select_provider(lazy_registry, lazy_method)));
    OperationRequest query{{{"p"}, {"refused-query"}, {"refused-support"}},
        {"csl.geometry.lazy-support"}, SupportQuery{expression, {1, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto admitted = lazy_provider.prepare(query);
    REQUIRE(std::holds_alternative<Rejection>(admitted));
    const auto& diagnostics = std::get<Rejection>(admitted).diagnostics;
    REQUIRE(diagnostics.size() == 1);
    CHECK(diagnostics[0].field == "test.leaf");
}

TEST_CASE("explicit materialization reports V growth and rejects a smaller vertex budget") {
    OperationRequest affine{{{"p"}, {"affine"}, {"mapped-square"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {2, 0, 0, 1}}, {1, -1}},
        SetRelation::equivalent, Assurance::numerical};
    const auto mapped = take<OperationResult>(create(affine)).output;
    OperationRequest sum{{{"p"}, {"sum"}, {"sum-square"}},
        {"csl.geometry.lazy-expression"}, MinkowskiSum{mapped, mapped},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(sum)).output;
    ConversionRequest request{{{"p"}, {"materialize"}, {"sum-v"}},
        expression, {"csl.polyhedron.v"}, Assurance::numerical};

    auto run = [&](std::size_t max_vertices) {
        Registry<ConversionPort> registry;
        auto entry = geometry::lazy::make_materializer({max_vertices, 0});
        const Method method{entry.identity.id, entry.identity.version};
        REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
        Requirements requirements;
        requirements.output.representation = {"csl.polyhedron.v"};
        requirements.output.relation = SetRelation::equivalent;
        auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
        return geometry::lazy::materialize_expression(request, {max_vertices, 0}, provider, {});
    };

    const auto success = alternative<geometry::lazy::MaterializationResult>(run(16));
    CHECK(success.growth.source_vertices == 8);
    CHECK(success.growth.estimated_vertices == 16);
    CHECK(success.growth.realized_vertices == 16);
    CHECK(success.growth.realized_rays == 0);
    CHECK(success.budget.max_vertices == 16);
    CHECK(success.result.output.id == SetId{"sum-v"});
    CHECK(success.result.evidence.reference.inputs == std::vector<SetId>{{"sum-square"}});
    const auto data = take(sets::from_handle(success.result.output));
    const auto vertices = std::get<sets::VRepresentation>(data.representation()).vertices;
    CHECK(vertices.rows() == 16);
    CHECK(vertices.cols() == 2);
    const auto lazy_answer = alternative<SupportResult>(
        support(expression, {1, 1}, "sum-lazy-reference"));
    CHECK(std::get<double>(lazy_answer.value) == 6.0);
    auto polyhedral = leaf_support_provider();
    OperationRequest direct_query{{{"p"}, {"sum-polyhedral-reference"}, {"sum-support"}},
        {"csl.geometry.polyhedral-support"}, SupportQuery{success.result.output, {1, 1}},
        SetRelation::equivalent, Assurance::numerical};
    auto direct_pipeline = take(polyhedral.prepare(direct_query));
    const auto direct_answer = alternative<SupportResult>(
        std::get<0>(direct_pipeline.create())->run({}));
    CHECK(std::get<double>(direct_answer.value) == 6.0);
    CHECK(std::get<double>(lazy_answer.value) == std::get<double>(direct_answer.value));

    const auto failure = alternative<geometry::lazy::MaterializationFailure>(run(15));
    CHECK(failure.budget.max_vertices == 15);
    CHECK(failure.growth.estimated_vertices == 16);
    CHECK(failure.growth.realized_vertices == 0);
    CHECK(std::holds_alternative<Unsupported>(failure.cause));
    CHECK(failure.reference.identity == request.identity);
}

TEST_CASE("shared singleton expression materializes once per node rather than expanding the graph") {
    auto point = take(sets::make_v({{"point"}, 1, {}},
        {take(numeric::snapshot(Matrix{1, 1, {1}})),
         take(numeric::snapshot(Matrix{0, 1, {}}))})).as_handle();
    for (std::size_t level = 0; level < 30; ++level) {
        const auto name = "sum-" + std::to_string(level);
        OperationRequest request{{{"p"}, {name}, {name}},
            {"csl.geometry.lazy-expression"}, MinkowskiSum{point, point},
            SetRelation::equivalent, Assurance::numerical};
        point = take<OperationResult>(create(request)).output;
    }
    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({1, 0});
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    const auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    ConversionRequest request{{{"p"}, {"shared-materialization"}, {"shared-v"}},
        point, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto result = alternative<geometry::lazy::MaterializationResult>(
        geometry::lazy::materialize_expression(request, {1, 0}, provider, {}));
    CHECK(result.growth.source_vertices == (std::size_t{1} << 30));
    CHECK(result.growth.realized_vertices == 1);
    const auto native = take(sets::from_handle(result.result.output)).representation();
    CHECK(std::get<sets::VRepresentation>(native).vertices(0, 0) == 1073741824.0);
    const auto support_answer = alternative<SupportResult>(support(point, {1}, "shared-support"));
    CHECK(std::get<double>(support_answer.value) == 1073741824.0);
}

TEST_CASE("affine ray support distinguishes finite and unbounded directions") {
    const auto ray = take(sets::make_v({{"ray"}, 1, {}},
        {take(numeric::snapshot(Matrix{1, 1, {0}})),
         take(numeric::snapshot(Matrix{1, 1, {1}}))})).as_handle();
    OperationRequest request{{{"p"}, {"flip"}, {"flipped-ray"}},
        {"csl.geometry.lazy-expression"}, AffineImage{ray, {1, 1, {-1}}, {2}},
        SetRelation::equivalent, Assurance::numerical};
    const auto flipped = take<OperationResult>(create(request)).output;
    const auto finite = alternative<SupportResult>(support(flipped, {1}, "finite-ray"));
    CHECK(std::get<double>(finite.value) == 2.0);
    CHECK(finite.maximizer == Vector{2});
    const auto unbounded = alternative<SupportResult>(support(flipped, {-1}, "unbounded-ray"));
    CHECK(std::holds_alternative<UnboundedSupport>(unbounded.value));
    CHECK_FALSE(unbounded.maximizer);

    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({1, 1});
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    const auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    ConversionRequest conversion{{{"p"}, {"materialize-ray"}, {"flipped-v"}},
        flipped, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto output = alternative<geometry::lazy::MaterializationResult>(
        geometry::lazy::materialize_expression(conversion, {1, 1}, provider, {}));
    const auto native = std::get<sets::VRepresentation>(
        take(sets::from_handle(output.result.output)).representation());
    CHECK(native.vertices(0, 0) == 2.0);
    CHECK(native.rays(0, 0) == -1.0);
}

TEST_CASE("affine support refuses a direction product that underflows to zero") {
    const auto ray = take(sets::make_v({{"tiny-direction-ray"}, 1, {}},
        {take(numeric::snapshot(Matrix{1, 1, {0}})),
         take(numeric::snapshot(Matrix{1, 1, {1}}))})).as_handle();
    const double tiny = std::numeric_limits<double>::min();
    OperationRequest request{{{"p"}, {"tiny-affine"}, {"tiny-image"}},
        {"csl.geometry.lazy-expression"}, AffineImage{ray, {1, 1, {tiny}}, {0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(request)).output;
    auto provider = lazy_support_provider();
    OperationRequest query{{{"p"}, {"tiny-support"}, {"sampled-support"}},
        {"csl.geometry.lazy-support"}, SupportQuery{expression, {tiny}},
        SetRelation::equivalent, Assurance::numerical};
    const auto admitted = provider.prepare(query);
    REQUIRE(std::holds_alternative<Rejection>(admitted));
    const auto& diagnostics = std::get<Rejection>(admitted).diagnostics;
    REQUIRE(diagnostics.size() == 1);
    CHECK(diagnostics[0].field == "lazy.direction");
}

TEST_CASE("affine support refuses cancellation of a nonzero exact direction") {
    const auto ray = take(sets::make_v({{"cancellation-ray"}, 1, {}},
        {take(numeric::snapshot(Matrix{1, 1, {0}})),
         take(numeric::snapshot(Matrix{1, 1, {-1}}))})).as_handle();
    const double ulp = std::ldexp(1.0, -52);
    OperationRequest request{{{"p"}, {"cancellation-affine"}, {"cancellation-image"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{ray, {2, 1, {1.0 - ulp, 1.0}}, {0, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(request)).output;
    auto provider = lazy_support_provider();
    OperationRequest query{{{"p"}, {"cancellation-support"}, {"sampled-support"}},
        {"csl.geometry.lazy-support"}, SupportQuery{expression, {1.0 + ulp, -1.0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto admitted = provider.prepare(query);
    REQUIRE(std::holds_alternative<Rejection>(admitted));
    const auto& diagnostics = std::get<Rejection>(admitted).diagnostics;
    REQUIRE(diagnostics.size() == 1);
    CHECK(diagnostics[0].field == "lazy.direction");
}

TEST_CASE("empty expression support stays empty and a cancelled materialization publishes nothing") {
    const auto empty = take(sets::make_empty({{"empty"}, 1, {}})).as_handle();
    OperationRequest request{{{"p"}, {"empty-image"}, {"empty-lazy"}},
        {"csl.geometry.lazy-expression"}, AffineImage{empty, {1, 1, {2}}, {1}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(request)).output;
    const auto answer = alternative<SupportResult>(support(expression, {1}, "empty-query"));
    CHECK(std::holds_alternative<EmptySupport>(answer.value));

    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({0, 0});
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    const auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    ConversionRequest conversion{{{"p"}, {"empty-materialization"}, {"empty-v"}},
        expression, {"csl.polyhedron.v"}, Assurance::numerical};
    std::stop_source stop_source;
    stop_source.request_stop();
    ExecutionContext cancelled;
    cancelled.cancellation = stop_source.get_token();
    const auto stopped = alternative<geometry::lazy::MaterializationFailure>(
        geometry::lazy::materialize_expression(conversion, {0, 0}, provider, cancelled));
    REQUIRE(std::holds_alternative<OperationStopped>(stopped.cause));
    CHECK(std::get<OperationStopped>(stopped.cause).reason == StopReason::cancelled);
    CHECK(stopped.growth.realized_vertices == 0);

    const auto completed = alternative<geometry::lazy::MaterializationResult>(
        geometry::lazy::materialize_expression(conversion, {0, 0}, provider, {}));
    CHECK(completed.growth.estimated_vertices == 0);
    CHECK(completed.growth.realized_vertices == 0);
    const auto native = std::get<sets::VRepresentation>(
        take(sets::from_handle(completed.result.output)).representation());
    CHECK(native.vertices.rows() == 0);
}

TEST_CASE("materialization wrapper rejects a provider with a different identity") {
    OperationRequest expression_request{{{"p"}, {"identity-image"}, {"identity-lazy"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {1, 0, 0, 1}}, {0, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(expression_request)).output;
    ConversionRequest request{{{"p"}, {"identity-materialization"}, {"identity-v"}},
        expression, {"csl.polyhedron.v"}, Assurance::numerical};
    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({4, 0});
    entry.identity.id = {"csl.geometry.some-other-converter"};
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    const auto outcome = geometry::lazy::materialize_expression(request, {4, 0}, provider, {});
    REQUIRE(std::holds_alternative<geometry::lazy::MaterializationFailure>(outcome));
    const auto& cause = std::get<geometry::lazy::MaterializationFailure>(outcome).cause;
    REQUIRE(std::holds_alternative<Unsupported>(cause));
    const auto& diagnostics = std::get<Unsupported>(cause).diagnostics;
    REQUIRE(diagnostics.size() == 1);
    CHECK(diagnostics[0].field == "lazy.provider");
}

TEST_CASE("zero-coordinate projection materializes the nonempty singleton") {
    OperationRequest projection{{{"p"}, {"zero-projection"}, {"zero-lazy"}},
        {"csl.geometry.lazy-expression"}, Projection{square(), {}},
        SetRelation::equivalent, Assurance::numerical};
    const auto expression = take<OperationResult>(create(projection)).output;
    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({4, 0});
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    ConversionRequest request{{{"p"}, {"zero-materialization"}, {"zero-v"}},
        expression, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto result = alternative<geometry::lazy::MaterializationResult>(
        geometry::lazy::materialize_expression(request, {4, 0}, provider, {}));
    CHECK(result.growth.estimated_vertices == 1);
    CHECK(result.growth.realized_vertices == 1);
    const auto native = take(sets::from_handle(result.result.output)).representation();
    const auto vertices = std::get<sets::VRepresentation>(native).vertices;
    CHECK(vertices.rows() == 1);
    CHECK(vertices.cols() == 0);
}

TEST_CASE("materialization rejects vertex growth overflow and an expired deadline") {
    auto source = take(sets::make_v({{"two-points"}, 1, {}},
        {take(numeric::snapshot(Matrix{2, 1, {0, 1}})),
         take(numeric::snapshot(Matrix{0, 1, {}}))})).as_handle();
    for (std::size_t level = 0; level < std::numeric_limits<std::size_t>::digits; ++level) {
        const auto name = "doubling-" + std::to_string(level);
        OperationRequest request{{{"p"}, {name}, {name}},
            {"csl.geometry.lazy-expression"}, MinkowskiSum{source, source},
            SetRelation::equivalent, Assurance::numerical};
        source = take<OperationResult>(create(request)).output;
    }
    Registry<ConversionPort> registry;
    auto entry = geometry::lazy::make_materializer({std::numeric_limits<std::size_t>::max(), 0});
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    const auto provider = take(prepare_provider(select_provider(registry, method, requirements)));
    ConversionRequest overflow_request{{{"p"}, {"overflow"}, {"overflow-v"}},
        source, {"csl.polyhedron.v"}, Assurance::numerical};
    const auto overflow = alternative<geometry::lazy::MaterializationFailure>(
        geometry::lazy::materialize_expression(overflow_request,
            {std::numeric_limits<std::size_t>::max(), 0}, provider, {}));
    REQUIRE(std::holds_alternative<Unsupported>(overflow.cause));
    REQUIRE_FALSE(std::get<Unsupported>(overflow.cause).diagnostics.empty());
    CHECK(std::get<Unsupported>(overflow.cause).diagnostics[0].field == "lazy.growth");

    OperationRequest small{{{"p"}, {"deadline-image"}, {"deadline-lazy"}},
        {"csl.geometry.lazy-expression"},
        AffineImage{square(), {2, 2, {1, 0, 0, 1}}, {0, 0}},
        SetRelation::equivalent, Assurance::numerical};
    const auto small_handle = take<OperationResult>(create(small)).output;
    ConversionRequest deadline_request{{{"p"}, {"deadline"}, {"deadline-v"}},
        small_handle, {"csl.polyhedron.v"}, Assurance::numerical};
    ExecutionContext expired;
    expired.deadline = std::chrono::steady_clock::now() - std::chrono::seconds(1);
    const auto deadline = alternative<geometry::lazy::MaterializationFailure>(
        geometry::lazy::materialize_expression(deadline_request, {4, 0}, provider, expired));
    REQUIRE(std::holds_alternative<OperationStopped>(deadline.cause));
    CHECK(std::get<OperationStopped>(deadline.cause).reason == StopReason::deadline_expired);
    CHECK(deadline.reference.identity == deadline_request.identity);
    CHECK(deadline.provider.actual_module == ModuleId{"csl.geometry.lazy-materializer"});
    CHECK(deadline.lineage.size() == 1);
    CHECK(deadline.growth.estimated_vertices == 4);
    CHECK(deadline.growth.realized_vertices == 0);
}
