#pragma once

// Shared bounded exact H-polytope arithmetic for synthesis verifiers.
// This header is private to synthesis: it is not a geometry-provider contract.

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <stop_token>
#include <string>
#include <utility>
#include <vector>

namespace csl::synthesis::detail::exact_h {

static_assert(std::numeric_limits<double>::is_iec559 &&
              std::numeric_limits<double>::digits == 53 &&
              std::numeric_limits<double>::max_exponent == 1024 &&
              std::numeric_limits<double>::min_exponent == -1021,
              "Exact H-polytope arithmetic requires IEEE-754 binary64 doubles");

inline constexpr std::size_t default_max_integer_bits = 8192;
inline constexpr std::size_t default_max_rows = 4096;
inline constexpr std::size_t default_max_generated_rows = 100000;
inline constexpr std::size_t default_max_operations = 5000000;
inline constexpr std::size_t default_max_variables = 32;
inline constexpr std::size_t default_max_stages = 4096;

struct Integer {
    std::vector<std::uint32_t> words;
    bool negative{};

    friend bool operator==(const Integer&, const Integer&) = default;
};

struct Row {
    std::vector<Integer> coefficients;
    Integer bound;
    bool strict{};

    friend bool operator==(const Row&, const Row&) = default;
};

struct Limits {
    std::size_t max_variables{default_max_variables};
    std::size_t max_stages{default_max_stages};
    std::size_t max_rows{default_max_rows};
    std::size_t max_generated_rows{default_max_generated_rows};
    std::size_t max_integer_bits{default_max_integer_bits};
    std::size_t max_operations{default_max_operations};
};

enum class FeasibilityState { feasible, infeasible, unsupported, cancelled };

struct FeasibilityResult {
    FeasibilityState state{FeasibilityState::unsupported};
    std::size_t peak_rows{};
    std::size_t generated_rows{};
    std::size_t maximum_integer_bits{};
    std::string reason;
};

enum class InclusionState { included, not_included, unsupported, cancelled };

struct InclusionResult {
    InclusionState state{InclusionState::unsupported};
    std::string reason;
};

namespace exact_detail {

inline void trim(Integer& value) {
    while (!value.words.empty() && value.words.back() == 0)
        value.words.pop_back();
    if (value.words.empty())
        value.negative = false;
}

inline bool is_zero(const Integer& value) noexcept {
    return value.words.empty();
}

inline std::size_t bit_length(const Integer& value) noexcept {
    if (value.words.empty())
        return 0;
    const auto top = value.words.back();
    return (value.words.size() - 1) * 32 +
           (32U - static_cast<unsigned>(std::countl_zero(top)));
}

inline unsigned trailing_zero_bits(const Integer& value) noexcept {
    for (std::size_t i = 0; i < value.words.size(); ++i) {
        if (value.words[i])
            return static_cast<unsigned>(i * 32) +
                   static_cast<unsigned>(std::countr_zero(value.words[i]));
    }
    return 0;
}

inline void shift_right(Integer& value, unsigned bits) {
    if (bits == 0 || is_zero(value))
        return;
    const std::size_t whole = bits / 32;
    const unsigned partial = bits % 32;
    if (whole >= value.words.size()) {
        value = {};
        return;
    }
    std::vector<std::uint32_t> shifted(value.words.size() - whole, 0);
    for (std::size_t i = whole; i < value.words.size(); ++i) {
        const std::size_t at = i - whole;
        shifted[at] = value.words[i] >> partial;
        if (partial && i + 1 < value.words.size())
            shifted[at] |= value.words[i + 1] << (32U - partial);
    }
    value.words = std::move(shifted);
    trim(value);
}

inline void normalize_power_of_two(Row& row) {
    unsigned common = std::numeric_limits<unsigned>::max();
    for (const auto& coefficient : row.coefficients)
        if (!is_zero(coefficient))
            common = std::min(common, trailing_zero_bits(coefficient));
    if (!is_zero(row.bound))
        common = std::min(common, trailing_zero_bits(row.bound));
    if (common == std::numeric_limits<unsigned>::max() || common == 0)
        return;
    for (auto& coefficient : row.coefficients)
        shift_right(coefficient, common);
    shift_right(row.bound, common);
}

inline int compare_magnitude(const Integer& lhs, const Integer& rhs) noexcept {
    if (lhs.words.size() != rhs.words.size())
        return lhs.words.size() < rhs.words.size() ? -1 : 1;
    for (std::size_t i = lhs.words.size(); i-- > 0;)
        if (lhs.words[i] != rhs.words[i])
            return lhs.words[i] < rhs.words[i] ? -1 : 1;
    return 0;
}

inline int compare(const Integer& lhs, const Integer& rhs) noexcept {
    if (lhs.negative != rhs.negative)
        return lhs.negative ? -1 : 1;
    const int magnitude = compare_magnitude(lhs, rhs);
    return lhs.negative ? -magnitude : magnitude;
}

inline bool add_magnitude(Integer& lhs, const Integer& rhs,
                          std::size_t max_bits) {
    const auto size = std::max(lhs.words.size(), rhs.words.size());
    lhs.words.resize(size, 0);
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < size; ++i) {
        const std::uint64_t a = lhs.words[i];
        const std::uint64_t b = i < rhs.words.size() ? rhs.words[i] : 0;
        const std::uint64_t sum = a + b + carry;
        lhs.words[i] = static_cast<std::uint32_t>(sum);
        carry = sum >> 32;
    }
    if (carry)
        lhs.words.push_back(static_cast<std::uint32_t>(carry));
    trim(lhs);
    return bit_length(lhs) <= max_bits;
}

inline void subtract_magnitude(Integer& lhs, const Integer& rhs) {
    std::uint64_t borrow = 0;
    for (std::size_t i = 0; i < lhs.words.size(); ++i) {
        const std::uint64_t a = lhs.words[i];
        const std::uint64_t b =
            (i < rhs.words.size() ? rhs.words[i] : 0) + borrow;
        lhs.words[i] = static_cast<std::uint32_t>(a - b);
        borrow = a < b ? 1 : 0;
    }
    trim(lhs);
}

inline bool add(Integer& lhs, const Integer& rhs, std::size_t max_bits) {
    if (is_zero(rhs))
        return true;
    if (is_zero(lhs)) {
        lhs = rhs;
        return bit_length(lhs) <= max_bits;
    }
    if (lhs.negative == rhs.negative)
        return add_magnitude(lhs, rhs, max_bits);
    const int order = compare_magnitude(lhs, rhs);
    if (order == 0) {
        lhs = {};
    } else if (order > 0) {
        subtract_magnitude(lhs, rhs);
    } else {
        Integer result = rhs;
        subtract_magnitude(result, lhs);
        lhs = std::move(result);
    }
    return bit_length(lhs) <= max_bits;
}

inline bool multiply_magnitude(const Integer& lhs, const Integer& rhs,
                               std::size_t max_bits, Integer& result) {
    result = {};
    if (is_zero(lhs) || is_zero(rhs))
        return true;
    if (lhs.words.size() > std::numeric_limits<std::size_t>::max() -
                               rhs.words.size())
        return false;
    const std::size_t result_words = lhs.words.size() + rhs.words.size();
    const std::size_t max_words = max_bits / 32 + (max_bits % 32 != 0);
    if (result_words > max_words && result_words - max_words > 1)
        return false;
    result.words.assign(result_words, 0);
    for (std::size_t i = 0; i < lhs.words.size(); ++i) {
        std::uint64_t carry = 0;
        for (std::size_t j = 0; j < rhs.words.size(); ++j) {
            const std::size_t at = i + j;
            const std::uint64_t product =
                static_cast<std::uint64_t>(lhs.words[i]) * rhs.words[j] +
                result.words[at] + carry;
            result.words[at] = static_cast<std::uint32_t>(product);
            carry = product >> 32;
        }
        std::size_t at = i + rhs.words.size();
        while (carry) {
            if (at >= result.words.size())
                return false;
            const std::uint64_t sum = result.words[at] + carry;
            result.words[at] = static_cast<std::uint32_t>(sum);
            carry = sum >> 32;
            ++at;
        }
    }
    trim(result);
    return bit_length(result) <= max_bits;
}

inline bool multiply(const Integer& lhs, const Integer& rhs,
                     std::size_t max_bits, Integer& result) {
    if (!multiply_magnitude(lhs, rhs, max_bits, result))
        return false;
    result.negative = !is_zero(result) && lhs.negative != rhs.negative;
    return true;
}

inline bool shift_left(Integer& value, std::size_t bits,
                       std::size_t max_bits) {
    if (bit_length(value) > max_bits)
        return false;
    if (is_zero(value) || bits == 0)
        return true;
    if (bits > max_bits - bit_length(value))
        return false;
    const std::size_t whole = bits / 32;
    const unsigned partial = static_cast<unsigned>(bits % 32);
    std::vector<std::uint32_t> shifted(value.words.size() + whole +
                                       (partial ? 1U : 0U), 0);
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < value.words.size(); ++i) {
        const std::uint64_t current =
            (static_cast<std::uint64_t>(value.words[i]) << partial) | carry;
        shifted[i + whole] = static_cast<std::uint32_t>(current);
        carry = current >> 32;
    }
    if (carry)
        shifted[value.words.size() + whole] =
            static_cast<std::uint32_t>(carry);
    value.words = std::move(shifted);
    trim(value);
    return bit_length(value) <= max_bits;
}

