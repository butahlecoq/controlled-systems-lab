#include <csl/model/discrete_catalogue.hpp>
#include <csl/model/linear_system.hpp>
#include <doctest/doctest.h>

#include <cmath>
#include <numeric>
#include <set>
#include <string>

namespace {
template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
}

TEST_CASE("all supplied models support native discrete stepping without choosing a task") {
    using namespace csl;
    using namespace csl::model::catalogue;
    const auto catalogue = discrete_models();
    REQUIRE(catalogue.size() == 35);
    std::set<std::string> identifiers;
    for (const auto &info : catalogue) {
        CHECK(identifiers.emplace(info.id).second);
        const auto data = take<DiscreteModelData>(make_discrete_model(info.id));
        const auto n = data.initial_state.size();
        CHECK(data.info.id == info.id);
        CHECK(data.states.size() == n);
        CHECK(data.controls.size() == data.coefficients.B.cols);
        CHECK(data.external.size() == data.coefficients.E.cols);
        CHECK(data.info.source.sha256 ==
              "6c5e7c1b09331186b8cd9ddfcd1a71afbc7bddb438a103f2fd4dcfdf780c081e");
        REQUIRE(data.time_step.value > 0);
        const Vector times{0, data.time_step.value};
        const auto system = take<model::LinearSystem>(model::snapshot(data.system_model(), times));
        const Vector u(data.controls.size(), 0), w(data.external.size(), 0);
        const auto next = take<Vector>(system.step({0}, data.initial_state, u, w));
        REQUIRE(next.size() == n);
        for (const auto value : next)
            CHECK(std::isfinite(value));
    }
    CHECK(std::holds_alternative<Diagnostics>(make_discrete_model("unknown-model")));
}

TEST_CASE("published quadcopter coefficients retain the source indexed coordinates") {
    using namespace csl;
    using namespace csl::model::catalogue;
    const auto data = take<DiscreteModelData>(make_discrete_model("catalogue-2026/model-21/1"));
    REQUIRE(data.states.size() == 12);
    REQUIRE(data.controls.size() == 4);
    CHECK(data.time_step.value == 0.1);
    CHECK(data.time_step.unit == "second");
    const auto system =
        take<model::LinearSystem>(model::snapshot(data.system_model(), Vector{0, 0.1}));
    const auto next = take<Vector>(
        system.step({0}, data.initial_state, Vector{0.1, -0.2, 0.3, -0.4}, Vector(12, 0)));
    CHECK(next[0] == doctest::Approx(-0.01452));
    CHECK(next[1] == doctest::Approx(0.01452));
    CHECK(next[2] == doctest::Approx(-0.0152));
    CHECK(next[5] == doctest::Approx(-0.00212));
}

TEST_CASE("incidence models preserve their total under zero external input") {
    using namespace csl;
    using namespace csl::model::catalogue;
    for (const auto number : {1, 9, 10, 19}) {
        const auto data = take<DiscreteModelData>(
            make_discrete_model("catalogue-2026/model-" + std::to_string(number) + "/1"));
        const auto system = take<model::LinearSystem>(
            model::snapshot(data.system_model(), Vector{0, data.time_step.value}));
        const auto next =
            take<Vector>(system.step({0}, data.initial_state, Vector(data.controls.size(), 0.5),
                                     Vector(data.external.size(), 0)));
        CHECK(std::accumulate(next.begin(), next.end(), 0.0) ==
              doctest::Approx(
                  std::accumulate(data.initial_state.begin(), data.initial_state.end(), 0.0)));
    }
}

TEST_CASE("different source time units remain distinct") {
    using namespace csl::model::catalogue;
    const auto building = take<DiscreteModelData>(make_discrete_model("catalogue-2026/model-28/1"));
    const auto banks = take<DiscreteModelData>(make_discrete_model("catalogue-2026/model-30/1"));
    CHECK(building.time_step.value == 0.25);
    CHECK(building.time_step.unit == "hour");
    CHECK(banks.time_step.value == 1);
    CHECK(banks.time_step.unit == "quarter");
}
