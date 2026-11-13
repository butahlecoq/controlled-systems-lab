#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/nominal_quadratic_history.hpp>

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
            {{2, 2, {0.0, 0.0, 0.0, 0.0}}, {0.0, 0.0}, 0.0}};
}

ConvexProgram accepted(ConvexDataResult<ConvexProgram> result) {
    REQUIRE(std::holds_alternative<ConvexProgram>(result));
    return std::get<ConvexProgram>(std::move(result));
}
}

TEST_CASE("history compiler preserves stage blocks, cross terms and source polynomial") {
    const auto program = accepted(compile_nominal_quadratic_history(task()));
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