inline Integer from_u64(std::uint64_t value, bool negative = false) {
    Integer result;
    if (value) {
        result.words.push_back(static_cast<std::uint32_t>(value));
        const auto high = static_cast<std::uint32_t>(value >> 32);
        if (high)
            result.words.push_back(high);
        result.negative = negative;
    }
    return result;
}

struct Dyadic {
    std::uint64_t significand{};
    int exponent{};
    bool negative{};
};

inline Dyadic decode(double value) noexcept {
    const auto bits = std::bit_cast<std::uint64_t>(value);
    const auto exponent_bits = static_cast<unsigned>((bits >> 52) & 0x7ffU);
    const auto fraction = bits & ((std::uint64_t{1} << 52) - 1);
    if (exponent_bits == 0)
        return {fraction, -1074, (bits >> 63) != 0};
    return {(std::uint64_t{1} << 52) | fraction,
            static_cast<int>(exponent_bits) - 1075, (bits >> 63) != 0};
}

inline bool exact_integer(double value, int common_exponent,
                          std::size_t max_bits, Integer& result) {
    const auto dyadic = decode(value);
    result = from_u64(dyadic.significand, dyadic.negative);
    if (!dyadic.significand)
        return true;
    const int shift = dyadic.exponent - common_exponent;
    if (shift < 0)
        return false;
    return shift_left(result, static_cast<std::size_t>(shift), max_bits);
}

