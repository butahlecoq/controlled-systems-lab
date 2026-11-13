#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/catalogue.hpp>
#include <csl/model/linear_system.hpp>

#include <set>

namespace {
template<class T, class... Errors> T take(std::variant<T, Errors...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
}

TEST_CASE("native source cases preserve the initial box and both horizon interpretations") {
    using namespace csl;
    const auto entries = model::catalogue::discrete_reachability_cases();
    REQUIRE(entries.size() >= 2);
    CHECK(entries[0].transitions == 7);
    CHECK(entries[1].transitions == 8);
    CHECK(entries[0].id != entries[1].id);
    CHECK(entries[0].source.sha256 == entries[1].source.sha256);
    for (const auto& info : entries) {
        if (info.states.size() != 3) continue;
        const auto data = take(model::catalogue::make_discrete_reachability_case(info.id));
        const auto system = take(model::snapshot(data.model, data.time_grid));
        CHECK(system.dimensions() == Dimensions{3, 1, 0});
        CHECK(system.horizon() == info.transitions);
        CHECK(data.controls.size() == info.transitions);
        CHECK(data.initial.center() == Vector{0, 0, 0});
        CHECK(data.initial.generators().values == Vector{0.5, 0, 0, 0, 1, 0, 0, 0, 1});
        CHECK(take(system.step({0}, Vector{0.5, -1, 100}, Vector{-3}, {})) == Vector{-8.5, -7, 2.5});
        CHECK(take(system.step({0}, Vector{0.5, -1, -100}, Vector{1}, {})) == Vector{3.5, 1, 2.5});
        std::set<std::string> factors;
        for (const auto& factor : data.initial.factor_ids()) CHECK(factors.insert(factor.value).second);
        for (std::size_t k = 0; k < data.controls.size(); ++k) {
            const auto& control = data.controls[k];
            CHECK(control.center() == Vector{-1});
            CHECK(control.generators().values == Vector{2});
            REQUIRE(control.factor_ids().size() == 1);
            CHECK(factors.insert(control.factor_ids()[0].value).second);
            CHECK(take(system.time({k + 1})) == static_cast<double>(k + 1));
        }
        CHECK(factors.size() == 3 + info.transitions);
    }
}

TEST_CASE("the archival four-state model retains fifteen independent input intervals") {
    using namespace csl;
    const auto data = take(model::catalogue::make_discrete_reachability_case(
        "archival-2017-4d-scalar-reachability/1"));
    const auto system = take(model::snapshot(data.model, data.time_grid));
    CHECK(system.dimensions() == Dimensions{4, 1, 0});
    CHECK(system.horizon() == 15);
    CHECK(data.controls.size() == 15);
    CHECK(data.initial.center() == Vector(4, 0));
    const Vector radii{0.052, 5, 0.018, 1};
    for (std::size_t j = 0; j < 4; ++j) CHECK(data.initial.generators().values[5 * j] == radii[j]);
    const auto value = take(system.step({0}, Vector{1, 2, 3, 4}, Vector{0.1}, {}));
    const Vector expected{1.08976, 2.13481, 3.0975, 4.9909};
    for (std::size_t j = 0; j < 4; ++j) CHECK(value[j] == doctest::Approx(expected[j]));
    std::set<std::string> factors;
    for (const auto& factor : data.initial.factor_ids()) CHECK(factors.insert(factor.value).second);
    for (const auto& control : data.controls) {
        CHECK(control.center() == Vector{0});
        CHECK(control.generators().values == Vector{0.14});
        REQUIRE(control.factor_ids().size() == 1);
        CHECK(factors.insert(control.factor_ids()[0].value).second);
    }
    CHECK(factors.size() == 19);
}

TEST_CASE("unknown native source cases are rejected with a typed diagnostic") {
    const auto result = csl::model::catalogue::make_discrete_reachability_case("missing-case");
    REQUIRE(std::holds_alternative<csl::Diagnostics>(result));
    const auto& errors = std::get<csl::Diagnostics>(result);
    REQUIRE(errors.size() == 1);
    CHECK(errors[0].code == csl::DiagnosticCode::invalid_input);
    CHECK(errors[0].field == "model.catalogue.id");
}
