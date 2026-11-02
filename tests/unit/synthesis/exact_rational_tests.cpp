#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <limits>

#include "synthesis/exact_rational.hpp"

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