inline bool make_row(std::span<const double> coefficients, double bound,
                     bool strict, std::size_t max_bits, Row& result,
                     int* binary_exponent = nullptr) {
    if (!std::isfinite(bound))
        return false;
    int common_exponent = std::numeric_limits<int>::max();
    const auto consider = [&](double value) {
        if (!std::isfinite(value))
            return false;
        const auto dyadic = decode(value);
        if (dyadic.significand)
            common_exponent = std::min(common_exponent, dyadic.exponent);
        return true;
    };
    for (double coefficient : coefficients)
        if (!consider(coefficient))
            return false;
    if (!consider(bound))
        return false;
    if (common_exponent == std::numeric_limits<int>::max())
        common_exponent = 0;
    result = {};
    result.coefficients.reserve(coefficients.size());
    for (double coefficient : coefficients) {
        Integer integer;
        if (!exact_integer(coefficient, common_exponent, max_bits, integer))
            return false;
        result.coefficients.push_back(std::move(integer));
    }
    if (!exact_integer(bound, common_exponent, max_bits, result.bound))
        return false;
    result.strict = strict;
    unsigned common_power = std::numeric_limits<unsigned>::max();
    for (const auto& coefficient : result.coefficients)
        if (!is_zero(coefficient))
            common_power = std::min(common_power,
                                    trailing_zero_bits(coefficient));
    if (!is_zero(result.bound))
        common_power = std::min(common_power,
                                trailing_zero_bits(result.bound));
    if (common_power == std::numeric_limits<unsigned>::max())
        common_power = 0;
    normalize_power_of_two(result);
    if (binary_exponent)
        *binary_exponent = common_exponent + static_cast<int>(common_power);
    return true;
}

inline bool row_is_constant(const Row& row) noexcept {
    return std::all_of(row.coefficients.begin(), row.coefficients.end(),
                       is_zero);
}

