#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <cmath>
#include <limits>

#include "synthesis/exact_h_enclosure.hpp"

using namespace csl::synthesis::detail::exact_rational;

namespace {
bool same(const Rational& lhs, const Rational& rhs, Budget& budget) {
    bool result{};
    return equal(lhs, rhs, result, budget) && result;
}
}

TEST_CASE("rational arithmetic preserves odd denominators and dyadic exponents") {
    Budget budget;
    Rational one_third, two_thirds, one, sum;
    REQUIRE(make_fraction(1, 3, one_third, budget));
    REQUIRE(make_fraction(2, 3, two_thirds, budget));
    REQUIRE(make_integer(1, one, budget));
    REQUIRE(add(one_third, two_thirds, sum, budget));
    CHECK(same(sum, one, budget));

    Rational half, five_sixths, mixed;
    REQUIRE(from_binary64(0.5, half, budget));
    REQUIRE(make_fraction(5, 6, five_sixths, budget));
    REQUIRE(add(one_third, half, mixed, budget));
    CHECK(same(mixed, five_sixths, budget));
    int order{};
    REQUIRE(compare(one_third, half, order, budget));
    CHECK(order < 0);

    Rational accumulated = one_third;
    REQUIRE(add(accumulated, half, accumulated, budget));
    CHECK(same(accumulated, five_sixths, budget));
}

TEST_CASE("rational construction canonicalizes signs and powers of two") {
    Budget budget;
    Rational negative, expected, dyadic, expected_dyadic, unreduced, one_third;
    REQUIRE(make_fraction(2, -3, negative, budget));
    REQUIRE(make_fraction(-2, 3, expected, budget));
    CHECK(same(negative, expected, budget));
    REQUIRE(from_binary64(0.125, dyadic, budget));
    REQUIRE(make_fraction(1, 8, expected_dyadic, budget));
    CHECK(same(dyadic, expected_dyadic, budget));
    CHECK_FALSE(dyadic.denominator.negative);
    REQUIRE(make_fraction(1001, 3003, unreduced, budget));
    REQUIRE(make_fraction(1, 3, one_third, budget));
    CHECK(unreduced == one_third);
}

TEST_CASE("adding wide dyadics uses only the arithmetic operation budget") {
    using exact_h::exact_detail::from_u64;
    Rational large{from_u64(1), from_u64(1), 2048};
    Rational one{from_u64(1), from_u64(1), 0};
    Rational result;
    Budget one_addition;
    one_addition.max_operations = 1;
    REQUIRE(add(large, one, result, one_addition));
    CHECK(result.binary_exponent == 0);
    CHECK(result.denominator == from_u64(1));
    REQUIRE(result.numerator.words.size() == 65);
    CHECK(result.numerator.words.front() == 1);
    CHECK(result.numerator.words.back() == 1);
    CHECK(one_addition.operations == 1);
}

TEST_CASE("rational arithmetic refuses bit and operation budget exhaustion") {
    Budget bit_budget{.max_integer_bits = 4, .max_operations = 16};
    Rational fifteen, sum;
    REQUIRE(make_integer(15, fifteen, bit_budget));
    CHECK_FALSE(add(fifteen, fifteen, sum, bit_budget));

    Budget operation_budget{.max_integer_bits = 64, .max_operations = 1};
    Rational one, result;
    REQUIRE(make_integer(1, one, operation_budget));
    CHECK_FALSE(multiply(one, one, result, operation_budget));
}

TEST_CASE("rational conversion rejects nonfinite binary64 inputs") {
    Budget budget;
    Rational value;
    CHECK_FALSE(from_binary64(std::numeric_limits<double>::infinity(), value, budget));
}

TEST_CASE("rational parser handles large exact witnesses and rejects malformed input") {
    Budget budget;
    Rational parsed, expected;
    REQUIRE(parse("-22372732538527557968995655584885504649887873368947295001505132908576311772305610948689388831835602767915142538822180404220637/65742268634831342597332464158599530180018681724968804273528997972883832204336594969293002728400911316448736602407117160185856",
        parsed, budget));
    CHECK(parsed.numerator.negative);
    CHECK_FALSE(parse("1//2", expected, budget));
    CHECK_FALSE(parse("1/0", expected, budget));
    CHECK_FALSE(parse("1/-3", expected, budget));
}

TEST_CASE("binary64 enclosure is directed for exact and fractional bounds") {
    using exact_h::Binary64BracketStatus;
    using exact_h::ExactRational;
    const auto one = exact_h::exact_detail::from_u64(1);
    const auto three = exact_h::exact_detail::from_u64(3);
    const double infinity = std::numeric_limits<double>::infinity();

    ExactRational value{one, three, 0};
    const auto positive = exact_h::bracket_binary64(value, 8192);
    REQUIRE(positive.status == Binary64BracketStatus::finite);
    CHECK(positive.lower == 1.0 / 3.0);
    CHECK(positive.upper == std::nextafter(positive.lower, infinity));
    double out{};
    CHECK_FALSE(exact_h::exact_rational_to_double(value, 8192, out));

    value.numerator.negative = true;
    const auto negative = exact_h::bracket_binary64(value, 8192);
    REQUIRE(negative.status == Binary64BracketStatus::finite);
    CHECK(negative.lower == -positive.upper);
    CHECK(negative.upper == -positive.lower);

    REQUIRE(exact_h::exact_rational_to_double(ExactRational{one, one, -3}, 8192, out));
    CHECK(out == 0.125);
    const auto underflow = exact_h::bracket_binary64(ExactRational{one, one, -1075}, 8192);
    REQUIRE(underflow.status == Binary64BracketStatus::finite);
    CHECK(underflow.lower == 0.0);
    CHECK(underflow.upper == std::numeric_limits<double>::denorm_min());

    CHECK(exact_h::bracket_binary64(ExactRational{one, one, 1024}, 8192).status ==
          Binary64BracketStatus::outside_finite_range);
    CHECK(exact_h::bracket_binary64(ExactRational{one, three, 0}, 1).status ==
          Binary64BracketStatus::arithmetic_budget);
}

