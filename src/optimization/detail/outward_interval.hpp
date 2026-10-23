#pragma once

#include <algorithm>
#include <array>
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

inline Interval whole() { return {negative_infinity, positive_infinity}; }
inline double down(double value) { return std::nextafter(value, negative_infinity); }
inline double up(double value) { return std::nextafter(value, positive_infinity); }

inline Interval add(Interval a, Interval b) {
    const double lower = a.lower + b.lower;
    const double upper = a.upper + b.upper;
    if (std::isnan(lower) || std::isnan(upper)) return whole();
    return {down(lower), up(upper)};
}

inline Interval multiply(Interval a, Interval b) {
    const std::array<double, 4> products{
        a.lower * b.lower, a.lower * b.upper, a.upper * b.lower, a.upper * b.upper};
    if (std::any_of(products.begin(), products.end(),
            [](double value) { return std::isnan(value); })) return whole();
    const auto [minimum, maximum] = std::minmax_element(products.begin(), products.end());
    return {down(*minimum), up(*maximum)};
}

inline Interval square(Interval value) {
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
