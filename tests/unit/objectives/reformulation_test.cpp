#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/objectives.hpp>
#include <array>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T accepted(Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

void check_costs(const NormSquareReformulation& record, const Vector& point,
                 double original, double squared) {
    CHECK(accepted(evaluate(record.original(), point)) == doctest::Approx(original).epsilon(1e-12));
    CHECK(accepted(evaluate(record.squared(), point)) == squared);
}
}

TEST_CASE("wide rectangular reformulation retains literal coefficients and original cost") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, 4}}))));
    const auto original = std::get<ResidualCoefficients>(record.original().coefficients());
    REQUIRE(original.map.rows() == 2);
    REQUIRE(original.map.cols() == 3);
    REQUIRE(original.target.size() == 2);
    const std::array expected_map{1., 0., 0., 0., 1., 1.};
    for (std::size_t row = 0; row < 2; ++row)
        for (std::size_t col = 0; col < 3; ++col)
            CHECK(original.map(row, col) == expected_map[row * 3 + col]);
    CHECK(original.target[0] == 1);
    CHECK(original.target[1] == 4);

    const auto squared = std::get<QuadraticCoefficients>(record.squared().coefficients());
    REQUIRE(squared.Q.rows() == 3);
    REQUIRE(squared.Q.cols() == 3);
    REQUIRE(squared.linear.size() == 3);
    const std::array expected_Q{2., 0., 0., 0., 2., 2., 0., 2., 2.};
    const std::array expected_q{-2., -8., -8.};
    for (std::size_t row = 0; row < 3; ++row) {
        CHECK(squared.linear[row] == expected_q[row]);
        for (std::size_t col = 0; col < 3; ++col)
            CHECK(squared.Q(row, col) == expected_Q[row * 3 + col]);
    }
    CHECK(squared.offset == 17);
    CHECK(record.transformation() == ObjectiveTransformation::residual_norm_squared);
    check_costs(record, {1, 1, 3}, 0, 0);
    check_costs(record, {4, 1, 7}, 5, 25);
}

// Complete analytic sets are derived in docs/contracts/objective-test-oracles.md.
// These finite witnesses check evaluation; the API is not enumerating minimizers.
TEST_CASE("zero minimum on the bounded segment retains endpoints and interior") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, 4}}))));
    // Box [0,2] x [0,4] x [0,4]; minimizers [1,t,4-t], 0 <= t <= 4.
    check_costs(record, {1, 0, 4}, 0, 0);
    check_costs(record, {1, 2, 2}, 0, 0);
    check_costs(record, {1, 4, 0}, 0, 0);
    check_costs(record, {0, 0, 4}, 1, 1);
    check_costs(record, {1, 1, 2}, 1, 1);
}

TEST_CASE("nonzero bounded minimum preserves the segment but changes cost units") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {3, 4}}))));
    // Box [0,1] x [0,4] x [0,4]; same segment, minima 2 and 4.
    check_costs(record, {1, 0, 4}, 2, 4);
    check_costs(record, {1, 2, 2}, 2, 4);
    check_costs(record, {1, 4, 0}, 2, 4);
    check_costs(record, {0, 0, 4}, 3, 9);
}

TEST_CASE("rank-one residual retains a bounded two-parameter zero-cost family") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{2, 3, {1, 1, 0, 2, 2, 0}}, {1, 2}}))));
    // Box [0,1]^3; minimizers [t,1-t,s], 0 <= t,s <= 1.
    check_costs(record, {0, 1, 0}, 0, 0);
    check_costs(record, {1, 0, 1}, 0, 0);
    check_costs(record, {0.5, 0.5, 0.25}, 0, 0);
    check_costs(record, {0, 0, 0}, 2.23606797749979, 5);
}

