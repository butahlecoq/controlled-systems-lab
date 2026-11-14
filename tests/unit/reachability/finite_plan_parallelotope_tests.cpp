#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <doctest/doctest.h>
#include <two_points_fixture.hpp>

#include <cmath>
#include <stop_token>

using namespace csl;
using namespace csl::reachability;

namespace {
template <class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

FixedPlanRequest two_points_request() {
    const auto full = csl::issue824::fixture::two_points_request("two-points-parallelotope");
    return {full.system,       full.initial,           {{-2.5}, {-2.5}, {-2.5}},
            full.disturbances, full.admissible_states, {"two-points-parallelotope"}};
}
sets::SetData planar_safe(std::string id, double bound) {
    return take(sets::make_h({{std::move(id)}, 2, {"x1", "x2"}},
                             {take(numeric::snapshot(Matrix{4, 2, {1, 0, -1, 0, 0, 1, 0, -1}})),
                              take(numeric::snapshot_vector(Vector{bound, bound, bound, bound})),
                              take(numeric::snapshot(Matrix{0, 2, {}})),
                              take(numeric::snapshot_vector(Vector{}))}));
}
FixedPlanRequest planar_request() {
    const SystemModel model{{{2, 1, 0},
                             TimeDomain::discrete,
                             LinearStage{{2, 2, {1, 0, 0, 1}}, {2, 1, {0, 0}}, {2, 0, {}}, {0, 0}}},
                            {}};
    const auto system = take(csl::model::snapshot(model, Vector{0, 1}));
    const auto initial =
        take(sets::make_v({{"planar-initial"}, 2, {"x1", "x2"}},
                          {take(numeric::snapshot(Matrix{4, 2, {-1, -1, 1, -1, 1, 1, -1, 1}})),
                           take(numeric::snapshot(Matrix{0, 2, {}}))}));
    const auto disturbance = take(sets::make_singleton({{"planar-disturbance"}, 0, {}},
                                                       take(numeric::snapshot_vector(Vector{}))));
    return {system,
            initial,
            {{0}},
            {disturbance},
            {planar_safe("planar-safe-initial", 2), planar_safe("planar-safe-terminal", 2)},
            {"planar-parallelotope"}};
}
sets::SetData four_state_domain(std::string id, Matrix inequalities, Vector upper_bounds,
                                Matrix equalities = {0, 4, {}}, Vector equality_values = {}) {
    return take(sets::make_h({{std::move(id)}, 4, {}},
                             {take(numeric::snapshot(std::move(inequalities))),
                              take(numeric::snapshot_vector(std::move(upper_bounds))),
                              take(numeric::snapshot(std::move(equalities))),
                              take(numeric::snapshot_vector(std::move(equality_values)))}));
}
sets::SetData wide_four_state_domain() {
    return four_state_domain("wide-four-state-domain",
                             {8, 4, {1, 0, 0, 0, -1, 0, 0,  0, 0, 1, 0, 0, 0, -1, 0, 0,
                                     0, 0, 1, 0, 0,  0, -1, 0, 0, 0, 0, 1, 0, 0,  0, -1}},
                             Vector(8, 100));
}
} // namespace

TEST_CASE("fixed non-axis frame encloses every finite TwoPoints reachable state") {
    const auto request = two_points_request();
    const auto enclosure = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<FinitePlanParallelotopeTrace>(enclosure));
    const auto exact = fixed_plan_disturbance(request, 27);
    REQUIRE(std::holds_alternative<FixedPlanReachable>(exact));
    const auto &trace = std::get<FinitePlanParallelotopeTrace>(enclosure);
    CHECK(trace.relation == SetRelation::outer);
    const auto &stages = std::get<FixedPlanReachable>(exact).stages;
    REQUIRE(trace.frame.rows == 4);
    REQUIRE(trace.frame.cols == 4);
    REQUIRE(trace.stages.size() == stages.size());

    // Independently transform every exact finite-history vertex through the
    // integer inverse frame Q^-1 and check full 4D coordinate inclusion.
    constexpr int inverse[4][4] = {{1, -1, 1, -1}, {0, 1, -1, 1}, {0, 0, 1, -1}, {0, 0, 0, 1}};
    for (std::size_t stage = 0; stage < stages.size(); ++stage) {
        const auto repr = stages[stage].representation();
        const auto *points = std::get_if<sets::VRepresentation>(&repr);
        REQUIRE(points != nullptr);
        for (std::size_t row = 0; row < points->vertices.rows(); ++row)
            for (std::size_t i = 0; i < 4; ++i) {
                double coordinate = 0.0;
                for (std::size_t j = 0; j < 4; ++j)
                    coordinate += static_cast<double>(inverse[i][j]) * points->vertices(row, j);
                CHECK(trace.stages[stage].lower[i] <= coordinate);
                CHECK(trace.stages[stage].upper[i] >= coordinate);
            }
    }
    CHECK(trace.frame.values[1] == 1.0);
    CHECK(trace.frame.values[4] == 0.0);
    CHECK(trace.frame.values[5] == 1.0);
}

