#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include "optimization/detail/outward_interval.hpp"

using namespace csl::optimization::detail;

TEST_CASE("exact endpoint operations retain singleton values") {
    CHECK(add({0.0, 0.0}, {0.0, 0.0}).lower == 0.0);
    CHECK(add({1.0, 1.0}, {-1.0, -1.0}).lower == 0.0);
    CHECK(add({-0.0, -0.0}, {-0.0, -0.0}).lower == 0.0);
    CHECK(add({std::numeric_limits<double>::denorm_min(),
        std::numeric_limits<double>::denorm_min()}, {0.0, 0.0}).lower ==
        std::numeric_limits<double>::denorm_min());
    CHECK(multiply({0.0, 0.0}, {7.0, 7.0}).lower == 0.0);
    CHECK(multiply({-1.0, -1.0}, {3.0, 3.0}).lower == -3.0);
    CHECK(square({0.0, 0.0}).lower == 0.0);
    CHECK(square({0.0, 0.0}).upper == 0.0);
    CHECK(square({1.0, 1.0}).lower == 1.0);
    CHECK(square({1.0, 1.0}).upper == 1.0);
}

TEST_CASE("cancellation is exact while nonzero subnormal residuals stay outward") {
    const auto cancelled = add({1.0, 1.0}, {-1.0, -1.0});
    CHECK(cancelled.lower == 0.0);
    CHECK(cancelled.upper == 0.0);
    const auto exact_subnormal = add({std::numeric_limits<double>::denorm_min(),
        std::numeric_limits<double>::denorm_min()},
        {std::numeric_limits<double>::denorm_min(),
        std::numeric_limits<double>::denorm_min()});
    CHECK(exact_subnormal.lower == 2 * std::numeric_limits<double>::denorm_min());
    CHECK(exact_subnormal.upper == 2 * std::numeric_limits<double>::denorm_min());
}

TEST_CASE("inexact endpoints widen outwards") {
    const auto sum = add({0.1, 0.1}, {0.2, 0.2});
    CHECK(sum.lower < 0.1 + 0.2);
    CHECK(sum.upper > 0.1 + 0.2);
    const auto product = multiply({0.1, 0.1}, {0.2, 0.2});
    CHECK(product.lower < 0.1 * 0.2);
    CHECK(product.upper > 0.1 * 0.2);
}

TEST_CASE("subnormal underflow and overflow remain enclosed") {
    const auto underflow = multiply({std::numeric_limits<double>::denorm_min(),
        std::numeric_limits<double>::denorm_min()}, {0.5, 0.5});
    CHECK(underflow.lower <= 0.0);
    CHECK(underflow.upper >= 0.0);
    const auto overflow = multiply({std::numeric_limits<double>::max(),
        std::numeric_limits<double>::max()}, {2.0, 2.0});
    CHECK(overflow.lower <= std::numeric_limits<double>::max());
    CHECK(overflow.upper == positive_infinity);
}

TEST_CASE("rounding mode support is explicit") {
    const int previous = std::fegetround();
    REQUIRE(std::fesetround(FE_TONEAREST) == 0);
    CHECK(supported_rounding_mode());
    if (std::fesetround(FE_DOWNWARD) == 0) {
        CHECK_FALSE(supported_rounding_mode());
        CHECK(std::fesetround(previous) == 0);
    }
}
