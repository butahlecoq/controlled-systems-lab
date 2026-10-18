#pragma once

#include "exact_h_interval.hpp"
#include <array>

namespace csl::geometry::detail {

// Certify exact equality for a finite V representation of an axis-aligned
// planar box. This deliberately declines general polygons: checking the four
// exact corners and every returned point is a complete proof for this shape.
inline std::variant<double, std::string> certify_h_rectangle(
        const sets::HRepresentation& h, const sets::VRepresentation& v) {
    if (h.inequalities.cols() != 2 || h.equalities.cols() != 2 ||
        v.vertices.cols() != 2 || v.rays.cols() != 2 || v.rays.rows() != 0)
        return std::string{"Global rectangle check requires planar H and finite V."};

    std::array<std::optional<RationalEndpoint>, 2> lower, upper;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        const double x = h.inequalities(row, 0);
        const double y = h.inequalities(row, 1);
        const double bound = h.upper_bounds[row];
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(bound))
            return std::string{"Nonfinite H inequality cannot be certified."};
        if (x == 0.0 && y == 0.0) {
            if (bound < 0.0) return std::string{"Exact H rectangle is empty."};
            continue;
        }
        if (x != 0.0 && y != 0.0)
            return std::string{"H rows are not axis-aligned; rectangle certificate unavailable."};
        const std::size_t axis = x == 0.0 ? 1 : 0;
        const double coefficient = axis == 0 ? x : y;
        const auto value = endpoint(coefficient, bound);
        auto& target = coefficient < 0.0 ? lower[axis] : upper[axis];
        if (!target) target = value;
        else {
            const auto order = compare(*target, value);
            if (!order) return std::string{"Exact H endpoint comparison exceeded checked arithmetic range."};
            if ((coefficient < 0.0 && *order < 0) ||
                (coefficient > 0.0 && *order > 0)) target = value;
        }
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        if (h.equalities(row, 0) != 0.0 || h.equalities(row, 1) != 0.0 ||
            h.equality_values[row] != 0.0)
            return std::string{"Nontrivial H equalities are outside the rectangle certificate."};
    }
    for (std::size_t axis = 0; axis < 2; ++axis) {
        if (!lower[axis] || !upper[axis])
            return std::string{"Exact H rectangle is unbounded."};
        const auto order = compare(*lower[axis], *upper[axis]);
        if (!order) return std::string{"Exact H endpoint comparison exceeded checked arithmetic range."};
        if (*order > 0) return std::string{"Exact H rectangle is empty."};
    }
    if (v.vertices.rows() == 0)
        return std::string{"Converted V set omits the nonempty exact H rectangle."};

    std::array<std::array<bool, 2>, 2> corner_seen{};
    for (std::size_t row = 0; row < v.vertices.rows(); ++row) {
        std::array<double, 2> point{v.vertices(row, 0), v.vertices(row, 1)};
        if (!std::isfinite(point[0]) || !std::isfinite(point[1]))
            return std::string{"Nonfinite converted V vertex cannot be certified."};
        std::array<std::array<bool, 2>, 2> endpoint_matches{};
        for (std::size_t axis = 0; axis < 2; ++axis) {
            const RationalEndpoint represented{point[axis], 1.0};
            const auto low_order = compare(represented, *lower[axis]);
            const auto high_order = compare(represented, *upper[axis]);
            if (!low_order || !high_order)
                return std::string{"Exact V/H comparison exceeded checked arithmetic range."};
            if (*low_order < 0 || *high_order > 0)
                return std::string{"Converted V vertex lies outside the exact H rectangle."};
            endpoint_matches[axis][0] = *low_order == 0;
            endpoint_matches[axis][1] = *high_order == 0;
        }
        for (std::size_t x = 0; x < 2; ++x)
            for (std::size_t y = 0; y < 2; ++y)
                if (endpoint_matches[0][x] && endpoint_matches[1][y]) corner_seen[x][y] = true;
    }
    for (const auto& row : corner_seen)
        for (const bool seen : row)
            if (!seen) return std::string{"Converted V set omits an exact H rectangle corner."};
    return 0.0;
}

} // namespace csl::geometry::detail