inline bool normalize_rows(std::vector<Row>& rows, std::size_t max_rows) {
    std::vector<Row> nonconstant;
    nonconstant.reserve(rows.size());
    for (auto& row : rows) {
        if (row_is_constant(row)) {
            const int bound_order = compare(row.bound, {});
            if (bound_order < 0 || (bound_order == 0 && row.strict))
                return false;
            continue;
        }
        nonconstant.push_back(std::move(row));
    }
    const auto less_integer = [](const Integer& lhs, const Integer& rhs) {
        return compare(lhs, rhs) < 0;
    };
    std::sort(nonconstant.begin(), nonconstant.end(), [&](const Row& lhs,
                                                           const Row& rhs) {
        for (std::size_t i = 0; i < lhs.coefficients.size(); ++i) {
            if (lhs.coefficients[i] == rhs.coefficients[i])
                continue;
            return less_integer(lhs.coefficients[i], rhs.coefficients[i]);
        }
        if (lhs.bound != rhs.bound)
            return less_integer(lhs.bound, rhs.bound);
        return lhs.strict < rhs.strict;
    });
    nonconstant.erase(std::unique(nonconstant.begin(), nonconstant.end()),
                      nonconstant.end());
    if (nonconstant.size() > max_rows)
        return false;
    rows = std::move(nonconstant);
    return true;
}

} // namespace exact_detail

inline bool make_row(std::span<const double> coefficients, double bound,
                     bool strict, std::size_t max_integer_bits, Row& result,
                     int* binary_exponent = nullptr) {
    return exact_detail::make_row(coefficients, bound, strict,
                                  max_integer_bits, result, binary_exponent);
}

inline bool append_equality(std::span<const double> coefficients, double value,
                            std::size_t max_integer_bits,
                            std::vector<Row>& rows) {
    Row positive;
    if (!make_row(coefficients, value, false, max_integer_bits, positive))
        return false;
    Row negative = positive;
    for (auto& coefficient : negative.coefficients)
        coefficient.negative = !exact_detail::is_zero(coefficient) &&
                                !coefficient.negative;
    negative.bound.negative = !exact_detail::is_zero(negative.bound) &&
                              !negative.bound.negative;
    rows.push_back(std::move(positive));
    rows.push_back(std::move(negative));
    return true;
}

inline bool append_inequality(std::span<const double> coefficients,
                             double bound, bool strict,
                             std::size_t max_integer_bits,
                             std::vector<Row>& rows) {
    Row row;
    if (!make_row(coefficients, bound, strict, max_integer_bits, row))
        return false;
    rows.push_back(std::move(row));
    return true;
}

