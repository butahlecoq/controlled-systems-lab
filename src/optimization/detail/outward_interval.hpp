#pragma once

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <limits>

namespace csl::optimization::detail {

static_assert(std::numeric_limits<double>::is_iec559 &&
    std::numeric_limits<double>::radix == 2 &&
    std::numeric_limits<double>::digits == 53,
    "outward intervals require IEC 60559 binary64 arithmetic");

struct Interval {
    double lower;
    double upper;
};

inline constexpr double negative_infinity = -std::numeric_limits<double>::infinity();
inline constexpr double positive_infinity = std::numeric_limits<double>::infinity();
inline bool supported_rounding_mode() { return std::fegetround() == FE_TONEAREST; }

inline Interval whole() { return {negative_infinity, positive_infinity}; }
inline double down(double value) { return std::nextafter(value, negative_infinity); }
inline double up(double value) { return std::nextafter(value, positive_infinity); }

// Knuth's TwoSum decomposition proves the rounded sum exact when its error is
// zero. For finite binary64 inputs without overflow, all intermediate exact
// sums/differences remain integer multiples of the least subnormal, so the
// decomposition does not lose a nonzero residual to underflow.
inline bool exact_sum(double a, double b, double sum) {
    if (!std::isfinite(a) || !std::isfinite(b) || !std::isfinite(sum)) return false;
    const double b_virtual = sum - a;
    const double a_virtual = sum - b_virtual;
    const double b_roundoff = b - b_virtual;
    const double a_roundoff = a - a_virtual;
    return a_roundoff + b_roundoff == 0.0;
}

inline Interval add(Interval a, Interval b) {
    const double lower = a.lower + b.lower;
    const double upper = a.upper + b.upper;
    if (std::isnan(lower) || std::isnan(upper)) return whole();
    return {exact_sum(a.lower, b.lower, lower) ? lower : down(lower),
        exact_sum(a.upper, b.upper, upper) ? upper : up(upper)};
}

inline Interval multiply(Interval a, Interval b) {
    struct Product { double value; bool exact; };
    const auto product = [](double x, double y) {
        const double value = x * y;
        const bool exact = std::isfinite(value) &&
            (x == 0.0 || y == 0.0 || x == 1.0 || y == 1.0 || x == -1.0 || y == -1.0);
        return Product{value, exact};
    };
    const std::array<Product, 4> products{
        product(a.lower, b.lower), product(a.lower, b.upper),
        product(a.upper, b.lower), product(a.upper, b.upper)};
    if (std::any_of(products.begin(), products.end(),
            [](const Product& value) { return std::isnan(value.value); })) return whole();
    const auto minimum = std::min_element(products.begin(), products.end(),
        [](const Product& x, const Product& y) { return x.value < y.value; });
    const auto maximum = std::max_element(products.begin(), products.end(),
        [](const Product& x, const Product& y) { return x.value < y.value; });
    return {minimum->exact ? minimum->value : down(minimum->value),
        maximum->exact ? maximum->value : up(maximum->value)};
}

inline Interval square(Interval value) {
    if (value.lower == 0.0 && value.upper == 0.0) return {0.0, 0.0};
    if (value.lower == value.upper &&
        (value.lower == 1.0 || value.lower == -1.0)) return {1.0, 1.0};
    if (value.lower <= 0 && value.upper >= 0) {
        const double upper = std::max(value.lower * value.lower, value.upper * value.upper);
        if (std::isnan(upper)) return {0, positive_infinity};
        return {0, up(upper)};
    }
    const double first = value.lower * value.lower;
    const double second = value.upper * value.upper;
    if (std::isnan(first) || std::isnan(second)) return {0, positive_infinity};
    return {std::max(0.0, down(std::min(first, second))), up(std::max(first, second))};
}

inline Interval square_root(Interval value) {
    if (value.upper < 0) return whole();
    double lower = 0;
    if (std::isfinite(value.lower) && value.lower > 0) {
        auto candidate = std::sqrt(value.lower);
        for (int attempt = 0; attempt < 4 && candidate > 0; ++attempt) {
            if (square({candidate, candidate}).upper <= value.lower) {
                lower = candidate;
                break;
            }
            candidate = down(candidate);
        }
    }
    double upper = positive_infinity;
    if (std::isfinite(value.upper)) {
        auto candidate = std::sqrt(std::max(0.0, value.upper));
        for (int attempt = 0; attempt < 4; ++attempt) {
            if (square({candidate, candidate}).lower >= value.upper) {
                upper = candidate;
                break;
            }
            candidate = up(candidate);
        }
        if (!std::isfinite(upper))
            upper = std::max(1.0, value.upper); // sqrt(x) <= max(1,x), x >= 0.
    }
    return {lower, upper};
}

} // namespace csl::optimization::detail
