#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/values.hpp>

#include <cstddef>
#include <chrono>
#include <optional>
#include <span>
#include <stop_token>
#include <string>
#include <variant>
#include <vector>

namespace csl::geometry {

struct QuickHull2D {
    // Original input positions, starting at the lexicographically smallest
    // vertex and continuing counterclockwise. No repeated closing vertex.
    std::vector<std::size_t> vertex_indices;
};

using QuickHull2DResult = std::variant<QuickHull2D, Diagnostics>;

struct QuickHullControl {
    std::stop_token cancellation;
    std::optional<std::chrono::steady_clock::time_point> deadline;
};
struct QuickHullStopped { std::string reason; };
using ControlledQuickHull2DResult = std::variant<QuickHull2D, Diagnostics, QuickHullStopped>;

// A geometric, LP-independent 2D hull adapter. Input is borrowed only for the
// call. Every nonempty point must have exactly two finite coordinates; an empty
// cloud has an empty hull. Coincident points use the lowest original index.
// Collinear edge/interior points are omitted; a collinear cloud keeps only its
// endpoints. Orientation is exact for the supplied binary64 coordinates.
QuickHull2DResult quickhull_2d(std::span<const Vector> points);
// Same source algorithm and ordering, with cooperative checks at comparison
// and candidate-scan boundaries for operation callers with execution controls.
ControlledQuickHull2DResult quickhull_2d_controlled(std::span<const Vector> points,
    QuickHullControl control);

} // namespace csl::geometry