inline FeasibilityResult feasible(std::vector<Row> rows,
                                  std::size_t variables,
                                  Limits limits = {},
                                  std::stop_token cancellation = {},
                                  std::size_t retained_variables = 0,
                                  std::vector<Row>* projected_rows = nullptr) {
    if (projected_rows)
        projected_rows->clear();
    FeasibilityResult result;
    const auto unsupported = [&](const char* reason) {
        result.state = FeasibilityState::unsupported;
        result.reason = reason;
        return result;
    };
    if (variables > limits.max_variables)
        return unsupported("Variable count exceeds the exact feasibility limit");
    if (retained_variables > variables)
        return unsupported("Retained variable count exceeds the relation dimension");
    if (rows.size() > limits.max_rows)
        return unsupported("Initial row count exceeds the exact feasibility limit");
    if (cancellation.stop_requested()) {
        result.state = FeasibilityState::cancelled;
        result.reason = "Exact feasibility was cancelled";
        return result;
    }
    for (auto& row : rows) {
        if (row.coefficients.size() != variables)
            return unsupported("Constraint row dimensions do not match");
        exact_detail::trim(row.bound);
        result.maximum_integer_bits = std::max(
            result.maximum_integer_bits, exact_detail::bit_length(row.bound));
        for (auto& coefficient : row.coefficients) {
            exact_detail::trim(coefficient);
            result.maximum_integer_bits = std::max(
                result.maximum_integer_bits,
                exact_detail::bit_length(coefficient));
        }
        if (result.maximum_integer_bits > limits.max_integer_bits)
            return unsupported("Input integer bit limit exceeded");
    }
    if (!exact_detail::normalize_rows(rows, limits.max_rows)) {
        result.state = FeasibilityState::infeasible;
        result.peak_rows = rows.size();
        return result;
    }
    result.peak_rows = rows.size();
    std::size_t operations = 0;
    for (std::size_t eliminated = 0;
         eliminated < variables - retained_variables; ++eliminated) {
        if (cancellation.stop_requested()) {
            result.state = FeasibilityState::cancelled;
            result.reason = "Exact feasibility was cancelled";
            return result;
        }
        const std::size_t variable = retained_variables;
        std::vector<const Row*> positive, negative, zero;
        for (const auto& row : rows) {
            const int sign = exact_detail::compare(row.coefficients[variable], {});
            if (sign > 0)
                positive.push_back(&row);
            else if (sign < 0)
                negative.push_back(&row);
            else
                zero.push_back(&row);
        }
        if (!positive.empty() && !negative.empty() &&
            positive.size() > (limits.max_rows -
                               std::min(limits.max_rows, zero.size())) /
                                  negative.size())
            return unsupported("Fourier-Motzkin row limit would be exceeded");
        const std::size_t pair_count = positive.size() * negative.size();
        if (zero.size() > limits.max_rows ||
            pair_count > limits.max_rows - zero.size() ||
            pair_count > limits.max_generated_rows -
                             std::min(limits.max_generated_rows,
                                      result.generated_rows))
            return unsupported("Fourier-Motzkin resource limit would be exceeded");
        const std::size_t remaining_variables = variables - eliminated;
        if (remaining_variables >
            std::numeric_limits<std::size_t>::max() / 3)
            return unsupported("Exact operation count overflows size_t");
        const std::size_t operations_per_pair = 3 * remaining_variables;
        if (operations_per_pair > limits.max_operations ||
            (operations_per_pair != 0 &&
             pair_count >
                 (limits.max_operations - operations) / operations_per_pair))
            return unsupported("Exact arithmetic operation limit exceeded");
        operations += pair_count * operations_per_pair;
        std::vector<Row> next;
        next.reserve(zero.size() + pair_count);
        for (const Row* row : zero) {
            Row copy = *row;
            copy.coefficients.erase(copy.coefficients.begin() +
                                    static_cast<std::ptrdiff_t>(variable));
            next.push_back(std::move(copy));
        }
        std::size_t pair_visits = 0;
        for (const Row* upper : positive) {
            for (const Row* lower : negative) {
                if ((pair_visits++ & 255U) == 0 && cancellation.stop_requested()) {
                    result.state = FeasibilityState::cancelled;
                    result.reason = "Exact feasibility was cancelled";
                    return result;
                }
                const Integer upper_scale = upper->coefficients[variable];
                Integer lower_scale = lower->coefficients[variable];
                lower_scale.negative = false;
                Row combined;
                combined.strict = upper->strict || lower->strict;
                combined.coefficients.reserve(variables - eliminated - 1);
                for (std::size_t column = 0;
                     column < variables - eliminated; ++column) {
                    if (column == variable)
                        continue;
                    Integer left, right;
                    if (!exact_detail::multiply(lower_scale,
                                                upper->coefficients[column],
                                                limits.max_integer_bits, left) ||
                        !exact_detail::multiply(upper_scale,
                                                lower->coefficients[column],
                                                limits.max_integer_bits, right) ||
                        exact_detail::bit_length(left) >
                            limits.max_integer_bits ||
                        exact_detail::bit_length(right) >
                            limits.max_integer_bits)
                        return unsupported("Exact integer bit limit exceeded");
                    result.maximum_integer_bits = std::max(
                        result.maximum_integer_bits,
                        exact_detail::bit_length(left));
                    result.maximum_integer_bits = std::max(
                        result.maximum_integer_bits,
                        exact_detail::bit_length(right));
                    if (!exact_detail::add(left, right,
                                           limits.max_integer_bits))
                        return unsupported("Exact integer bit limit exceeded");
                    result.maximum_integer_bits = std::max(
                        result.maximum_integer_bits,
                        exact_detail::bit_length(left));
                    combined.coefficients.push_back(std::move(left));
                }
                Integer left_bound, right_bound;
                if (!exact_detail::multiply(lower_scale, upper->bound,
                                            limits.max_integer_bits,
                                            left_bound) ||
                    !exact_detail::multiply(upper_scale, lower->bound,
                                            limits.max_integer_bits,
                                            right_bound))
                    return unsupported("Exact integer bit limit exceeded");
                result.maximum_integer_bits = std::max(
                    result.maximum_integer_bits,
                    exact_detail::bit_length(left_bound));
                result.maximum_integer_bits = std::max(
                    result.maximum_integer_bits,
                    exact_detail::bit_length(right_bound));
                if (!exact_detail::add(left_bound, right_bound,
                                       limits.max_integer_bits))
                    return unsupported("Exact integer bit limit exceeded");
                combined.bound = std::move(left_bound);
                exact_detail::normalize_power_of_two(combined);
                result.maximum_integer_bits = std::max(
                    result.maximum_integer_bits,
                    exact_detail::bit_length(combined.bound));
                next.push_back(std::move(combined));
            }
        }
        result.generated_rows += pair_count;
        if (!exact_detail::normalize_rows(next, limits.max_rows)) {
            result.state = FeasibilityState::infeasible;
            result.peak_rows = std::max(result.peak_rows, next.size());
            return result;
        }
        result.peak_rows = std::max(result.peak_rows, next.size());
        rows = std::move(next);
    }
    result.state = FeasibilityState::feasible;
    if (projected_rows)
        *projected_rows = std::move(rows);
    return result;
}

