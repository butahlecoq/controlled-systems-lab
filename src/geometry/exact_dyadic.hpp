#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>

namespace csl::geometry::detail {
namespace exact_detail {

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

} // namespace exact_detail
} // namespace csl::geometry::detail