TEST_CASE("binary64 enclosure validates the denominator for zero") {
    using exact_h::Binary64BracketStatus;
    using exact_h::ExactRational;
    const auto one = exact_h::exact_detail::from_u64(1);
    const auto zero = exact_h::bracket_binary64(ExactRational{{}, one, 0}, 8192);
    REQUIRE(zero.status == Binary64BracketStatus::finite);
    CHECK(zero.lower == 0.0);
    CHECK(zero.upper == 0.0);

    auto negative_denominator = one;
    negative_denominator.negative = true;

    CHECK(exact_h::bracket_binary64(ExactRational{{}, {}, 0}, 8192).status ==
          Binary64BracketStatus::invalid);
    CHECK(exact_h::bracket_binary64(ExactRational{{}, negative_denominator, 0}, 8192).status ==
          Binary64BracketStatus::invalid);
}

TEST_CASE("exact projection can substitute a signed equality before generating inequality pairs") {
    using exact_h::FeasibilityState;
    using exact_h::InclusionState;
    exact_h::Limits limits;
    limits.max_rows = 3;
    const double upper[] = {0, 1};
    const double lower[] = {0, -1};
    const double mapping[] = {-1, -2};
    const double positive[] = {1};
    const double negative[] = {-1};

    std::vector<exact_h::Row> bounds, equalities, projected, expected;
    REQUIRE(exact_h::append_inequality(upper, 1, true, limits.max_integer_bits, bounds));
    REQUIRE(exact_h::append_inequality(lower, 0, false, limits.max_integer_bits, bounds));
    auto opposing_rows = bounds;
    REQUIRE(exact_h::append_equality(mapping, 0, limits.max_integer_bits, opposing_rows));
    CHECK(exact_h::feasible(std::move(opposing_rows), 2, limits).state ==
          FeasibilityState::unsupported);

    exact_h::Row equation;
    REQUIRE(exact_h::make_row(mapping, 0, false, limits.max_integer_bits, equation));
    equalities.push_back(equation);
    REQUIRE(exact_h::append_inequality(positive, 0, false, limits.max_integer_bits, expected));
    REQUIRE(exact_h::append_inequality(negative, 2, true, limits.max_integer_bits, expected));

    const auto result = exact_h::feasible(bounds, 2, limits, std::stop_token{}, 1,
                                          &projected, equalities);
    REQUIRE(result.state == FeasibilityState::feasible);
    CHECK(result.generated_rows == 0);
    CHECK(exact_h::included_in(projected, expected, 1).state == InclusionState::included);
    CHECK(exact_h::included_in(expected, projected, 1).state == InclusionState::included);

    limits.max_operations = 1;
    CHECK(exact_h::feasible(bounds, 2, limits, std::stop_token{}, 1,
                            &projected, equalities).state == FeasibilityState::unsupported);
    CHECK(projected.empty());
}

TEST_CASE("contradictory eliminated equalities are infeasible") {
    const double coefficients[] = {0, 1};
    std::vector<exact_h::Row> equalities(2), projected;
    REQUIRE(exact_h::make_row(coefficients, 1, false, 8192, equalities[0]));
    REQUIRE(exact_h::make_row(coefficients, 2, false, 8192, equalities[1]));

    using exact_h::FeasibilityState;
    CHECK(exact_h::feasible({}, 2, {}, std::stop_token{}, 1,
                            &projected, equalities).state == FeasibilityState::infeasible);
    CHECK(projected.empty());

    std::stop_source source;
    source.request_stop();
    CHECK(exact_h::feasible({}, 2, {}, source.get_token(), 1,
                            &projected, equalities).state == FeasibilityState::cancelled);
}

TEST_CASE("rounded H rows cover the exact boundary despite losing normal bits") {
    using namespace csl::synthesis::detail::exact_h_enclosure;
    Budget budget;
    Rational minus_one, zero;
    REQUIRE(make_integer(-1, minus_one, budget));
    REQUIRE(make_integer(0, zero, budget));
    const Interval box[] = {{minus_one, zero}};
    const exact_h::Row row{{exact_h::exact_detail::from_u64((std::uint64_t{1} << 54) + 1)},
                            exact_h::exact_detail::from_u64((std::uint64_t{1} << 54) + 1, true)};
    const auto rounded = enclose_upper_row(row, box, budget);
    REQUIRE(rounded);
    CHECK(rounded->coefficients == std::vector<double>{0.5});
    CHECK(rounded->bound == -0.5);

    const Interval reversed[] = {{zero, minus_one}};
    CHECK_FALSE(enclose_upper_row(row, reversed, budget));
    Budget exhausted;
    exhausted.max_operations = 0;
    CHECK_FALSE(enclose_upper_row(row, box, exhausted));
}

TEST_CASE("negative affine coefficients exchange interval endpoints") {
    using namespace csl::synthesis::detail::exact_h_enclosure;
    Budget budget;
    Rational one, two, three, minus_five, minus_three;
    REQUIRE(make_integer(1, one, budget));
    REQUIRE(make_integer(2, two, budget));
    REQUIRE(make_integer(3, three, budget));
    REQUIRE(make_integer(-5, minus_five, budget));
    REQUIRE(make_integer(-3, minus_three, budget));
    Interval total{one, one};
    REQUIRE(accumulate_scaled_interval(total, -2, Interval{two, three}, budget));
    CHECK(same(total.lower, minus_five, budget));
    CHECK(same(total.upper, minus_three, budget));
}