struct ExactRational {
    Integer numerator;
    Integer denominator{exact_detail::from_u64(1)};
    int binary_exponent{};
};

enum class LinearMinimumState {
    minimum,
    infeasible,
    unbounded_below,
    unsupported,
    cancelled
};

struct LinearMinimumResult {
    LinearMinimumState state{LinearMinimumState::unsupported};
    ExactRational value;
    bool attained{};
    std::size_t peak_rows{};
    std::size_t generated_rows{};
    std::size_t maximum_integer_bits{};
    std::string reason;
};

inline bool compare_rationals(const ExactRational& lhs,
                              const ExactRational& rhs,
                              std::size_t max_bits, int& order) {
    if (lhs.denominator.negative || rhs.denominator.negative ||
        exact_detail::is_zero(lhs.denominator) ||
        exact_detail::is_zero(rhs.denominator))
        return false;
    Integer left, right;
    if (!exact_detail::multiply(lhs.numerator, rhs.denominator, max_bits, left) ||
        !exact_detail::multiply(rhs.numerator, lhs.denominator, max_bits, right))
        return false;
    order = exact_detail::compare(left, right);
    return true;
}

inline bool compare_scaled_rationals(const ExactRational& lhs,
                                     const ExactRational& rhs,
                                     std::size_t max_bits, int& order) {
    if (lhs.denominator.negative || rhs.denominator.negative ||
        exact_detail::is_zero(lhs.denominator) ||
        exact_detail::is_zero(rhs.denominator))
        return false;
    Integer left, right;
    if (!exact_detail::multiply(lhs.numerator, rhs.denominator, max_bits, left) ||
        !exact_detail::multiply(rhs.numerator, lhs.denominator, max_bits, right))
        return false;
    const auto lhs_shift = static_cast<std::int64_t>(lhs.binary_exponent) -
                           static_cast<std::int64_t>(rhs.binary_exponent);
    if (lhs_shift > 0) {
        if (static_cast<std::uint64_t>(lhs_shift) > max_bits)
            return false;
        const auto shift = static_cast<std::size_t>(lhs_shift);
        if (!exact_detail::shift_left(left, shift, max_bits))
            return false;
    } else if (lhs_shift < 0) {
        const auto rhs_shift = static_cast<std::uint64_t>(-lhs_shift);
        if (rhs_shift > max_bits)
            return false;
        const auto shift = static_cast<std::size_t>(rhs_shift);
        if (!exact_detail::shift_left(right, shift, max_bits))
            return false;
    }
    order = exact_detail::compare(left, right);
    return true;
}

inline bool exact_rational_to_double(const ExactRational& value,
                                     std::size_t max_bits, double& result) {
    if (exact_detail::is_zero(value.numerator)) {
        result = 0.0;
        return true;
    }
    if (value.denominator.negative || exact_detail::is_zero(value.denominator))
        return false;

    ExactRational magnitude = value;
    const bool negative = magnitude.numerator.negative;
    magnitude.numerator.negative = false;
    constexpr std::uint64_t max_finite_bits = 0x7fefffffffffffffULL;
    std::uint64_t low = 0;
    std::uint64_t high = max_finite_bits;
    while (low <= high) {
        const auto bits = low + (high - low) / 2;
        const auto candidate = std::bit_cast<double>(bits);
        const auto dyadic = exact_detail::decode(candidate);
        ExactRational candidate_rational;
        candidate_rational.numerator = exact_detail::from_u64(dyadic.significand);
        candidate_rational.binary_exponent = dyadic.exponent;
        int order = 0;
        if (!compare_scaled_rationals(magnitude, candidate_rational,
                                      max_bits, order))
            return false;
        if (order == 0) {
            const auto signed_bits = bits | (negative ? (std::uint64_t{1} << 63) : 0);
            result = std::bit_cast<double>(signed_bits);
            return true;
        }
        if (order > 0) {
            if (bits == max_finite_bits) break;
            low = bits + 1;
        } else {
            if (bits == 0) break;
            high = bits - 1;
        }
    }
    return false;
}

