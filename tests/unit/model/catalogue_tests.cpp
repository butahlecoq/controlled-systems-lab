#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/catalogue.hpp>
#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <set>
#include <utility>

namespace {
template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
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
    for (const auto &info : entries) {
        if (!info.id.starts_with("bulaev-2016-slide33/"))
            continue;
        const auto data = take(model::catalogue::make_discrete_reachability_case(info.id));
        const auto system = take(model::snapshot(data.model, data.time_grid));
        CHECK(system.dimensions() == Dimensions{3, 1, 0});
        CHECK(system.horizon() == info.transitions);
        CHECK(data.controls.size() == info.transitions);
        CHECK(data.initial.center() == Vector{0, 0, 0});
        CHECK(data.initial.generators().values == Vector{0.5, 0, 0, 0, 1, 0, 0, 0, 1});
        CHECK(take(system.step({0}, Vector{0.5, -1, 100}, Vector{-3}, {})) ==
              Vector{-8.5, -7, 2.5});
        CHECK(take(system.step({0}, Vector{0.5, -1, -100}, Vector{1}, {})) == Vector{3.5, 1, 2.5});
        std::set<std::string> factors;
        for (const auto &factor : data.initial.factor_ids())
            CHECK(factors.insert(factor.value).second);
        for (std::size_t k = 0; k < data.controls.size(); ++k) {
            const auto &control = data.controls[k];
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
    for (std::size_t j = 0; j < 4; ++j)
        CHECK(data.initial.generators().values[5 * j] == radii[j]);
    const auto value = take(system.step({0}, Vector{1, 2, 3, 4}, Vector{0.1}, {}));
    const Vector expected{1.08976, 2.13481, 3.0975, 4.9909};
    for (std::size_t j = 0; j < 4; ++j)
        CHECK(value[j] == doctest::Approx(expected[j]));
    std::set<std::string> factors;
    for (const auto &factor : data.initial.factor_ids())
        CHECK(factors.insert(factor.value).second);
    for (const auto &control : data.controls) {
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
    const auto &errors = std::get<csl::Diagnostics>(result);
    REQUIRE(errors.size() == 1);
    CHECK(errors[0].code == csl::DiagnosticCode::invalid_input);
    CHECK(errors[0].field == "model.catalogue.id");
}

TEST_CASE("slide50 uses printed two-input dynamics and a separately authored initial box") {
    using namespace csl;
    for (const auto &variant :
         {std::pair{"bulaev-2016-slide50/authored-box/illustrated-five/1", 5u},
          std::pair{"bulaev-2016-slide50/authored-box/literal-six/1", 6u}}) {
        const auto data = take(model::catalogue::make_discrete_reachability_case(variant.first));
        const auto system = take(model::snapshot(data.model, data.time_grid));
        CHECK(system.dimensions() == Dimensions{3, 2, 0});
        CHECK(system.horizon() == variant.second);
        CHECK(data.info.controls.size() == 2);
        CHECK(data.info.source.sha256 ==
              "029d55dd5b2d2ff1682bb42ffead7e2f5f0133df78864ae5ee583028200a88e5");
        CHECK(data.info.source.qualification.find("authored") != std::string_view::npos);
        CHECK(data.info.source.qualification.find("78") != std::string_view::npos);
        CHECK(data.initial.center() == Vector{0, 0, 0});
        CHECK(data.initial.generators().values == Vector{0.5, 0, 0, 0, 1, 0, 0, 0, 1});
        const auto step = take(system.step({0}, Vector{1, 2, 3}, Vector{0.5, -0.25}, {}));
        CHECK(step[0] == doctest::Approx(2.3));
        CHECK(step[1] == doctest::Approx(-1.34));
        CHECK(step[2] == doctest::Approx(2.08));
        std::set<std::string> factors;
        for (const auto &factor : data.initial.factor_ids())
            CHECK(factors.insert(factor.value).second);
        REQUIRE(data.controls.size() == variant.second);
        for (std::size_t k = 0; k < data.controls.size(); ++k) {
            const auto &control = data.controls[k];
            CHECK(control.center() == Vector{0, 0});
            CHECK(control.generators().values == Vector{1, 0, 0, 1});
            REQUIRE(control.factor_ids().size() == 2);
            for (const auto &factor : control.factor_ids())
                CHECK(factors.insert(factor.value).second);
        }
        CHECK(factors.size() == 3 + 2 * variant.second);
    }
}

TEST_CASE("spatial deviation dynamics are discoverable through the common native catalogue") {
    using namespace csl;
    constexpr std::string_view id = "spatial-flight/b-consistent-body9-synthetic/1";
    const auto entries = model::catalogue::discrete_reachability_cases();
    const auto found =
        std::find_if(entries.begin(), entries.end(),
                     [&](const model::catalogue::CaseInfo &entry) { return entry.id == id; });
    REQUIRE(found != entries.end());
    const auto data = take(model::catalogue::make_discrete_reachability_case(id));
    const auto system = take(model::snapshot(data.model, data.time_grid));
    CHECK(system.dimensions() == Dimensions{9, 3, 0});
    CHECK(system.horizon() == 20);
    CHECK(data.info.source.qualification.find("synthetic") != std::string_view::npos);
    CHECK(data.info.states[0].name == "delta_vx");
    CHECK(data.info.states[8].name == "delta_omega_z");
    CHECK(data.initial.center() == Vector(9, 0));
    CHECK(data.initial.factor_ids().size() == 9);
    REQUIRE(data.controls.size() == 20);
    CHECK(data.controls.front().center() == Vector(3, 0));
    CHECK(data.controls.front().factor_ids().size() == 3);
    CHECK(data.info.controls[0].name == "delta_u0");
    CHECK(data.controls.front().coordinate_labels()[0] == data.info.controls[0].name);
    REQUIRE(data.time_grid.size() == 21);
    CHECK(data.time_grid.back() == doctest::Approx(1));
}
