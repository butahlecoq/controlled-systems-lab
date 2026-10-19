#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/optimization/feasible_directions/smooth_convex.hpp>

#include <cmath>
#include <limits>
#include <memory>
#include <stop_token>

using namespace csl;
using namespace csl::optimization;
using namespace csl::optimization::feasible_directions;

namespace {
template<class T, class... Other> T accepted(std::variant<T, Other...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
ExecutionContext context() {
    return {std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {}, {}, {1e-9, 1e-9}, "smooth-convex-test"};
}
LinearProgram box(std::string name, std::vector<Interval> variables) {
    const auto n = variables.size();
    return accepted(make_linear_program({{{"smooth-convex"}, {std::move(name)}},
        Vector(n, 0), 0, {0, n, {0}, {}, {}}, std::move(variables), {}}));
}
std::unique_ptr<LPWorkspace> workspace(const LinearProgram& feasible) {
    auto backend = accepted(adapters::lp::make_highs_registration());
    auto result = backend.factory(feasible);
    REQUIRE(result);
    return result;
}
SmoothObjective quadratic(std::string id, Vector center, Vector weights) {
    const auto dimension = center.size();
    return {std::move(id), dimension, ObjectiveClaim::declared_convex,
        [center, weights](std::span<const double> point) {
            double sum = 0;
            for (std::size_t j = 0; j < point.size(); ++j)
                sum = std::fma(0.5 * weights[j] * (point[j] - center[j]), point[j] - center[j], sum);
            return sum;
        },
        [center, weights](std::span<const double> point) {
            Vector gradient(point.size());
            for (std::size_t j = 0; j < point.size(); ++j)
                gradient[j] = weights[j] * (point[j] - center[j]);
            return gradient;
        }};
}
Vector reference_qp(const LinearProgram& feasible, const Vector& center, const Vector& weights) {
    Matrix q{center.size(), center.size(), Vector(center.size() * center.size(), 0)};
    Vector linear(center.size());
    double offset = 0;
    for (std::size_t j = 0; j < center.size(); ++j) {
        q.values[j * q.cols + j] = weights[j];
        linear[j] = -weights[j] * center[j];
        offset += 0.5 * weights[j] * center[j] * center[j];
    }
    const auto csr = std::get<numeric::CsrInput>(feasible.constraints().descriptor());
    SparseMatrix rows{csr.rows, csr.cols, {csr.row_offsets.begin(), csr.row_offsets.end()},
        {csr.column_indices.begin(), csr.column_indices.end()}, {csr.values.begin(), csr.values.end()}};
    auto program = accepted(make_convex_program({
        {feasible.identity().problem, {feasible.identity().program.value + "/reference"}},
        QuadraticTerminal{std::move(q), std::move(linear), offset},
        std::move(rows),
        {feasible.variables().begin(), feasible.variables().end()},
        {feasible.rows().begin(), feasible.rows().end()}, {}}));
    auto backend = accepted(adapters::convex::make_highs_registration());
    auto solver = backend.factory(program);
    REQUIRE(solver);
    auto result = accepted(solver->solve(program, context()));
    REQUIRE(result.termination == Termination::completed);
    REQUIRE(result.outcome.value == MathematicalOutcome::optimal);
    REQUIRE(result.primal);
    return *result.primal;
}

TEST_CASE("the equality-face solve evaluates only feasible points") {
    auto feasible = accepted(make_linear_program({{{"smooth-convex"}, {"equality-face"}},
        Vector{0, 0}, 0, {1, 2, {0, 2}, {0, 1}, {1, 1}},
        {{0, 1}, {0, 1}}, {{1, 1}}}));
    auto solver = workspace(feasible);
    auto objective = quadratic("face-quadratic", {2, 2}, {1, 1});
    const auto ordinary_value = objective.value;
    std::size_t visited = 0;
    objective.value = [&](std::span<const double> point) {
        REQUIRE(point.size() == 2);
        CHECK(point[0] >= -1e-9);
        CHECK(point[1] >= -1e-9);
        CHECK(point[0] <= 1 + 1e-9);
        CHECK(point[1] <= 1 + 1e-9);
        CHECK(point[0] + point[1] == doctest::Approx(1).epsilon(1e-9));
        ++visited;
        return ordinary_value(point);
    };
    const auto result = accepted(minimize(feasible, objective, Vector{0.25, 0.75}, *solver, context()));
    CHECK(visited >= 2);
    CHECK(result.point[0] == doctest::Approx(0.5).epsilon(1e-7));
    CHECK(result.point[1] == doctest::Approx(0.5).epsilon(1e-7));
    const auto qp = reference_qp(feasible, {2, 2}, {1, 1});
    CHECK(result.point[0] == doctest::Approx(qp[0]).epsilon(1e-7));
    CHECK(result.point[1] == doctest::Approx(qp[1]).epsilon(1e-7));
}
}

TEST_CASE("declared smooth convex quadratics agree with literals and an independent QP") {
    struct Case { Vector center, weights, start, expected; };
    const std::vector<Case> cases{
        {{0.25}, {2}, {0.8}, {0.25}},
        {{2, -1}, {1, 4}, {0.5, 0.5}, {1, 0}},
        {{0.2, 0.7}, {2, 1}, {0.8, 0.1}, {0.2, 0.7}}
    };
    for (std::size_t i = 0; i < cases.size(); ++i) {
        const auto& fixture = cases[i];
        auto feasible = box("quadratic-" + std::to_string(i),
            std::vector<Interval>(fixture.center.size(), Interval{0, 1}));
        auto solver = workspace(feasible);
        auto objective = quadratic("quadratic", fixture.center, fixture.weights);
        const auto result = accepted(minimize(feasible, objective, fixture.start, *solver, context()));
        const auto qp = reference_qp(feasible, fixture.center, fixture.weights);
        REQUIRE(result.point.size() == fixture.expected.size());
        for (std::size_t j = 0; j < result.point.size(); ++j) {
            CHECK(result.point[j] == doctest::Approx(fixture.expected[j]).epsilon(1e-6));
            CHECK(result.point[j] == doctest::Approx(qp[j]).epsilon(1e-6));
        }
        CHECK(result.objective == doctest::Approx(objective.value(result.point)).epsilon(1e-8));
        CHECK(result.projected_gradient_residual <= 1e-7);
        CHECK(result.evidence == SmoothEvidence::declared_convex_numerical_stationarity);
    }
}

TEST_CASE("zero direction, infeasible start and unsupported declaration are distinct") {
    auto feasible = box("boundary", {{0, 1}});
    auto solver = workspace(feasible);
    auto objective = quadratic("quadratic", {0.25}, {2});
    const auto zero = accepted(minimize(feasible, objective, Vector{0.25}, *solver, context()));
    CHECK(zero.reason == StationarityReason::zero_projected_direction);
    CHECK(zero.iterations == 0);
    const auto invalid = minimize(feasible, objective, Vector{2}, *solver, context());
    REQUIRE(std::holds_alternative<Diagnostics>(invalid));
    CHECK(std::get<Diagnostics>(invalid).front().field == "feasible_directions.start");
    objective.claim = ObjectiveClaim::declared_nonconvex;
    const auto unsupported = minimize(feasible, objective, Vector{0.25}, *solver, context());
    CHECK(std::holds_alternative<Unsupported>(unsupported));
}

TEST_CASE("cancelled, exhausted and stalled runs retain the last feasible point") {
    auto feasible = box("stops", {{0, 1}});
    auto solver = workspace(feasible);
    auto objective = quadratic("quadratic", {2}, {1});
    std::stop_source source;
    source.request_stop();
    auto cancelled_context = context();
    cancelled_context.cancellation = source.get_token();
    const auto cancelled = minimize(feasible, objective, Vector{0.25},
        *solver, cancelled_context);
    REQUIRE(std::holds_alternative<SmoothStopped>(cancelled));
    CHECK(std::get<SmoothStopped>(cancelled).reason == SmoothStopReason::cancelled);
    CHECK(std::get<SmoothStopped>(cancelled).last_feasible_iterate == Vector{0.25});

    auto capped = minimize(feasible, objective, Vector{0.25}, *solver, context(), {.max_iterations = 1});
    REQUIRE(std::holds_alternative<SmoothStopped>(capped));
    CHECK(std::get<SmoothStopped>(capped).reason == SmoothStopReason::resource_limit);
    CHECK(std::get<SmoothStopped>(capped).last_feasible_iterate == Vector{1});

    SmoothObjective inconsistent{"inconsistent", 1, ObjectiveClaim::declared_convex,
        [](std::span<const double> x) { return x[0]; },
        [](std::span<const double>) { return Vector{-1}; }};
    SmoothPolicy search;
    search.max_backtracks = 4;
    search.minimum_step = 0.01;
    const auto stalled = minimize(feasible, inconsistent, Vector{0.25}, *solver, context(), search);
    REQUIRE(std::holds_alternative<SmoothStopped>(stalled));
    CHECK(std::get<SmoothStopped>(stalled).reason == SmoothStopReason::line_search_stall);
    CHECK(std::get<SmoothStopped>(stalled).last_feasible_iterate == Vector{0.25});
}

TEST_CASE("callback failures do not become numerical stationarity") {
    auto feasible = box("callbacks", {{0, 1}});
    auto solver = workspace(feasible);
    auto objective = quadratic("quadratic", {0.5}, {1});
    objective.value = [](std::span<const double>) { return std::numeric_limits<double>::quiet_NaN(); };
    const auto bad_value = minimize(feasible, objective, Vector{0.25}, *solver, context());
    REQUIRE(std::holds_alternative<SmoothStopped>(bad_value));
    CHECK(std::get<SmoothStopped>(bad_value).reason == SmoothStopReason::callback_failure);
    CHECK(std::get<SmoothStopped>(bad_value).last_feasible_iterate == Vector{0.25});
    CHECK_FALSE(std::get<SmoothStopped>(bad_value).last_objective.has_value());
    objective = quadratic("quadratic", {0.5}, {1});
    objective.gradient = [](std::span<const double>) { return Vector{}; };
    const auto bad_gradient = minimize(feasible, objective, Vector{0.25}, *solver, context());
    REQUIRE(std::holds_alternative<SmoothStopped>(bad_gradient));
    CHECK(std::get<SmoothStopped>(bad_gradient).reason == SmoothStopReason::callback_failure);
}