TEST_CASE("parallelotope route supports bounded two-state LV-shaped propagation") {
    auto request = planar_request();
    const auto result = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<FinitePlanParallelotopeTrace>(result));
    const auto &trace = std::get<FinitePlanParallelotopeTrace>(result);
    CHECK(trace.relation == SetRelation::outer);
    REQUIRE(trace.frame.rows == 2);
    REQUIRE(trace.frame.cols == 2);
    CHECK(trace.frame.values == Vector{1, 0, 0, 1});
    REQUIRE(trace.stages.size() == 2);
    CHECK(trace.stages[1].lower[0] <= -1.0);
    CHECK(trace.stages[1].upper[1] >= 1.0);

    request.admissible_states[1] = planar_safe("planar-too-narrow", 0.5);
    const auto outside = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<Unsupported>(outside));
    CHECK(std::get<Unsupported>(outside).diagnostics.front().field ==
          "finite_plan_parallelotope.safe_sets");
}

TEST_CASE("four-state parallelotope accepts unconstrained and containing H domains") {
    auto request = two_points_request();
    auto domain = four_state_domain("zero-row-four-state-H", {0, 4, {}}, {});
    SUBCASE("zero-row H represents the unconstrained orbit domain") {}
    SUBCASE("bounded H contains every propagated outer parallelotope") {
        domain = wide_four_state_domain();
    }
    SUBCASE("coupled H contains every propagated outer parallelotope") {
        domain = four_state_domain("wide-coupled-H", {1, 4, {1, -1, 0, 0}}, {100});
    }
    request.admissible_states.assign(request.admissible_states.size(), domain);
    const auto result = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<FinitePlanParallelotopeTrace>(result));
    const auto &trace = std::get<FinitePlanParallelotopeTrace>(result);
    CHECK(trace.relation == SetRelation::outer);
    CHECK(trace.assurance == Assurance::numerical);
    CHECK(trace.stages.size() == request.system.horizon() + 1);
}

TEST_CASE("four-state parallelotope checks initial and later H constraints") {
    auto request = two_points_request();
    request.admissible_states.assign(request.admissible_states.size(), wide_four_state_domain());
    bool initial = false;
    SUBCASE("initial coordinate bound is violated") {
        initial = true;
        request.admissible_states[0] =
            four_state_domain("tight-initial", {1, 4, {1, 0, 0, 0}}, {4});
    }
    SUBCASE("later coordinate bound is violated") {
        request.admissible_states[1] = four_state_domain("tight-later", {1, 4, {1, 0, 0, 0}}, {4});
    }
    SUBCASE("coupled H row excludes the propagated set") {
        request.admissible_states[1] =
            four_state_domain("coupled-later", {1, 4, {1, -1, 0, 0}}, {6});
    }
    SUBCASE("H equality is not satisfied by the complete outer set") {
        request.admissible_states[1] =
            four_state_domain("equality-later", {0, 4, {}}, {}, {1, 4, {1, -1, 0, 0}}, {0});
    }
    const auto result = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    const auto &diagnostic = std::get<Unsupported>(result).diagnostics.front();
    CHECK(diagnostic.field == "finite_plan_parallelotope.safe_sets");
    CHECK(
        diagnostic.explanation ==
        (initial
             ? "Initial parallelotope does not certify containment in the physical state constraint."
             : "Propagated outer parallelotope does not certify containment in the physical state constraint."));
}

TEST_CASE("four-state parallelotope refuses empty and disjoint singleton domains") {
    auto request = two_points_request();
    SUBCASE("empty domain") {
        request.admissible_states[0] = take(sets::make_empty({{"empty-safe"}, 4, {}}));
    }
    SUBCASE("disjoint singleton domain") {
        request.admissible_states[0] =
            take(sets::make_singleton({{"disjoint-singleton-safe"}, 4, {}},
                                      take(numeric::snapshot_vector(Vector{1000, 0, 0, 0}))));
    }
    const auto result = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    CHECK(std::get<Unsupported>(result).diagnostics.front().field ==
          "finite_plan_parallelotope.safe_sets");
}

TEST_CASE("four-state parallelotope retains dimension and cancellation boundaries") {
    auto request = two_points_request();
    request.admissible_states[0] = planar_safe("wrong-dimensional-safe", 100);
    const auto malformed = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<Unsupported>(malformed));
    CHECK(std::get<Unsupported>(malformed).diagnostics.front().explanation ==
          "State-constraint dimension differs from model.");

    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation = cancellation.get_token();
    const auto cancelled = finite_plan_parallelotope(request, context);
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason == StopReason::cancelled);
}

TEST_CASE("four-state parallelotope refuses unsupported V state domains") {
    auto request = two_points_request();
    auto bounded = take(sets::make_v({{"bounded-four-state-safe"}, 4, {}},
                                     {take(numeric::snapshot(Matrix{1, 4, {0.0, 0.0, 0.0, 0.0}})),
                                      take(numeric::snapshot(Matrix{0, 4, {}}))}));
    request.admissible_states[1] = std::move(bounded);

    const auto result = finite_plan_parallelotope(request);
    REQUIRE(std::holds_alternative<Unsupported>(result));
    const auto &diagnostic = std::get<Unsupported>(result).diagnostics[0];
    CHECK(diagnostic.field == "finite_plan_parallelotope.safe_sets");
    CHECK(
        diagnostic.explanation ==
        "Propagated outer parallelotope does not certify containment in the physical state constraint.");
}
