#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>

namespace csl::geometry::detail {
namespace exact_detail {

static_assert(std::numeric_limits<double>::is_iec559 &&
    std::numeric_limits<double>::digits == 53 &&
    std::numeric_limits<double>::max_exponent == 1024 &&
    std::numeric_limits<double>::min_exponent == -1021,
    "Exact geometry dyadic arithmetic requires IEEE-754 binary64 double");

// A binary64 significand has at most 53 bits. A finite binary64 value has
// exponent at most 971 in this representation and at least -1074, so a
// product spans fewer than 4200 positions after scaling by 2^-2148. Even
// summing size_t::max products adds fewer than 64 bits; 8192 bits therefore
// suffice. Every insertion and carry is still checked and fails closed.
inline constexpr std::size_t limb_count = 128;
inline constexpr int common_exponent = -2148;

struct Integer {
    std::array<std::uint64_t, limb_count> limbs{};
    bool negative = false;
};

struct Dyadic { std::uint64_t significand; int exponent; bool negative; };

inline Dyadic decode(double value) noexcept {
    const auto bits = std::bit_cast<std::uint64_t>(value);
    const auto exponent_bits = static_cast<unsigned>((bits >> 52) & 0x7ffU);
    const auto fraction = bits & ((std::uint64_t{1} << 52) - 1);
    if (exponent_bits == 0) return {fraction, -1074, (bits >> 63) != 0};
    return {(std::uint64_t{1} << 52) | fraction,
        static_cast<int>(exponent_bits) - 1023 - 52, (bits >> 63) != 0};
}

inline bool is_zero(const Integer& value) noexcept {
    for (auto limb : value.limbs) if (limb) return false;
    return true;
}

inline int compare_magnitude(const Integer& lhs, const Integer& rhs) noexcept {
    for (std::size_t i = limb_count; i-- > 0;)
        if (lhs.limbs[i] != rhs.limbs[i]) return lhs.limbs[i] < rhs.limbs[i] ? -1 : 1;
    return 0;
}

inline bool add_magnitude(Integer& lhs, const Integer& rhs) noexcept {
    std::uint64_t carry = 0;
    for (std::size_t i = 0; i < limb_count; ++i) {
        const auto first = lhs.limbs[i] + rhs.limbs[i];
        const bool carry_first = first < lhs.limbs[i];
        const auto second = first + carry;
        const bool carry_second = second < first;
        lhs.limbs[i] = second;
        carry = static_cast<std::uint64_t>(carry_first || carry_second);
    }
    return carry == 0;
}

inline void subtract_magnitude(Integer& lhs, const Integer& rhs) noexcept {
    std::uint64_t borrow = 0;
    for (std::size_t i = 0; i < limb_count; ++i) {
        const auto first = lhs.limbs[i] - rhs.limbs[i];
        const bool borrow_first = lhs.limbs[i] < rhs.limbs[i];
        const auto second = first - borrow;
        const bool borrow_second = first < borrow;
        lhs.limbs[i] = second;
        borrow = static_cast<std::uint64_t>(borrow_first || borrow_second);
    }
}

inline bool add_signed(Integer& lhs, const Integer& rhs) noexcept {
    if (is_zero(rhs)) return true;
    if (is_zero(lhs)) { lhs = rhs; return true; }
    if (lhs.negative == rhs.negative) return add_magnitude(lhs, rhs);
    const int order = compare_magnitude(lhs, rhs);
    if (order == 0) lhs = {};
    else if (order > 0) subtract_magnitude(lhs, rhs);
    else { Integer difference = rhs; subtract_magnitude(difference, lhs); lhs = difference; }
    if (is_zero(lhs)) lhs.negative = false;
    return true;
}

inline bool add_bit(Integer& target, std::size_t bit, bool negative) noexcept {
    if (bit >= limb_count * 64) return false;
    Integer term;
    term.limbs[bit / 64] = std::uint64_t{1} << (bit % 64);
    term.negative = negative;
    return add_signed(target, term);
}

inline bool add_dyadic(Integer& target, Dyadic value) noexcept {
    if (!value.significand) return true;
    const int shift = value.exponent - common_exponent;
    if (shift < 0) return false;
    for (unsigned bit = 0; bit < 53; ++bit)
        if ((value.significand >> bit) & 1U)
            if (!add_bit(target, static_cast<std::size_t>(shift) + bit, value.negative)) return false;
    return true;
}

inline bool add_product(Integer& target, Dyadic lhs, Dyadic rhs) noexcept {
    if (!lhs.significand || !rhs.significand) return true;
    const int shift = lhs.exponent + rhs.exponent - common_exponent;
    if (shift < 0) return false;
    // Multiply two at-most-53-bit significands in four 32-bit words. The
    // largest intermediate is (2^32-1)^2 + 2(2^32-1) = 2^64-1, so uint64_t
    // is sufficient. Four words cover the at-most-106-bit product.
    const std::array<std::uint32_t, 2> a{
        static_cast<std::uint32_t>(lhs.significand),
        static_cast<std::uint32_t>(lhs.significand >> 32)};
    const std::array<std::uint32_t, 2> b{
        static_cast<std::uint32_t>(rhs.significand),
        static_cast<std::uint32_t>(rhs.significand >> 32)};
    std::array<std::uint32_t, 4> product{};
    for (std::size_t i = 0; i < a.size(); ++i) {
        std::uint64_t carry = 0;
        for (std::size_t j = 0; j < b.size(); ++j) {
            const std::uint64_t value = static_cast<std::uint64_t>(a[i]) * b[j] +
                product[i + j] + carry;
            product[i + j] = static_cast<std::uint32_t>(value);
            carry = value >> 32;
        }
        std::size_t at = i + b.size();
        while (carry) {
            if (at >= product.size()) return false;
            const std::uint64_t value = static_cast<std::uint64_t>(product[at]) + carry;
            product[at++] = static_cast<std::uint32_t>(value);
            carry = value >> 32;
        }
    }
    Integer term;
    term.negative = lhs.negative != rhs.negative;
    for (std::size_t i = 0; i < product.size(); ++i) {
        if (!product[i]) continue;
        const std::size_t bit = static_cast<std::size_t>(shift) + 32 * i;
        const auto limb = bit / 64;
        const auto offset = static_cast<unsigned>(bit % 64);
        if (limb >= limb_count) return false;
        term.limbs[limb] |= static_cast<std::uint64_t>(product[i]) << offset;
        if (offset && limb + 1 < limb_count)
            term.limbs[limb + 1] |= static_cast<std::uint64_t>(product[i]) >> (64 - offset);
        else if (offset && (static_cast<std::uint64_t>(product[i]) >> (64 - offset))) return false;
    }
    return add_signed(target, term);
}

// Return the least finite binary64 no smaller than the exact nonnegative value
// magnitude * 2^common_exponent. Integer shifts inspect discarded bits, so the
// conversion is outward even below the normal range without floating estimates.
inline std::uint64_t shifted_low_bits(const Integer& value, std::size_t shift) noexcept {
    const auto limb = shift / 64;
    const auto offset = static_cast<unsigned>(shift % 64);
    if (limb >= limb_count) return 0;
    std::uint64_t result = value.limbs[limb] >> offset;
    if (offset && limb + 1 < limb_count) result |= value.limbs[limb + 1] << (64 - offset);
    return result;
}

inline bool has_bits_below(const Integer& value, std::size_t bit) noexcept {
    const auto full_limbs = bit / 64;
    for (std::size_t i = 0; i < full_limbs; ++i)
        if (value.limbs[i]) return true;
    const auto offset = static_cast<unsigned>(bit % 64);
    return offset != 0 && full_limbs < limb_count &&
        (value.limbs[full_limbs] & ((std::uint64_t{1} << offset) - 1)) != 0;
}

inline std::optional<double> outward_binary64(const Integer& magnitude) noexcept {
    if (magnitude.negative) return std::nullopt;
    std::size_t highest = limb_count * 64;
    for (std::size_t limb = limb_count; limb-- > 0;) {
        if (!magnitude.limbs[limb]) continue;
        highest = limb * 64 + (63U - static_cast<unsigned>(std::countl_zero(magnitude.limbs[limb])));
        break;
    }
    if (highest == limb_count * 64) return 0.0;

    const int exact_exponent = static_cast<int>(highest) + common_exponent;
    if (exact_exponent < -1074) return std::numeric_limits<double>::denorm_min();
    if (exact_exponent < -1022) {
        constexpr std::size_t subnormal_shift = 1074;
        auto units = shifted_low_bits(magnitude, subnormal_shift);
        if (has_bits_below(magnitude, subnormal_shift)) ++units;
        if (units == (std::uint64_t{1} << 52))
            return std::bit_cast<double>(std::uint64_t{1} << 52); // smallest normal
        return std::bit_cast<double>(units);
    }
    const auto shift = highest - 52;
    auto significand = shifted_low_bits(magnitude, shift);
    int exponent = exact_exponent;
    if (has_bits_below(magnitude, shift) && ++significand == (std::uint64_t{1} << 53)) {
        significand >>= 1;
        ++exponent;
    }
    if (exponent > 1023) return std::nullopt;
    const auto exponent_bits = static_cast<std::uint64_t>(exponent + 1023);
    const auto fraction = significand - (std::uint64_t{1} << 52);
    return std::bit_cast<double>((exponent_bits << 52) | fraction);
}

} // namespace exact_detail
} // namespace csl::geometry::detail
