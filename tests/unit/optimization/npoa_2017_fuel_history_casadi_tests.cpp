#include <doctest/doctest.h>

#include <csl/adapters/nlp/casadi_history_optimizer.hpp>
#include <csl/sets/data.hpp>

#include <array>
#include <cmath>
#include <vector>

using namespace csl;

namespace {
template <class T, class... E> T take(std::variant<T, E...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

optimization::HistoryOptimizationRequest programmed_fuel_request() {
    constexpr std::size_t state_dimension = 4;
    constexpr std::size_t control_dimension = 1;
    constexpr std::size_t horizon = 10;
    constexpr std::size_t history_dimension = (horizon + 1) * state_dimension + horizon;
    constexpr std::array<std::array<double, 4>, 4> transition{
        {{{1, 0, 0, 0}}, {{-1, 1, 0, 0}}, {{0, 0, 1, 0}}, {{0, 0, -1, 1}}}};
    const Vector input{5.0 / 12.0, 0, -1.0 / 3.0, 0};
    const Vector initial{25.14, 247, 19.915, 199.92};

    Matrix equalities{
        4 + horizon * state_dimension, history_dimension,
        std::vector<double>((4 + horizon * state_dimension) * history_dimension, 0.0)};
    const auto set_equality = [&](std::size_t row, std::size_t column, double value) {
        equalities.values[row * history_dimension + column] = value;
    };
    Vector equality_values(4 + horizon * state_dimension, 0.0);
    for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate) {
        set_equality(coordinate, coordinate, 1.0);
        equality_values[coordinate] = initial[coordinate];
    }
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        for (std::size_t row = 0; row < state_dimension; ++row) {
            const auto equality = 4 + stage * state_dimension + row;
            set_equality(equality, (stage + 1) * state_dimension + row, 1.0);
            for (std::size_t column = 0; column < state_dimension; ++column)
                set_equality(equality, stage * state_dimension + column, -transition[row][column]);
            set_equality(equality, (horizon + 1) * state_dimension + stage, -input[row]);
        }
    }

    Matrix inequalities{64, history_dimension, std::vector<double>(64 * history_dimension, 0.0)};
    Vector upper_bounds(64, 0.0);
    std::size_t inequality = 0;
    const auto add_bound = [&](std::size_t index, double coefficient, double bound,
                               std::size_t row) {
        inequalities.values[row * history_dimension + index] = coefficient;
        upper_bounds[row] = bound;
    };
    for (std::size_t stage = 0; stage <= horizon; ++stage) {
        const auto state = stage * state_dimension;
        add_bound(state, 1.0, 25.833, inequality++);
        add_bound(state, -1.0, -24.167, inequality++);
        add_bound(state + 2, 1.0, 20.66, inequality++);
        add_bound(state + 2, -1.0, -19.33, inequality++);
    }
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        const auto control = (horizon + 1) * state_dimension + stage;
        add_bound(control, 1.0, 1.0, inequality++);
        add_bound(control, -1.0, 1.0, inequality++);
    }
    REQUIRE(inequality == inequalities.rows);

    auto full_history = take(sets::make_h(
        {{"npoa-2017-programmed-fuel-full-history"}, history_dimension, {}},
        {take(numeric::snapshot(inequalities)), take(numeric::snapshot_vector(upper_bounds)),
         take(numeric::snapshot(equalities)), take(numeric::snapshot_vector(equality_values))}));
    synthesis::JointHistoryRelation relation{{{state_dimension, control_dimension, 0}, horizon},
                                             std::move(full_history)};

    // Literal expansion of (25-x1)^2+x2^2+(20-x3)^2+x4^2+(x2-x4)^2
    // under the library convention 1/2 x'Qx + q'x + c.
    QuadraticTerminal terminal{
        {4, 4, {2, 0, 0, 0, 0, 4, 0, -2, 0, 0, 2, 0, 0, -2, 0, 4}}, {-50, 0, -40, 0}, 1025.0};
    optimization::RunningControlCost no_running_cost{"", 0, {}};
    auto cost = take(optimization::compile_history_cost(relation, TerminalObjective{terminal},
                                                        no_running_cost, 0));

    Vector start(history_dimension, 0.0);
    Vector state = initial;
    for (std::size_t stage = 0; stage <= horizon; ++stage) {
        for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate)
            start[stage * state_dimension + coordinate] = state[coordinate];
        if (stage < horizon) {
            Vector next(state_dimension, 0.0);
            for (std::size_t row = 0; row < state_dimension; ++row)
                for (std::size_t column = 0; column < state_dimension; ++column)
                    next[row] += transition[row][column] * state[column];
            state = std::move(next);
        }
    }

    return {{ProblemId{"npoa-2017-programmed-fuel"}, ProgramId{"npoa-2017-terminal-quadratic"}},
            {std::move(relation), {}},
            std::move(cost),
            optimization::SuppliedStart{std::move(start), {}}};
}
}

TEST_CASE("CasADi/IPOPT solves the source-bound four-state programmed-fuel history") {
    auto request = programmed_fuel_request();
    auto registration = adapters::nlp::make_casadi_history_optimizer_registration();
    auto workspace = registration.factory(request);
    const auto outcome =
        registry::HistoryOptimizerPort::run(*workspace, request, ExecutionContext{});
    if (const auto *diagnostic = std::get_if<Diagnostic>(&outcome)) {
        INFO(diagnostic->field);
        FAIL_CHECK(diagnostic->explanation);
    }
    REQUIRE(std::holds_alternative<optimization::HistoryOptimizationResult>(outcome));
    const auto &result = std::get<optimization::HistoryOptimizationResult>(outcome);
    CHECK(result.history.size() == 54);
    CHECK(result.maximum_history_violation < 1e-7);
    CHECK(result.source_cost.total == doctest::Approx(4.649522381047).epsilon(2e-5));
    CHECK(result.reported_objective == doctest::Approx(result.source_cost.total).epsilon(1e-7));
    CHECK(result.membership_witnesses.empty());
}
