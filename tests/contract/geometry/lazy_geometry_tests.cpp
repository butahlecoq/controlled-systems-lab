#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/lazy.hpp>
#include <csl/numeric/data.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

#include <iostream>

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
