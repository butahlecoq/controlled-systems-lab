#pragma once

#include <csl/core/values.hpp>
#include "exact_dyadic.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::geometry::detail {
inline bool independent_directions(const Matrix &rows) {
    using namespace exact_detail;
    if (rows.rows == 0 || rows.rows != rows.cols ||
        rows.rows > std::numeric_limits<std::size_t>::max() / rows.cols ||
        rows.values.size() != rows.rows * rows.cols ||
        !std::all_of(rows.values.begin(), rows.values.end(),
                     [](double value) { return std::isfinite(value); }))
        return false;
    if (rows.rows == 2) {
        Integer determinant;
        if (!add_product(determinant, decode(rows.values[0]), decode(rows.values[3])))
            return false;
        auto negative = decode(rows.values[1]);
        negative.negative = !negative.negative;
        return add_product(determinant, negative, decode(rows.values[2])) && !is_zero(determinant);
    }
    // Elimination only proposes a binary64 inverse. Admission below proves
    // nonsingularity exactly, independently of pivot growth or working precision.
    const auto n = rows.rows;
    Vector work = rows.values;
    Vector inverse(n * n, 0.0);
    for (std::size_t row = 0; row < n; ++row) {
        double scale = 0.0;
        for (std::size_t column = 0; column < n; ++column)
            scale = std::max(scale, std::abs(work[row * n + column]));
        if (scale == 0.0)
            return false;
        for (std::size_t column = 0; column < n; ++column)
            work[row * n + column] /= scale;
        inverse[row * n + row] = 1.0 / scale;
    }
    for (std::size_t pivot = 0; pivot < n; ++pivot) {
        std::size_t best = pivot;
        for (std::size_t row = pivot + 1; row < n; ++row)
            if (std::abs(work[row * n + pivot]) > std::abs(work[best * n + pivot]))
                best = row;
        const auto divisor = work[best * n + pivot];
        if (divisor == 0.0 || !std::isfinite(divisor))
            return false;
        if (best != pivot)
            for (std::size_t column = 0; column < n; ++column) {
                std::swap(work[pivot * n + column], work[best * n + column]);
                std::swap(inverse[pivot * n + column], inverse[best * n + column]);
            }
        for (std::size_t column = 0; column < n; ++column) {
            work[pivot * n + column] /= divisor;
            inverse[pivot * n + column] /= divisor;
        }
        for (std::size_t row = 0; row < n; ++row) {
            if (row == pivot)
                continue;
            const auto multiplier = work[row * n + pivot];
            for (std::size_t column = 0; column < n; ++column) {
                work[row * n + column] -= multiplier * work[pivot * n + column];
                inverse[row * n + column] -= multiplier * inverse[pivot * n + column];
            }
        }
    }
    if (!std::all_of(inverse.begin(), inverse.end(),
                     [](double value) { return std::isfinite(value); }))
        return false;

    // ||I - B A||_infinity < 1 implies B A, hence square A, is invertible
    // (Neumann series). Each residual and absolute row sum uses exact dyadics
    // of the original A and candidate B, with no rounded norm comparison.
    Integer one;
    if (!add_dyadic(one, decode(1.0)))
        return false;
    for (std::size_t row = 0; row < n; ++row) {
        Integer row_sum;
        for (std::size_t column = 0; column < n; ++column) {
            Integer residual;
            if (row == column && !add_dyadic(residual, decode(1.0)))
                return false;
            for (std::size_t inner = 0; inner < n; ++inner) {
                auto negative = decode(inverse[row * n + inner]);
                negative.negative = !negative.negative;
                if (!add_product(residual, negative, decode(rows.values[inner * n + column])))
                    return false;
            }
            if (!add_magnitude(row_sum, residual))
                return false;
            if (compare_magnitude(row_sum, one) >= 0)
                return false;
        }
    }
    return true;
}
} // namespace csl::geometry::detail
