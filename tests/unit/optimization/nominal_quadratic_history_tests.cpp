#include <doctest/doctest.h>
#include <csl/optimization/nominal_quadratic_history.hpp>
#include <csl/optimization/objectives.hpp>

#include <limits>

using namespace csl;
using namespace csl::optimization;

namespace {
NominalQuadraticHistoryTask task() {
    const Matrix b{2, 1, {1.0, 0.0}}, e{2, 0, {}};
    const auto transition = [&](double scale, Vector offset) {
        return LinearStage{Matrix{2, 2, {scale, 0.0, 0.0, scale}}, b, e, std::move(offset)};
    };
    const Matrix zero_state{2, 2, {0.0, 0.0, 0.0, 0.0}};
    const Matrix zero_cross{2, 1, {0.0, 0.0}};
    QuadraticHistoryStageCost no_state{zero_state, zero_cross, {1, 1, {0.4}},
                                       {0.0, 0.0}, {0.0},      0.0};
    QuadraticHistoryStageCost tracking{
        {2, 2, {2.0, 0.0, 0.0, 0.0}}, {2, 1, {0.25, 0.0}}, {1, 1, {0.4}}, {-2.0, 0.0}, {0.0}, 1.0};
    return {{{"history-test"}, {"stage-varying"}},
            {transition(1.0, {0.5, 0.0}), transition(2.0, {-0.25, 0.0})},
            KnownInitial{{0.4, -0.2}},
            {},
            {{{-2.0, 2.0}}, {{-2.0, 2.0}}},
            TemporalConstraints{{1, 8, {0, 2}, {6, 7}, {-1.0, 1.0}}, {{-0.8, -0.8}}},
            {no_state, tracking},
            {{2, 2, {0.0, 0.0, 0.0, 0.0}}, {0.0, 0.0}, 0.0},
            {}};
}

CompiledNominalQuadraticHistory accepted(ConvexDataResult<CompiledNominalQuadraticHistory> result) {
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(result));
    return std::get<CompiledNominalQuadraticHistory>(std::move(result));
}
}

TEST_CASE("history task aggregates default to no positive-part budgets") {
    NominalQuadraticHistoryTask no_budgets{{{"history-test"}, {"default-empty-budget-field"}},
                                           {},
                                           KnownInitial{{0.0}},
                                           {},
                                           {},
                                           std::nullopt,
                                           {},
                                           {Matrix{1, 1, {0.0}}, {0.0}, 0.0}};
    CHECK(no_budgets.control_positive_part_budgets.empty());
}

TEST_CASE("history compiler preserves stage blocks, cross terms and source polynomial") {
    const auto compiled = accepted(compile_nominal_quadratic_history(task()));
    const auto &program = compiled.program;
    CHECK(compiled.layout.state_variable_count == 6);
    CHECK(compiled.layout.control_variable_count == 2);
    CHECK(compiled.layout.base_variable_count == 8);
    CHECK(compiled.layout.total_variable_count == 8);
    CHECK(compiled.layout.accepts_primal_size(8));
    CHECK(compiled.layout.state_index(2, 1) == 5);
    CHECK(compiled.layout.control_index(1, 0) == 7);
    const auto &qp = program.quadratic_program();
    REQUIRE(qp.hessian().rows() == 8);
    CHECK(qp.hessian()(2, 2) == doctest::Approx(2.0));
    CHECK(qp.hessian()(2, 7) == doctest::Approx(0.25));
    CHECK(qp.hessian()(7, 2) == doctest::Approx(0.25));
    CHECK(qp.hessian()(6, 6) == doctest::Approx(0.4));
    CHECK(qp.hessian()(7, 7) == doctest::Approx(0.4));
    CHECK(qp.hessian()(4, 4) == 0.0);    // terminal state cost is separate
    CHECK(qp.constraints().rows() == 9); // initial, transitions, stage bounds, temporal slew
    CHECK(qp.rows()[2].lower == doctest::Approx(0.5));
    CHECK(qp.rows()[4].lower == doctest::Approx(-0.25));
    CHECK(qp.rows()[8].lower == doctest::Approx(-0.8)); // u[1] - u[0]
    const auto objective =
        evaluate_primal(program, Vector{0.4, -0.2, 1.2, -0.2, 1.65, -0.4, 0.3, -0.5},
                        {1e-10, 1e-10}, {{"history-test-literal"}, "1"});
    REQUIRE(std::holds_alternative<ConvexPrimalEvaluation>(objective));
    CHECK(std::get<ConvexPrimalEvaluation>(objective).original_objective ==
          doctest::Approx(-0.042));
}

TEST_CASE("history compiler rejects malformed stage data and external channels") {
    auto malformed = task();
    malformed.running_costs.pop_back();
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.dynamics[0].E = {2, 1, {0.0, 0.0}};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.running_costs[0].offset = std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.dynamics[0].B.cols = std::numeric_limits<std::size_t>::max();
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.temporal->joint_map.column_indices[1] = 6;
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.state_bounds = {{{2.0, 1.0}}};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
}

TEST_CASE(
    "history compiler passes asymmetric and nonconvex Hessian rejection to native validation") {
    auto malformed = task();
    malformed.running_costs[1].state_hessian.values = {2.0, 1.0, 0.0, 0.0};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));

    malformed = task();
    malformed.running_costs[1].state_hessian.values = {2.0, 3.0, 3.0, 2.0};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
}

