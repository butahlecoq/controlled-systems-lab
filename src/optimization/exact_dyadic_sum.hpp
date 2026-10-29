#pragma once

#include <array>
#include <bit>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace csl::optimization::detail {

static_assert(std::numeric_limits<double>::is_iec559 &&
    std::numeric_limits<double>::digits == 53 &&
    std::numeric_limits<double>::max_exponent == 1024 &&
    std::numeric_limits<double>::min_exponent == -1021,
    "Exact LP witness checks require IEEE-754 binary64 double");

class ExactDyadicSum {
    class Magnitude {
        std::vector<std::uint32_t> words_;
    public:
        void add_word(std::size_t index, std::uint32_t value) {
            std::uint64_t carry = value;
            while (carry) {
                if (index >= words_.size()) words_.resize(index + 1, 0);
                const auto sum = static_cast<std::uint64_t>(words_[index]) + carry;
                words_[index] = static_cast<std::uint32_t>(sum);
                carry = sum >> 32;
                ++index;
            }
        }

        int compare(const Magnitude& other) const noexcept {
            auto left = words_.size();
            auto right = other.words_.size();
            while (left && words_[left - 1] == 0) --left;
            while (right && other.words_[right - 1] == 0) --right;
            if (left != right) return left < right ? -1 : 1;
            while (left) {
                --left;
                if (words_[left] != other.words_[left])
                    return words_[left] < other.words_[left] ? -1 : 1;
            }
            return 0;
        }
    };

    struct Parts {
        bool negative;
        std::uint64_t significand;
        int exponent;
    };

    static Parts parts(double value) noexcept {
        const auto bits = std::bit_cast<std::uint64_t>(value);
        const auto exponent = static_cast<unsigned>((bits >> 52) & 0x7ffU);
        const auto fraction = bits & ((std::uint64_t{1} << 52) - 1);
        if (exponent == 0) return {(bits >> 63) != 0, fraction, -1074};
        return {(bits >> 63) != 0, (std::uint64_t{1} << 52) | fraction,
            static_cast<int>(exponent) - 1023 - 52};
    }

    static std::array<std::uint32_t, 4> multiply(std::uint64_t left,
            std::uint64_t right) noexcept {
        const std::array<std::uint32_t, 2> a{
            static_cast<std::uint32_t>(left), static_cast<std::uint32_t>(left >> 32)};
        const std::array<std::uint32_t, 2> b{
            static_cast<std::uint32_t>(right), static_cast<std::uint32_t>(right >> 32)};
        std::array<std::uint32_t, 4> product{};
        for (std::size_t i = 0; i < 2; ++i) {
            std::uint64_t carry = 0;
            for (std::size_t j = 0; j < 2; ++j) {
                const auto index = i + j;
                const auto value = static_cast<std::uint64_t>(a[i]) * b[j] + product[index] + carry;
                product[index] = static_cast<std::uint32_t>(value);
                carry = value >> 32;
            }
            auto index = i + 2;
            while (carry && index < product.size()) {
                const auto value = static_cast<std::uint64_t>(product[index]) + carry;
                product[index++] = static_cast<std::uint32_t>(value);
                carry = value >> 32;
            }
        }
        return product;
    }

    static constexpr int binary64_product_common_exponent = -2148;
    Magnitude positive_;
    Magnitude negative_;

public:
    void add(double value, bool negate = false) {
        add_product(value, 1.0, negate);
    }

    void add_product(double left, double right, bool negate = false) {
        const auto a = parts(left);
        const auto b = parts(right);
        if (!a.significand || !b.significand) return;
        const auto product = multiply(a.significand, b.significand);
        const auto shift = static_cast<std::size_t>(
            a.exponent + b.exponent - binary64_product_common_exponent);
        const auto word = shift / 32;
        const auto bit = static_cast<unsigned>(shift % 32);
        auto& magnitude = ((a.negative != b.negative) != negate) ? negative_ : positive_;
        for (std::size_t i = 0; i < product.size(); ++i) {
            if (!product[i]) continue;
            const auto shifted = static_cast<std::uint64_t>(product[i]) << bit;
            magnitude.add_word(word + i, static_cast<std::uint32_t>(shifted));
            magnitude.add_word(word + i + 1, static_cast<std::uint32_t>(shifted >> 32));
        }
    }

    bool zero() const noexcept { return positive_.compare(negative_) == 0; }
    bool positive() const noexcept { return positive_.compare(negative_) > 0; }
    bool negative() const noexcept { return positive_.compare(negative_) < 0; }
};

} // namespace csl::optimization::detail