// Project an exact H-relation onto the integer-scaled value of a binary64
// linear objective. The objective scale is retained so values from paths with
// different coefficient exponents can be compared without floating point.
inline LinearMinimumResult minimize_linear(
    std::span<const Row> relation, std::size_t variables,
    std::span<const double> objective, double offset, Limits limits = {},
    std::stop_token cancellation = {}) {
    const auto unsupported = [](const char* reason) {
        LinearMinimumResult result;
        result.reason = reason;
        return result;
    };
    if (cancellation.stop_requested())
        return {LinearMinimumState::cancelled, {}, false, 0, 0, 0,
                "Exact linear minimization was cancelled"};
    if (objective.size() != variables || variables >= limits.max_variables ||
        variables == std::numeric_limits<std::size_t>::max() ||
        relation.size() > limits.max_rows ||
        relation.size() > limits.max_operations /
                              std::max<std::size_t>(variables + 1, 1))
        return unsupported("Linear objective or augmented relation exceeds exact limits");
    Row objective_row;
    int objective_exponent = 0;
    if (!make_row(objective, offset, false, limits.max_integer_bits,
                  objective_row, &objective_exponent))
        return unsupported("Linear objective is non-finite or exceeds exact limits");
    if (relation.size() > limits.max_rows -
                              std::min<std::size_t>(2, limits.max_rows))
        return unsupported("Objective equation exceeds the exact row limit");

    std::vector<Row> augmented;
    augmented.reserve(relation.size() + 2);
    for (const auto& row : relation) {
        if (cancellation.stop_requested())
            return {LinearMinimumState::cancelled, {}, false, 0, 0, 0,
                    "Exact linear minimization was cancelled"};
        if (row.coefficients.size() != variables)
            return unsupported("Relation row dimensions do not match the objective");
        Row expanded = row;
        expanded.coefficients.insert(expanded.coefficients.begin(), Integer{});
        augmented.push_back(std::move(expanded));
    }
    Row objective_equality;
    objective_equality.coefficients.reserve(variables + 1);
    objective_equality.coefficients.push_back(exact_detail::from_u64(1));
    for (const auto& coefficient : objective_row.coefficients) {
        Integer negated = coefficient;
        negated.negative = !exact_detail::is_zero(negated) && !negated.negative;
        objective_equality.coefficients.push_back(std::move(negated));
    }
    objective_equality.bound = objective_row.bound;
    Row inverse_equality = objective_equality;
    for (auto& coefficient : inverse_equality.coefficients)
        coefficient.negative = !exact_detail::is_zero(coefficient) &&
                               !coefficient.negative;
    inverse_equality.bound.negative = !exact_detail::is_zero(inverse_equality.bound) &&
                                      !inverse_equality.bound.negative;
    augmented.push_back(std::move(objective_equality));
    augmented.push_back(std::move(inverse_equality));

    std::vector<Row> projection;
    const auto projected = feasible(std::move(augmented), variables + 1,
                                    limits, cancellation, 1, &projection);
    LinearMinimumResult result;
    result.peak_rows = projected.peak_rows;
    result.generated_rows = projected.generated_rows;
    result.maximum_integer_bits = projected.maximum_integer_bits;
    if (projected.state == FeasibilityState::cancelled) {
        result.state = LinearMinimumState::cancelled;
        result.reason = projected.reason;
        return result;
    }
    if (projected.state == FeasibilityState::unsupported) {
        result.state = LinearMinimumState::unsupported;
        result.reason = projected.reason;
        return result;
    }
    if (projected.state == FeasibilityState::infeasible) {
        result.state = LinearMinimumState::infeasible;
        return result;
    }

    bool have_lower_bound = false;
    ExactRational minimum;
    bool attained = false;
    for (const auto& row : projection) {
        if (cancellation.stop_requested())
            return {LinearMinimumState::cancelled, {}, false,
                    result.peak_rows, result.generated_rows,
                    result.maximum_integer_bits,
                    "Exact linear minimization was cancelled"};
        if (row.coefficients.size() != 1)
            return unsupported("Objective projection did not retain one variable");
        const int coefficient_order = exact_detail::compare(row.coefficients[0], {});
        if (coefficient_order >= 0)
            continue;
        ExactRational candidate;
        candidate.numerator = row.bound;
        candidate.numerator.negative = !exact_detail::is_zero(candidate.numerator) &&
                                       !candidate.numerator.negative;
        candidate.denominator = row.coefficients[0];
        candidate.denominator.negative = false;
        candidate.binary_exponent = objective_exponent;
        int order = 1;
        if (have_lower_bound &&
            !compare_rationals(candidate, minimum, limits.max_integer_bits, order))
            return unsupported("Rational objective comparison exceeds exact limits");
        if (!have_lower_bound || order > 0) {
            minimum = std::move(candidate);
            have_lower_bound = true;
            attained = !row.strict;
        } else if (order == 0 && row.strict) {
            attained = false;
        }
    }
    if (!have_lower_bound) {
        result.state = LinearMinimumState::unbounded_below;
        return result;
    }
    result.state = LinearMinimumState::minimum;
    result.value = std::move(minimum);
    result.attained = attained;
    return result;
}

