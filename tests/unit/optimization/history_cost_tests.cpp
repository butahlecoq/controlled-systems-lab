#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/optimization/history_cost.hpp>
#include <csl/sets/data.hpp>

#include <cmath>
#include <limits>

using namespace csl;

namespace {

synthesis::JointHistoryRelation relation(std::size_t horizon, std::size_t state, std::size_t control) {
    auto set = sets::make_universal({{"feasible-full-history"},
        state * (horizon + 1) + control * horizon, {}});
    return {{Dimensions{state, control, 0}, horizon}, std::get<sets::SetData>(std::move(set))};
}

double polynomial_value(const optimization::HistoryQuadraticPolynomial& polynomial,
        std::span<const double> point) {
    double value = polynomial.offset;
    for(std::size_t i = 0; i < point.size(); ++i) {
        value += polynomial.linear[i] * point[i];
        for(std::size_t j = 0; j < point.size(); ++j)
            value += 0.5 * point[i] * polynomial.Q.values[i * point.size() + j] * point[j];
    }
    return value;
}

double residual_value(const optimization::WeightedHistoryResidualNorm& term,
        std::span<const double> point) {
    double norm = 0.0;
    for(std::size_t row = 0; row < term.map.rows; ++row) {
        double residual = -term.target[row];
        for(std::size_t column = 0; column < point.size(); ++column)
            residual += term.map.values[row * term.map.cols + column] * point[column];
        norm = std::hypot(norm, std::sqrt(term.weights[row]) * residual);
    }
    return term.coefficient * norm;
}

} // namespace

TEST_CASE("history cost compiles the original terminal and absolute-stage quadratic source formulas") {
    const auto history = relation(2, 1, 2);
    const TerminalObjective terminal = QuadraticTerminal{
        {1, 1, {2.0}}, {-4.0}, 4.0};
    const optimization::RunningControlCost running{"source-quadratic", 4, {
        {1, {optimization::QuadraticControlPenalty{{0.0, 0.0}, {1.0, 1.0},
            {1.0, 1.0}, 100.0, 4}}},
        {2, {optimization::QuadraticControlPenalty{{0.5, -1.0}, {2.0, 0.5},
            {3.0, 0.25}, 4.0, 4}}},
        {3, {optimization::EuclideanControlPenalty{{1, 2, {1.0, 2.0}}, {3.0}, 0.5}}}
    }};

    const auto compiled = optimization::compile_history_cost(history, terminal, running, 2);
    REQUIRE(std::holds_alternative<optimization::HistoryCostProgram>(compiled));
    const auto& program = std::get<optimization::HistoryCostProgram>(compiled);
    CHECK(program.coordinates == history.coordinates);
    REQUIRE(program.residual_norms.size() == 1);

    const std::vector<Vector> states{{0.0}, {1.0}, {1.25}};
    const std::vector<Vector> controls{{0.3, -0.25}, {1.0, 0.5}};
    const auto evaluated = optimization::evaluate_history_cost(program, states, controls);
    REQUIRE(std::holds_alternative<optimization::HistoryCostEvaluation>(evaluated));
    const auto result = std::get<optimization::HistoryCostEvaluation>(evaluated);
    CHECK(result.terminal == doctest::Approx(0.5625));
    CHECK(result.running == doctest::Approx(3.0925));
    CHECK(result.total == doctest::Approx(3.655));

    const Vector canonical{0.0, 1.0, 1.25, 0.3, -0.25, 1.0, 0.5};
    CHECK(polynomial_value(program.quadratic, canonical) + residual_value(program.residual_norms[0], canonical)
        == doctest::Approx(result.total));
}

TEST_CASE("history cost keeps orbit-like residual norms as separate source terms") {
    const auto history = relation(2, 1, 2);
    const TerminalObjective terminal = ResidualNormTerminal{
        {1, 1, {1.0}}, {0.0}, {1.0}};
    const optimization::RunningControlCost running{"sum-of-norms", 2, {
        {0, {optimization::EuclideanControlPenalty{{1, 2, {1.0, 0.0}}, {-1.0}, 1.0}}},
        {1, {optimization::EuclideanControlPenalty{{1, 2, {0.0, 1.0}}, {2.0}, 2.0}}}
    }};
    const auto compiled = optimization::compile_history_cost(history, terminal, running, 0);
    REQUIRE(std::holds_alternative<optimization::HistoryCostProgram>(compiled));
    const auto& program = std::get<optimization::HistoryCostProgram>(compiled);
    REQUIRE(program.residual_norms.size() == 3);
    CHECK(program.residual_norms[0].coefficient == doctest::Approx(1.0));
    CHECK(program.residual_norms[1].coefficient == doctest::Approx(1.0));
    CHECK(program.residual_norms[2].coefficient == doctest::Approx(2.0));

    const auto evaluated = optimization::evaluate_history_cost(program,
        std::vector<Vector>{{0.0}, {0.0}, {3.0}}, std::vector<Vector>{{-1.0, 0.0}, {0.0, -1.0}});
    REQUIRE(std::holds_alternative<optimization::HistoryCostEvaluation>(evaluated));
    const auto result = std::get<optimization::HistoryCostEvaluation>(evaluated);
    CHECK(result.terminal == doctest::Approx(3.0));
    CHECK(result.running == doctest::Approx(4.0));
    CHECK(result.total == doctest::Approx(7.0));
    CHECK(result.total != doctest::Approx(std::sqrt(3.0 * 3.0 + 2.0 * 2.0 + 2.0 * 2.0)));
    CHECK(result.total != doctest::Approx(3.0 * 3.0 + 2.0 * 2.0 + 2.0 * 2.0));
}

TEST_CASE("history cost rejects shape, schedule, and nonfinite source data") {
    const auto history = relation(2, 1, 1);
    const TerminalObjective terminal = LinearTerminal{{1.0}, 0.0};
    const optimization::RunningControlCost duplicate{"bad", 4, {{2, {}}, {2, {}}}};
    CHECK(std::holds_alternative<Diagnostics>(optimization::compile_history_cost(history, terminal, duplicate, 1)));

    const optimization::RunningControlCost unsorted{"bad", 4, {{2, {}}, {1, {}}}};
    CHECK(std::holds_alternative<Diagnostics>(optimization::compile_history_cost(history, terminal, unsorted, 1)));

    const optimization::RunningControlCost out_of_range{"bad", 4, {{4, {}}}};
    CHECK(std::holds_alternative<Diagnostics>(optimization::compile_history_cost(history, terminal, out_of_range, 1)));

    const optimization::RunningControlCost nonfinite{"bad", 4, {{1,
        {optimization::QuadraticControlPenalty{{0.0}, {1.0}, {1.0},
            std::numeric_limits<double>::infinity(), 4}}}}};
    CHECK(std::holds_alternative<Diagnostics>(optimization::compile_history_cost(history, terminal, nonfinite, 1)));

    auto wrong_dimension = history;
    wrong_dimension.coordinates.dimensions.control = 2;
    CHECK(std::holds_alternative<Diagnostics>(optimization::compile_history_cost(wrong_dimension, terminal, {}, 0)));
}
