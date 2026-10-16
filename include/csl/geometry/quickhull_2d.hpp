#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>

#include <cstddef>
#include <span>
#include <variant>
#include <vector>

namespace csl::geometry {

struct QuickHull2D {
    // Original input positions, starting at the lexicographically smallest
    // vertex and continuing counterclockwise. No repeated closing vertex.
    std::vector<std::size_t> vertex_indices;
};

using QuickHull2DResult = std::variant<QuickHull2D, Diagnostics>;

// A geometric, LP-independent 2D hull adapter. Input is borrowed only for the
// call. Every nonempty point must have exactly two finite coordinates; an empty
// cloud has an empty hull. Coincident points use the lowest original index.
// Collinear edge/interior points are omitted; a collinear cloud keeps only its
// endpoints. Orientation is exact for the supplied binary64 coordinates.
QuickHull2DResult quickhull_2d(std::span<const Vector> points);

} // namespace csl::geometry