// Prove source ⊆ target by checking whether source intersects the strict
// complement of each target half-space. Equality rows must be represented by
// both opposing non-strict inequalities, as produced by append_equality.
inline InclusionResult included_in(std::span<const Row> source,
                                   std::span<const Row> target,
                                   std::size_t variables,
                                   Limits limits = {},
                                   std::stop_token cancellation = {}) {
    const auto unsupported = [](const char* reason) {
        return InclusionResult{InclusionState::unsupported, reason};
    };
    if (cancellation.stop_requested())
        return {InclusionState::cancelled,
                "Exact relation inclusion was cancelled"};
    if (variables > limits.max_variables || target.size() > limits.max_rows ||
        source.size() > limits.max_rows ||
        (!target.empty() && source.size() == limits.max_rows))
        return unsupported("Relation dimensions exceed exact inclusion limits");
    const auto valid_rows = [&](std::span<const Row> rows) {
        for (const auto& row : rows) {
            if (row.coefficients.size() != variables ||
                exact_detail::bit_length(row.bound) > limits.max_integer_bits)
                return false;
            for (const auto& coefficient : row.coefficients)
                if (exact_detail::bit_length(coefficient) > limits.max_integer_bits)
                    return false;
        }
        return true;
    };
    if (!valid_rows(source) || !valid_rows(target))
        return unsupported("Relation rows exceed exact inclusion limits");
    if (target.size() > limits.max_generated_rows ||
        (!target.empty() && limits.max_operations / target.size() == 0))
        return unsupported("Relation inclusion exceeds the exact operation limit");
    Limits per_check = limits;
    if (!target.empty()) {
        per_check.max_operations /= target.size();
        per_check.max_generated_rows /= target.size();
    }
    for (const auto& constraint : target) {
        if (cancellation.stop_requested())
            return {InclusionState::cancelled,
                    "Exact relation inclusion was cancelled"};
        if (constraint.coefficients.size() != variables)
            return unsupported("Target relation row dimensions do not match");
        std::vector<Row> counterexample(source.begin(), source.end());
        Row violation = constraint;
        for (auto& coefficient : violation.coefficients)
            coefficient.negative = !exact_detail::is_zero(coefficient) &&
                                   !coefficient.negative;
        violation.bound.negative = !exact_detail::is_zero(violation.bound) &&
                                   !violation.bound.negative;
        violation.strict = !constraint.strict;
        counterexample.push_back(std::move(violation));
        auto result = feasible(std::move(counterexample), variables, per_check,
                               cancellation);
        if (result.state == FeasibilityState::feasible)
            return {InclusionState::not_included,
                    "Source relation contains a target-half-space violation"};
        if (result.state == FeasibilityState::unsupported)
            return unsupported("Exact feasibility could not decide relation inclusion");
        if (result.state == FeasibilityState::cancelled)
            return {InclusionState::cancelled, result.reason};
    }
    return {InclusionState::included, {}};
}

} // namespace csl::synthesis::detail::exact_h
