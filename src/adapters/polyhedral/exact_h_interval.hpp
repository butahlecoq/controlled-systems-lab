#pragma once

#include <csl/sets/data.hpp>
#include "../../geometry/exact_dyadic.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <string>
#include <variant>

namespace csl::adapters::polyhedral::detail {
namespace dyadic = csl::geometry::detail::exact_detail;

// This checks the original ambient-one H rows, independently of the LP and
// floating-point equality reduction that produced the converted vertices.
struct RationalEndpoint { double numerator; double positive_denominator; };

inline std::optional<int> compare(const RationalEndpoint& lhs, const RationalEndpoint& rhs) {
    dyadic::Integer difference;
    if (!dyadic::add_product(difference, dyadic::decode(lhs.numerator),
            dyadic::decode(rhs.positive_denominator))) return std::nullopt;
    auto opposite = dyadic::decode(rhs.numerator);
    opposite.negative = !opposite.negative;
    if (!dyadic::add_product(difference, opposite,
            dyadic::decode(lhs.positive_denominator))) return std::nullopt;
    if (dyadic::is_zero(difference)) return 0;
    return difference.negative ? -1 : 1;
}

inline RationalEndpoint endpoint(double coefficient, double bound) {
    if (coefficient < 0) return {-bound, -coefficient};
    return {bound, coefficient};
}

inline std::variant<double, std::string> outward_endpoint_error(
        const RationalEndpoint& exact, double represented) {
    dyadic::Integer discrepancy;
    if (!dyadic::add_dyadic(discrepancy, dyadic::decode(exact.numerator)))
        return std::string{"Exact H endpoint exceeds checked arithmetic range."};
    auto negated = dyadic::decode(represented);
    negated.negative = !negated.negative;
    if (!dyadic::add_product(discrepancy, negated,
            dyadic::decode(exact.positive_denominator)))
        return std::string{"Exact H endpoint discrepancy exceeds checked arithmetic range."};
    discrepancy.negative = false;
    if (dyadic::is_zero(discrepancy)) return 0.0;

    constexpr std::uint64_t largest_finite = 0x7fefffffffffffffULL;
    const auto sufficient = [&](std::uint64_t bits) {
        dyadic::Integer product;
        if (!dyadic::add_product(product, dyadic::decode(std::bit_cast<double>(bits)),
                dyadic::decode(exact.positive_denominator))) return false;
        return dyadic::compare_magnitude(product, discrepancy) >= 0;
    };
    if (!sufficient(largest_finite))
        return std::string{"Exact H endpoint discrepancy has no finite binary64 outward bound."};
    std::uint64_t lower = 0, upper = largest_finite;
    while (lower < upper) {
        const auto middle = lower + (upper - lower) / 2;
        if (sufficient(middle)) upper = middle;
        else lower = middle + 1;
    }
    return std::bit_cast<double>(lower);
}

inline std::variant<double, std::string> certify_h_interval(
        const sets::HRepresentation& h, const sets::VRepresentation& v) {
    if (h.inequalities.cols() != 1 || h.equalities.cols() != 1 ||
        v.vertices.cols() != 1 || v.rays.cols() != 1 || v.rays.rows() != 0)
        return std::string{"Global interval check requires ambient-one H and finite V."};

    std::optional<RationalEndpoint> lower, upper;
    bool empty = false;
    const auto accept = [&](double coefficient, double bound, bool equality) {
        if (!std::isfinite(coefficient) || !std::isfinite(bound)) return false;
        if (coefficient == 0) {
            if (equality ? bound != 0 : bound < 0) empty = true;
            return true;
        }
        const auto value = endpoint(coefficient, bound);
        if (coefficient < 0 || equality) {
            if (lower) {
                const auto order = compare(*lower, value);
                if (!order) return false;
                if (*order < 0) lower = value;
            } else lower = value;
        }
        if (coefficient > 0 || equality) {
            if (upper) {
                const auto order = compare(*upper, value);
                if (!order) return false;
                if (*order > 0) upper = value;
            } else upper = value;
        }
        return true;
    };
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row)
        if (!accept(h.inequalities(row, 0), h.upper_bounds[row], false))
            return std::string{"Nonfinite H inequality cannot be certified."};
    for (std::size_t row = 0; row < h.equalities.rows(); ++row)
        if (!accept(h.equalities(row, 0), h.equality_values[row], true))
            return std::string{"Nonfinite H equality cannot be certified."};
    if (lower && upper) {
        const auto order = compare(*lower, *upper);
        if (!order) return std::string{"Exact H endpoint comparison exceeded checked arithmetic range."};
        if (*order > 0) empty = true;
    }
    if (empty) {
        if (v.vertices.rows() == 0) return 0.0;
        return std::string{"Converted V set is nonempty while exact H set is empty."};
    }
    if (!lower || !upper)
        return std::string{"Exact H set is unbounded; no finite V coverage certificate exists."};
    if (v.vertices.rows() == 0)
        return std::string{"Converted V set omits a nonempty exact H interval."};
    double v_lower = std::numeric_limits<double>::infinity();
    double v_upper = -std::numeric_limits<double>::infinity();
    for (std::size_t row = 0; row < v.vertices.rows(); ++row) {
        const double value = v.vertices(row, 0);
        if (!std::isfinite(value))
            return std::string{"Nonfinite converted V vertex cannot be certified."};
        v_lower = std::min(v_lower, value);
        v_upper = std::max(v_upper, value);
    }
    auto low_error = outward_endpoint_error(*lower, v_lower);
    if (const auto* error = std::get_if<std::string>(&low_error)) return *error;
    auto high_error = outward_endpoint_error(*upper, v_upper);
    if (const auto* error = std::get_if<std::string>(&high_error)) return *error;
    return std::max(std::get<double>(low_error), std::get<double>(high_error));
}
} // namespace csl::adapters::polyhedral::detail
