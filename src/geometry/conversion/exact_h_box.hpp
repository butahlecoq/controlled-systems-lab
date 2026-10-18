#pragma once

#include "exact_h_interval.hpp"
#include <limits>
#include <vector>

namespace csl::geometry::detail {

// A box certificate is complete only when every returned V point is inside
// the exact stored-dyadic H box and every box corner is present in V. Limit
// corner enumeration before allocating or shifting, and decline larger boxes.
inline constexpr std::size_t maximum_certified_box_corners = 4096;

inline std::variant<double, std::string> certify_h_box(
        const sets::HRepresentation& h, const sets::VRepresentation& v) {
    const std::size_t dimension = h.inequalities.cols();
    if (dimension < 2 || dimension >= std::numeric_limits<std::size_t>::digits ||
        (std::size_t{1} << dimension) > maximum_certified_box_corners ||
        h.equalities.cols() != dimension || v.vertices.cols() != dimension ||
        v.rays.cols() != dimension || v.rays.rows() != 0)
        return std::string{"Global box check requires finite H and V in a supported dimension (2 through 12)."};

    std::vector<std::optional<RationalEndpoint>> lower(dimension), upper(dimension);
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        std::size_t axis = dimension;
        double coefficient = 0.0;
        for (std::size_t col = 0; col < dimension; ++col) {
            const double value = h.inequalities(row, col);
            if (!std::isfinite(value))
                return std::string{"Nonfinite H inequality cannot be certified."};
            if (value == 0.0) continue;
            if (axis != dimension)
                return std::string{"H rows are not axis-aligned; box certificate unavailable."};
            axis = col;
            coefficient = value;
        }
        const double bound = h.upper_bounds[row];
        if (!std::isfinite(bound))
            return std::string{"Nonfinite H inequality cannot be certified."};
        if (axis == dimension) {
            if (bound < 0.0) return std::string{"Exact H box is empty."};
            continue;
        }
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
        for (std::size_t col = 0; col < dimension; ++col)
            if (h.equalities(row, col) != 0.0)
                return std::string{"Nontrivial H equalities are outside the box certificate."};
        if (h.equality_values[row] != 0.0)
            return std::string{"Nontrivial H equalities are outside the box certificate."};
    }
    std::vector<bool> degenerate(dimension, false);
    for (std::size_t axis = 0; axis < dimension; ++axis) {
        if (!lower[axis] || !upper[axis])
            return std::string{"Exact H box is unbounded."};
        const auto order = compare(*lower[axis], *upper[axis]);
        if (!order) return std::string{"Exact H endpoint comparison exceeded checked arithmetic range."};
        if (*order > 0) return std::string{"Exact H box is empty."};
        degenerate[axis] = *order == 0;
    }
    if (v.vertices.rows() == 0)
        return std::string{"Converted V set omits the nonempty exact H box."};

    const std::size_t corner_count = std::size_t{1} << dimension;
    std::vector<bool> corner_seen(corner_count, false);
    std::vector<bool> corner_expanded(corner_count, false);
    for (std::size_t row = 0; row < v.vertices.rows(); ++row) {
        std::size_t corner = 0;
        std::vector<std::size_t> degenerate_axes;
        bool is_corner = true;
        for (std::size_t axis = 0; axis < dimension; ++axis) {
            const double point = v.vertices(row, axis);
            if (!std::isfinite(point))
                return std::string{"Nonfinite converted V vertex cannot be certified."};
            const RationalEndpoint represented{point, 1.0};
            const auto low_order = compare(represented, *lower[axis]);
            const auto high_order = compare(represented, *upper[axis]);
            if (!low_order || !high_order)
                return std::string{"Exact V/H comparison exceeded checked arithmetic range."};
            if (*low_order < 0 || *high_order > 0)
                return std::string{"Converted V vertex lies outside the exact H box."};
            if (*high_order == 0) corner |= std::size_t{1} << axis;
            if (degenerate[axis]) degenerate_axes.push_back(axis);
            else if (*low_order != 0 && *high_order != 0)
                is_corner = false;
        }
        if (!is_corner) continue;
        if (corner_expanded[corner]) continue;
        corner_expanded[corner] = true;
        // A degenerate coordinate is both its low and high endpoint. Expand
        // its bit choices so all distinct corner masks are marked exactly.
        const std::size_t expansions = std::size_t{1} << degenerate_axes.size();
        for (std::size_t choice = 0; choice < expansions; ++choice) {
            std::size_t mask = corner;
            for (std::size_t bit = 0; bit < degenerate_axes.size(); ++bit) {
                const auto axis = degenerate_axes[bit];
                if ((choice & (std::size_t{1} << bit)) == 0)
                    mask &= ~(std::size_t{1} << axis);
                else mask |= std::size_t{1} << axis;
            }
            corner_seen[mask] = true;
        }
    }
    if (std::find(corner_seen.begin(), corner_seen.end(), false) != corner_seen.end())
        return std::string{"Converted V set omits an exact H box corner."};
    return 0.0;
}

} // namespace csl::geometry::detail
