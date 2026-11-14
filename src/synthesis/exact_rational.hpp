#pragma once

// Bounded exact rational arithmetic shared by compiled profile verifiers.
// This is private synthesis machinery; it is not a set representation API.

#include "exact_h_polytope.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <string_view>

namespace csl::synthesis::detail::exact_rational {

namespace exact_h = ::csl::synthesis::detail::exact_h;
using exact_h::Integer;

inline constexpr std::size_t default_max_integer_bits = 8192;
inline constexpr std::size_t default_max_operations = 100000;

struct Budget {
    std::size_t max_integer_bits{default_max_integer_bits};
    std::size_t max_operations{default_max_operations};
    std::size_t operations{};
    std::size_t maximum_integer_bits{};
};

struct Rational {
    exact_h::Integer numerator;
    exact_h::Integer denominator{exact_h::exact_detail::from_u64(1)};
    int binary_exponent{};

    friend bool operator==(const Rational &, const Rational &) = default;
};

inline bool charge(Budget &budget) noexcept {
    if (budget.operations >= budget.max_operations)
        return false;
    ++budget.operations;
    return true;
}

inline bool observe(Budget &budget, const exact_h::Integer &value) noexcept {
    const auto bits = exact_h::exact_detail::bit_length(value);
    budget.maximum_integer_bits = std::max(budget.maximum_integer_bits, bits);
    return bits <= budget.max_integer_bits;
}

inline bool valid(const Rational &value, Budget &budget) noexcept {
    return !exact_h::exact_detail::is_zero(value.denominator) && !value.denominator.negative &&
           observe(budget, value.numerator) && observe(budget, value.denominator);
}

inline bool divide_magnitude(const Integer &dividend, const Integer &divisor, Integer &quotient,
                             Integer &remainder, Budget &budget) {
    using namespace exact_h::exact_detail;
    if (is_zero(divisor) || divisor.negative || dividend.negative)
        return false;
    quotient = {};
    remainder = dividend;
    while (compare_magnitude(remainder, divisor) >= 0) {
        if (!charge(budget))
            return false;
        const auto shift = bit_length(remainder) - bit_length(divisor);
        Integer shifted = divisor;
        if (!shift_left(shifted, shift, budget.max_integer_bits))
            return false;
        auto actual_shift = shift;
        if (compare_magnitude(remainder, shifted) < 0) {
            shift_right(shifted, 1);
            --actual_shift;
        }
        subtract_magnitude(remainder, shifted);
        const auto word = actual_shift / 32;
        if (quotient.words.size() <= word)
            quotient.words.resize(word + 1, 0);
        quotient.words[word] |= std::uint32_t{1} << (actual_shift % 32);
    }
    trim(quotient);
    return observe(budget, quotient) && observe(budget, remainder);
}

inline bool gcd(const Integer &lhs, const Integer &rhs, Integer &result, Budget &budget) {
    using namespace exact_h::exact_detail;
    Integer left = lhs;
    Integer right = rhs;
    left.negative = false;
    right.negative = false;
    while (!is_zero(right)) {
        Integer quotient, remainder;
        if (!divide_magnitude(left, right, quotient, remainder, budget))
            return false;
        left = std::move(right);
        right = std::move(remainder);
    }
    result = std::move(left);
    return observe(budget, result);
}

inline bool divide_exact(Integer &value, const Integer &divisor, Budget &budget) {
    Integer magnitude = value;
    const bool negative = magnitude.negative;
    magnitude.negative = false;
    Integer quotient, remainder;
    if (!divide_magnitude(magnitude, divisor, quotient, remainder, budget) ||
        !exact_h::exact_detail::is_zero(remainder))
        return false;
    quotient.negative = negative;
    value = std::move(quotient);
    return true;
}

inline bool normalize(Rational &value, Budget &budget);

inline bool parse_integer(std::string_view text, Integer &result, Budget &budget) {
    using namespace exact_h::exact_detail;
    if (text.empty())
        return false;
    const bool negative = text.front() == '-';
    if (negative)
        text.remove_prefix(1);
    if (text.empty())
        return false;
    result = {};
    for (const char digit : text) {
        if (digit < '0' || digit > '9' || !charge(budget))
            return false;
        Integer scaled;
        if (!exact_h::exact_detail::multiply(result, from_u64(10), budget.max_integer_bits,
                                             scaled) ||
            !add(scaled, from_u64(static_cast<std::uint64_t>(digit - '0')),
                 budget.max_integer_bits))
            return false;
        result = std::move(scaled);
    }
    result.negative = negative && !is_zero(result);
    return observe(budget, result);
}

inline bool parse(std::string_view text, Rational &result, Budget &budget) {
    const auto slash = text.find('/');
    if (slash == std::string_view::npos || text.find('/', slash + 1) != std::string_view::npos)
        return false;
    if (!charge(budget) || !parse_integer(text.substr(0, slash), result.numerator, budget) ||
        !parse_integer(text.substr(slash + 1), result.denominator, budget))
        return false;
    if (result.denominator.negative)
        return false;
    result.binary_exponent = 0;
    return normalize(result, budget);
}

inline bool normalize(Rational &value, Budget &budget) {
    using namespace exact_h::exact_detail;
    if (is_zero(value.denominator))
        return false;
    if (value.denominator.negative) {
        value.denominator.negative = false;
        if (!is_zero(value.numerator))
            value.numerator.negative = !value.numerator.negative;
    }
    if (is_zero(value.numerator)) {
        value.denominator = from_u64(1);
        value.binary_exponent = 0;
        return true;
    }

    const auto numerator_twos = trailing_zero_bits(value.numerator);
    if (numerator_twos) {
        const auto next = static_cast<std::int64_t>(value.binary_exponent) + numerator_twos;
        if (next > std::numeric_limits<int>::max())
            return false;
        shift_right(value.numerator, numerator_twos);
        value.binary_exponent = static_cast<int>(next);
    }
    const auto denominator_twos = trailing_zero_bits(value.denominator);
    if (denominator_twos) {
        const auto next = static_cast<std::int64_t>(value.binary_exponent) - denominator_twos;
        if (next < std::numeric_limits<int>::min())
            return false;
        shift_right(value.denominator, denominator_twos);
        value.binary_exponent = static_cast<int>(next);
    }
    Integer common;
    if (!gcd(value.numerator, value.denominator, common, budget))
        return false;
    if (!is_zero(common) && compare_magnitude(common, from_u64(1)) != 0 &&
        (!divide_exact(value.numerator, common, budget) ||
         !divide_exact(value.denominator, common, budget)))
        return false;
    return valid(value, budget);
}

inline bool make_integer(std::int64_t integer, Rational &result, Budget &budget) {
    if (!charge(budget))
        return false;
    const bool negative = integer < 0;
    const auto magnitude = negative ? static_cast<std::uint64_t>(-(integer + 1)) + 1U
                                    : static_cast<std::uint64_t>(integer);
    result = {};
    result.numerator = exact_h::exact_detail::from_u64(magnitude, negative);
    return valid(result, budget);
}

inline bool make_fraction(std::int64_t numerator, std::int64_t denominator, Rational &result,
                          Budget &budget) {
    if (!charge(budget) || denominator == 0)
        return false;
    const bool numerator_negative = numerator < 0;
    const auto numerator_magnitude = numerator_negative
                                         ? static_cast<std::uint64_t>(-(numerator + 1)) + 1U
                                         : static_cast<std::uint64_t>(numerator);
    const bool denominator_negative = denominator < 0;
    const auto denominator_magnitude = denominator_negative
                                           ? static_cast<std::uint64_t>(-(denominator + 1)) + 1U
                                           : static_cast<std::uint64_t>(denominator);
    result = {};
    result.numerator = exact_h::exact_detail::from_u64(numerator_magnitude,
                                                       numerator_negative != denominator_negative);
    result.denominator = exact_h::exact_detail::from_u64(denominator_magnitude);
    return normalize(result, budget);
}

inline bool from_binary64(double value, Rational &result, Budget &budget) {
    if (!charge(budget) || !std::isfinite(value))
        return false;
    const auto decoded = exact_h::exact_detail::decode(value);
    result = {};
    result.numerator = exact_h::exact_detail::from_u64(decoded.significand, decoded.negative);
    result.binary_exponent = decoded.exponent;
    return normalize(result, budget);
}

inline bool negate(const Rational &value, Rational &result, Budget &budget) {
    if (!charge(budget) || !valid(value, budget))
        return false;
    result = value;
    if (!exact_h::exact_detail::is_zero(result.numerator))
        result.numerator.negative = !result.numerator.negative;
    return true;
}

inline bool add(const Rational &lhs, const Rational &rhs, Rational &result, Budget &budget) {
    if (&lhs == &result || &rhs == &result) {
        const Rational lhs_copy = lhs;
        const Rational rhs_copy = rhs;
        return add(lhs_copy, rhs_copy, result, budget);
    }
    using namespace exact_h::exact_detail;
    if (!charge(budget) || !valid(lhs, budget) || !valid(rhs, budget))
        return false;
    const auto exponent = std::min(lhs.binary_exponent, rhs.binary_exponent);
    const auto lhs_shift =
        static_cast<std::size_t>(static_cast<std::int64_t>(lhs.binary_exponent) - exponent);
    const auto rhs_shift =
        static_cast<std::size_t>(static_cast<std::int64_t>(rhs.binary_exponent) - exponent);
    if (lhs_shift > budget.max_integer_bits || rhs_shift > budget.max_integer_bits)
        return false;

    Integer left, right, left_numerator, right_numerator;
    if (lhs.denominator == rhs.denominator) {
        left = lhs.numerator;
        right = rhs.numerator;
        if (!shift_left(left, lhs_shift, budget.max_integer_bits) ||
            !shift_left(right, rhs_shift, budget.max_integer_bits) ||
            !exact_h::exact_detail::add(left, right, budget.max_integer_bits))
            return false;
        result.numerator = std::move(left);
        result.denominator = lhs.denominator;
        result.binary_exponent = exponent;
        return normalize(result, budget);
    }
    if (!exact_h::exact_detail::multiply(lhs.numerator, rhs.denominator, budget.max_integer_bits,
                                         left_numerator) ||
        !exact_h::exact_detail::multiply(rhs.numerator, lhs.denominator, budget.max_integer_bits,
                                         right_numerator))
        return false;
    left = left_numerator;
    right = right_numerator;
    if (!shift_left(left, lhs_shift, budget.max_integer_bits) ||
        !shift_left(right, rhs_shift, budget.max_integer_bits) ||
        !exact_h::exact_detail::add(left, right, budget.max_integer_bits))
        return false;
    if (!exact_h::exact_detail::multiply(lhs.denominator, rhs.denominator, budget.max_integer_bits,
                                         result.denominator))
        return false;
    result.numerator = std::move(left);
    result.binary_exponent = exponent;
    return normalize(result, budget);
}

inline bool subtract(const Rational &lhs, const Rational &rhs, Rational &result, Budget &budget) {
    Rational negative;
    return negate(rhs, negative, budget) && add(lhs, negative, result, budget);
}

inline bool multiply(const Rational &lhs, const Rational &rhs, Rational &result, Budget &budget) {
    if (&lhs == &result || &rhs == &result) {
        const Rational lhs_copy = lhs;
        const Rational rhs_copy = rhs;
        return multiply(lhs_copy, rhs_copy, result, budget);
    }
    using namespace exact_h::exact_detail;
    if (!charge(budget) || !valid(lhs, budget) || !valid(rhs, budget))
        return false;
    const auto exponent = static_cast<std::int64_t>(lhs.binary_exponent) + rhs.binary_exponent;
    if (exponent < std::numeric_limits<int>::min() || exponent > std::numeric_limits<int>::max())
        return false;
    if (!exact_h::exact_detail::multiply(lhs.numerator, rhs.numerator, budget.max_integer_bits,
                                         result.numerator) ||
        !exact_h::exact_detail::multiply(lhs.denominator, rhs.denominator, budget.max_integer_bits,
                                         result.denominator))
        return false;
    result.binary_exponent = static_cast<int>(exponent);
    return normalize(result, budget);
}

inline bool compare(const Rational &lhs, const Rational &rhs, int &order, Budget &budget) {
    using namespace exact_h::exact_detail;
    if (!charge(budget) || !valid(lhs, budget) || !valid(rhs, budget))
        return false;
    Integer left, right;
    if (!exact_h::exact_detail::multiply(lhs.numerator, rhs.denominator, budget.max_integer_bits,
                                         left) ||
        !exact_h::exact_detail::multiply(rhs.numerator, lhs.denominator, budget.max_integer_bits,
                                         right))
        return false;
    const auto exponent = std::min(lhs.binary_exponent, rhs.binary_exponent);
    const auto lhs_shift =
        static_cast<std::size_t>(static_cast<std::int64_t>(lhs.binary_exponent) - exponent);
    const auto rhs_shift =
        static_cast<std::size_t>(static_cast<std::int64_t>(rhs.binary_exponent) - exponent);
    if (lhs_shift > budget.max_integer_bits || rhs_shift > budget.max_integer_bits ||
        !shift_left(left, lhs_shift, budget.max_integer_bits) ||
        !shift_left(right, rhs_shift, budget.max_integer_bits))
        return false;
    order = exact_h::exact_detail::compare(left, right);
    return true;
}

inline bool equal(const Rational &lhs, const Rational &rhs, bool &result, Budget &budget) {
    using namespace exact_h::exact_detail;
    if (!charge(budget) || !valid(lhs, budget) || !valid(rhs, budget))
        return false;
    if (lhs.denominator == rhs.denominator && lhs.binary_exponent == rhs.binary_exponent) {
        result = exact_h::exact_detail::compare(lhs.numerator, rhs.numerator) == 0;
        return true;
    }
    int order{};
    if (!compare(lhs, rhs, order, budget))
        return false;
    result = order == 0;
    return true;
}

} // namespace csl::synthesis::detail::exact_rational