TEST_CASE("positive-part budgets use private epigraph columns after the canonical history") {
    const Matrix a{1, 1, {1.0}}, b{1, 3, {0.0, 0.0, 0.0}}, e{1, 0, {}};
    const Matrix zero_state{1, 1, {0.0}}, zero_cross{1, 3, {0.0, 0.0, 0.0}};
    const Matrix zero_control{3, 3, Vector(9, 0.0)};
    const QuadraticHistoryStageCost cost{zero_state, zero_cross,     zero_control,
                                         {0.0},      Vector(3, 0.0), 0.0};
    NominalQuadraticHistoryTask positive_part{{{"positive-part-test"}, {"exact-epigraph"}},
                                              {{a, b, e, {0.0}}},
                                              KnownInitial{{0.0}},
                                              {},
                                              {},
                                              std::nullopt,
                                              {cost},
                                              {zero_state, {0.0}, 0.0},
                                              {{{{2, 0, 1}, 1.0}}}};

    const auto compiled = accepted(compile_nominal_quadratic_history(positive_part));
    const auto &layout = compiled.layout;
    const auto &qp = compiled.program.quadratic_program();
    CHECK(layout.state_variable_count == 2);
    CHECK(layout.control_variable_count == 3);
    CHECK(layout.base_variable_count == 5);
    CHECK(layout.auxiliary_variable_count == 3);
    CHECK(layout.total_variable_count == 8);
    CHECK(layout.accepts_primal_size(8));
    CHECK_FALSE(layout.accepts_primal_size(5));
    REQUIRE(layout.auxiliary_blocks.size() == 1);
    CHECK(layout.auxiliary_blocks[0].stage == 0);
    CHECK(layout.auxiliary_blocks[0].budget_index == 0);
    CHECK(layout.auxiliary_blocks[0].first_variable == 5);
    CHECK((layout.auxiliary_blocks[0].control_indices == std::vector<std::size_t>{2, 0, 1}));
    CHECK(layout.state_index(1, 0) == 1);
    CHECK(layout.control_index(0, 0) == 2);
    CHECK(layout.control_index(1, 0) == std::nullopt);
    REQUIRE(qp.hessian().rows() == 8);
    const auto objective_coefficients = qp.objective().coefficients();
    REQUIRE(std::holds_alternative<QuadraticCoefficients>(objective_coefficients));
    const auto &objective_linear = std::get<QuadraticCoefficients>(objective_coefficients).linear;
    for (std::size_t auxiliary = 5; auxiliary < 8; ++auxiliary) {
        CHECK(qp.hessian()(auxiliary, auxiliary) == 0.0);
        CHECK(objective_linear[auxiliary] == 0.0);
        CHECK(qp.variables()[auxiliary].lower == 0.0);
    }
    REQUIRE(qp.constraints().rows() == 6); // x0, dynamics, 3 epigraph rows, budget
    const std::vector<std::size_t> source_controls{4, 2, 3};
    for (std::size_t term = 0; term < source_controls.size(); ++term) {
        const auto row = term + 2;
        CHECK(qp.constraints()(row, source_controls[term]) == 1.0);
        CHECK(qp.constraints()(row, 5 + term) == -1.0);
        CHECK(qp.rows()[row].upper == 0.0);
    }
    const auto budget_row = 5;
    CHECK(qp.constraints()(budget_row, 5) == 1.0);
    CHECK(qp.constraints()(budget_row, 6) == 1.0);
    CHECK(qp.constraints()(budget_row, 7) == 1.0);
    CHECK(qp.rows()[budget_row].upper == 1.0);
}

TEST_CASE("positive-part budget input rejects malformed stage lists and coordinates") {
    const auto original = [] {
        const Matrix a{1, 1, {1.0}}, b{1, 2, {0.0, 0.0}}, e{1, 0, {}};
        const Matrix zero_state{1, 1, {0.0}}, zero_cross{1, 2, {0.0, 0.0}};
        const Matrix zero_control{2, 2, Vector(4, 0.0)};
        const QuadraticHistoryStageCost cost{zero_state, zero_cross, zero_control,
                                             {0.0},      {0.0, 0.0}, 0.0};
        return NominalQuadraticHistoryTask{{{"positive-part-invalid"}, {"invalid-input"}},
                                           {{a, b, e, {0.0}}},
                                           KnownInitial{{0.0}},
                                           {},
                                           {},
                                           std::nullopt,
                                           {cost},
                                           {zero_state, {0.0}, 0.0},
                                           {{{{0, 1}, 1.0}}}};
    };
    auto malformed = original();
    malformed.control_positive_part_budgets.clear();
    malformed.control_positive_part_budgets.resize(2);
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
    malformed = original();
    malformed.control_positive_part_budgets[0][0].control_indices.clear();
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
    malformed = original();
    malformed.control_positive_part_budgets[0][0].upper_bound = -0.01;
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
    malformed = original();
    malformed.control_positive_part_budgets[0][0].upper_bound =
        std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
    malformed = original();
    malformed.control_positive_part_budgets[0][0].control_indices = {0, 0};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
    malformed = original();
    malformed.control_positive_part_budgets[0][0].control_indices = {
        std::numeric_limits<std::size_t>::max()};
    CHECK(std::holds_alternative<Diagnostics>(compile_nominal_quadratic_history(malformed)));
}