TEST_CASE("constant residual preserves every point of an analytic bounded box") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{2, 2, {0, 0, 0, 0}}, {3, 4}}))));
    // Every point of [-1,1]^2 minimizes these constant criteria.
    check_costs(record, {-1, -1}, 5, 25);
    check_costs(record, {1, 1}, 5, 25);
    check_costs(record, {0, 0}, 5, 25);
}

TEST_CASE("tall weighted residual provenance retains targets policy and quadratic convention") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{3, 2, {2, 0, 0, 3, 0, 0}}, {2, 6, 4}},
        {Assurance::numerical, {0.03125, 0.015625}}))));
    const auto original = std::get<ResidualCoefficients>(record.original().coefficients());
    REQUIRE(original.map.rows() == 3);
    REQUIRE(original.map.cols() == 2);
    REQUIRE(original.target.size() == 3);
    const std::array expected_map{2., 0., 0., 3., 0., 0.};
    const std::array expected_target{2., 6., 4.};
    for (std::size_t row = 0; row < 3; ++row) {
        CHECK(original.target[row] == expected_target[row]);
        for (std::size_t col = 0; col < 2; ++col)
            CHECK(original.map(row, col) == expected_map[row * 2 + col]);
    }
    const auto squared = std::get<QuadraticCoefficients>(record.squared().coefficients());
    REQUIRE(squared.Q.rows() == 2);
    REQUIRE(squared.Q.cols() == 2);
    REQUIRE(squared.linear.size() == 2);
    CHECK(squared.Q(0, 0) == 8);
    CHECK(squared.Q(0, 1) == 0);
    CHECK(squared.Q(1, 0) == 0);
    CHECK(squared.Q(1, 1) == 18);
    CHECK(squared.linear[0] == -8);
    CHECK(squared.linear[1] == -36);
    CHECK(squared.offset == 56);
    CHECK(record.transformation() == ObjectiveTransformation::residual_norm_squared);
    for (const auto& objective : {record.original(), record.squared()}) {
        CHECK(objective.policy().assurance == Assurance::numerical);
        CHECK(objective.policy().numerical.absolute_tolerance == 0.03125);
        CHECK(objective.policy().numerical.relative_tolerance == 0.015625);
    }
    check_costs(record, {1, 2}, 4, 16);
    check_costs(record, {0, 0}, 7.483314773547883, 56);
}

TEST_CASE("squaring only the norm in a mixed objective changes its minimizer") {
    const auto record = accepted(square_residual_norm(accepted(snapshot(ResidualNormTerminal{{1, 1, {1}}, {1}}))));
    const auto linear = accepted(snapshot(LinearTerminal{{0.5}, 0}));
    // On [0,2], |x-1|+x/2 minimizes at 1; (x-1)^2+x/2 minimizes at 0.75.
    // The sums below are test expressions, not a supported sum-objective API.
    CHECK(accepted(evaluate(record.original(), Vector{1})) + accepted(evaluate(linear, Vector{1})) == 0.5);
    CHECK(accepted(evaluate(record.original(), Vector{0.75})) + accepted(evaluate(linear, Vector{0.75})) == 0.625);
    CHECK(accepted(evaluate(record.squared(), Vector{1})) + accepted(evaluate(linear, Vector{1})) == 0.5);
    CHECK(accepted(evaluate(record.squared(), Vector{0.75})) + accepted(evaluate(linear, Vector{0.75})) == 0.4375);
}

TEST_CASE("norm squaring explicitly declines both nonresidual objective forms") {
    for (const auto& authored : std::vector<TerminalObjective>{
             LinearTerminal{{0.5}, 0}, QuadraticTerminal{{1, 1, {2}}, {-2}, 1}}) {
        const auto result = square_residual_norm(accepted(snapshot(authored)));
        REQUIRE(std::holds_alternative<Diagnostic>(result));
        CHECK(std::get<Diagnostic>(result).code == DiagnosticCode::unsupported);
        CHECK(std::get<Diagnostic>(result).field == "objective.reformulation");
    }
}
