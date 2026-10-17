#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/polyhedral_support.hpp>
#include <csl/numeric/data.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

#include <cmath>
#include <limits>
#include <variant>

using namespace csl;
using namespace csl::registry;

namespace {
template<class T, class... Alternatives> T take(std::variant<T, Alternatives...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

SetHandle v_set(std::string id, Matrix vertices, Matrix rays) {
    return take(sets::make_v({{std::move(id)}, vertices.cols(), {}},
        {take(numeric::snapshot(vertices)), take(numeric::snapshot(rays))})).as_handle();
}

OperationRequest support_request(SetHandle input, Vector direction, std::string request_id) {
    return {{{"test08"}, {std::move(request_id)}, {"support-reference"}},
        {"csl.geometry.polyhedral-support"}, SupportQuery{std::move(input), std::move(direction)},
        SetRelation::equivalent, Assurance::numerical};
}

OperationOutcome run_support(const OperationRequest& request) {
    Registry<GeometryPort> registry;
    auto entry = geometry::polyhedral::make_support_registration();
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    auto prepared = take(prepare_provider(select_provider(registry, method)));
    return std::get<0>(prepared.create())->run({});
}

void check_support_evidence(const SupportResult& result, const OperationRequest& request) {
    CHECK(result.evidence.reference.identity == request.identity);
    CHECK(result.evidence.reference.inputs == std::vector<SetId>{std::get<SupportQuery>(request.operation).input.id});
    CHECK(result.evidence.scope == GeometryClaimScope::support_value);
    CHECK(std::holds_alternative<SymbolicArgument>(result.evidence.support));
    CHECK(check_geometry_evidence(result.evidence, request).empty());
}
}

TEST_CASE("V support provider returns finite interval maximum and a maximizer") {
    const auto interval = v_set("unit-interval", {2, 1, {0, 1}}, {0, 1, {}});
    const auto request = support_request(interval, {1}, "finite-interval");
    const auto outcome = run_support(request);
    REQUIRE(std::holds_alternative<SupportResult>(outcome));
    const auto& result = std::get<SupportResult>(outcome);
    REQUIRE(std::holds_alternative<double>(result.value));
    CHECK(std::get<double>(result.value) == 1.0);
    REQUIRE(result.maximizer);
    CHECK(*result.maximizer == Vector{1.0});
    check_support_evidence(result, request);
}

TEST_CASE("V support provider distinguishes the empty set") {
    const auto empty = take(sets::make_empty({{"empty-support-set"}, 1, {}})).as_handle();
    const auto request = support_request(empty, {1}, "empty-support");
    const auto outcome = run_support(request);
    REQUIRE(std::holds_alternative<SupportResult>(outcome));
    const auto& result = std::get<SupportResult>(outcome);
    CHECK(std::holds_alternative<EmptySupport>(result.value));
    CHECK_FALSE(result.maximizer);
    check_support_evidence(result, request);
}

TEST_CASE("ray support is unbounded in its positive direction and finite in its negative direction") {
    const auto ray = v_set("positive-ray", {1, 1, {0}}, {1, 1, {1}});
    const auto positive_request = support_request(ray, {1}, "ray-positive");
    const auto positive = run_support(positive_request);
    REQUIRE(std::holds_alternative<SupportResult>(positive));
    CHECK(std::holds_alternative<UnboundedSupport>(std::get<SupportResult>(positive).value));
    CHECK_FALSE(std::get<SupportResult>(positive).maximizer);
    check_support_evidence(std::get<SupportResult>(positive), positive_request);

    const auto negative_request = support_request(ray, {-1}, "ray-negative");
    const auto negative = run_support(negative_request);
    REQUIRE(std::holds_alternative<SupportResult>(negative));
    const auto& result = std::get<SupportResult>(negative);
    REQUIRE(std::holds_alternative<double>(result.value));
    CHECK(std::get<double>(result.value) == 0.0);
    REQUIRE(result.maximizer);
    CHECK(*result.maximizer == Vector{0.0});
    check_support_evidence(result, negative_request);
}

TEST_CASE("exact ray dot signs detect positive support hidden by rounded cancellation") {
    const double large = std::ldexp(1.0, 100);
    const double tiny = std::numeric_limits<double>::denorm_min();
    const auto ray = v_set("cancellation-ray", {1, 3, {0, 0, 0}},
        {1, 3, {large, tiny, -large}});
    CHECK((large + tiny + -large) == 0.0);
    const auto request = support_request(ray, {1, 1, 1}, "ray-exact-positive-dot");
    const auto outcome = run_support(request);
    REQUIRE(std::holds_alternative<SupportResult>(outcome));
    CHECK(std::holds_alternative<UnboundedSupport>(std::get<SupportResult>(outcome).value));
    CHECK_FALSE(std::get<SupportResult>(outcome).maximizer);
    check_support_evidence(std::get<SupportResult>(outcome), request);
}

TEST_CASE("support provider rejects representations outside its V and empty profile") {
    const auto h = take(sets::make_h({{"interval-h"}, 1, {}},
        {take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
         take(numeric::snapshot_vector(Vector{1, 0})),
         take(numeric::snapshot(Matrix{0, 1, {}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
    const auto request = support_request(h, {1}, "unsupported-h");
    Registry<GeometryPort> registry;
    auto entry = geometry::polyhedral::make_support_registration();
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    const auto prepared = prepare_provider(select_provider(registry, method));
    CHECK(std::holds_alternative<Rejection>(prepared));
    REQUIRE(std::holds_alternative<Rejection>(prepared));
    REQUIRE_FALSE(std::get<Rejection>(prepared).diagnostics.empty());
    CHECK(std::get<Rejection>(prepared).diagnostics.front().field == "support.representation");
}
