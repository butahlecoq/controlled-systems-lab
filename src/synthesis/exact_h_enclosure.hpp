#pragma once

#include "exact_rational.hpp"

#include <algorithm>
#include <limits>
#include <optional>
#include <span>
#include <utility>
#include <vector>

namespace csl::synthesis::detail::exact_h_enclosure {

using exact_rational::Budget;
using exact_rational::Rational;

struct Interval {
    Rational lower, upper;
};

inline bool accumulate_scaled_interval(Interval &sum, double coefficient, const Interval &argument,
                                       Budget &budget) {
    Rational scale, lower, upper;
    const auto &first = coefficient < 0 ? argument.upper : argument.lower;
    const auto &last = coefficient < 0 ? argument.lower : argument.upper;
    if (!exact_rational::from_binary64(coefficient, scale, budget) ||
        !exact_rational::multiply(scale, first, lower, budget) ||
        !exact_rational::multiply(scale, last, upper, budget) ||
        !exact_rational::add(sum.lower, lower, lower, budget) ||
        !exact_rational::add(sum.upper, upper, upper, budget))
        return false;
    sum = {std::move(lower), std::move(upper)};
    return true;
}

struct Binary64UpperRow {
    std::vector<double> coefficients;
    double bound{};
};

// Enclose the exact half-space inside the supplied coordinate box. For every
// x in the box, the new normal's rounding error is at most the sum of its
// coordinatewise maxima. Add that exact allowance before rounding the RHS up.
inline std::optional<Binary64UpperRow>
enclose_upper_row(const exact_h::Row &row, std::span<const Interval> box, Budget &budget) {
    if (box.size() != row.coefficients.size())
        return std::nullopt;
    auto bits = exact_h::exact_detail::bit_length(row.bound);
    for (const auto &coefficient : row.coefficients)
        bits = std::max(bits, exact_h::exact_detail::bit_length(coefficient));
    if (bits > budget.max_integer_bits ||
        bits > static_cast<std::size_t>(std::numeric_limits<int>::max()))
        return std::nullopt;
    const auto exponent = -static_cast<int>(bits);
    const auto one = exact_h::exact_detail::from_u64(1);
    Rational corrected{row.bound, one, exponent};
    Binary64UpperRow result;
    result.coefficients.reserve(box.size());
    for (std::size_t coordinate = 0; coordinate < box.size(); ++coordinate) {
        const auto &interval = box[coordinate];
        int order{};
        if (!exact_rational::compare(interval.lower, interval.upper, order, budget) || order > 0)
            return std::nullopt;
        const auto &coefficient = row.coefficients[coordinate];
        const Rational exact{coefficient, one, exponent};
        const auto bracket =
            exact_h::bracket_binary64({coefficient, one, exponent}, budget.max_integer_bits);
        if (bracket.status != exact_h::Binary64BracketStatus::finite)
            return std::nullopt;
        result.coefficients.push_back(bracket.lower);
        if (bracket.lower == bracket.upper)
            continue;
        Rational rounded, error, allowance;
        if (!exact_rational::from_binary64(bracket.lower, rounded, budget) ||
            !exact_rational::subtract(rounded, exact, error, budget) ||
            !exact_rational::multiply(error,
                                      error.numerator.negative ? interval.lower : interval.upper,
                                      allowance, budget) ||
            !exact_rational::add(corrected, allowance, corrected, budget))
            return std::nullopt;
    }
    const auto bound = exact_h::bracket_binary64(
        {corrected.numerator, corrected.denominator, corrected.binary_exponent},
        budget.max_integer_bits);
    if (bound.status != exact_h::Binary64BracketStatus::finite)
        return std::nullopt;
    result.bound = bound.upper;
    return result;
}

} // namespace csl::synthesis::detail::exact_h_enclosure
