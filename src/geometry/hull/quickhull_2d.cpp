#include <csl/geometry/quickhull_2d.hpp>

// Reuse only the private exact dyadic integer arithmetic. The hull algorithm
// never constructs a membership LP or invokes an LP workspace.
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <numeric>
#include <utility>

namespace csl::geometry {
namespace {

using detail::exact_detail::Integer;

Integer orientation(const Vector& a, const Vector& b, const Vector& c) {
    using detail::exact_detail::add_product;
    using detail::exact_detail::decode;
    Integer value;
    const auto term = [&](double x, double y, bool subtract) {
        auto first = decode(x);
        if (subtract) first.negative = !first.negative;
        // Six binary64 products fit in the private 8192-bit exact accumulator.
        const bool accepted = add_product(value, first, decode(y));
        assert(accepted);
        static_cast<void>(accepted);
    };
    // (b-a) x (c-a), expanded to avoid rounded coordinate differences.
    term(b[0], c[1], false);
    term(b[1], a[0], false);
    term(a[1], c[0], false);
    term(b[0], a[1], true);
    term(a[0], c[1], true);
    term(b[1], c[0], true);
    return value;
}

int orientation_sign(const Integer& value) {
    return detail::exact_detail::is_zero(value) ? 0 : (value.negative ? -1 : 1);
}

bool coordinate_less(const std::span<const Vector> points, std::size_t a, std::size_t b) {
    if (points[a][0] != points[b][0]) return points[a][0] < points[b][0];
    if (points[a][1] != points[b][1]) return points[a][1] < points[b][1];
    return a < b;
}

void append_chain(std::span<const Vector> points, std::size_t left, std::size_t right,
                  int side, const std::vector<std::size_t>& candidates,
                  std::vector<std::size_t>& vertices) {
    if (candidates.empty()) return;
    std::size_t farthest = candidates.front();
    Integer greatest = orientation(points[left], points[right], points[farthest]);
    for (const auto candidate : candidates) {
        Integer distance = orientation(points[left], points[right], points[candidate]);
        if (detail::exact_detail::compare_magnitude(distance, greatest) > 0) {
            greatest = std::move(distance);
            farthest = candidate;
        }
        // Equal-area ties keep the first candidate in lexicographic order.
    }

    std::vector<std::size_t> before;
    std::vector<std::size_t> after;
    before.reserve(candidates.size());
    after.reserve(candidates.size());
    for (const auto candidate : candidates) {
        if (candidate == farthest) continue;
        const int first = orientation_sign(orientation(points[left], points[farthest], points[candidate]));
        if (first == side) {
            before.push_back(candidate);
        } else if (orientation_sign(orientation(points[farthest], points[right], points[candidate])) == side) {
            after.push_back(candidate);
        }
    }
    append_chain(points, left, farthest, side, before, vertices);
    vertices.push_back(farthest);
    append_chain(points, farthest, right, side, after, vertices);
}

} // namespace

QuickHull2DResult quickhull_2d(std::span<const Vector> points) {
    for (const auto& point : points) {
        if (point.size() != 2)
            return Diagnostics{{DiagnosticCode::invalid_input, "points",
                "QuickHull2D requires exactly two coordinates per point"}};
        if (!std::isfinite(point[0]) || !std::isfinite(point[1]))
            return Diagnostics{{DiagnosticCode::invalid_input, "points",
                "QuickHull2D requires finite coordinates"}};
    }

    QuickHull2D result;
    if (points.empty()) return result;
    std::vector<std::size_t> unique(points.size());
    std::iota(unique.begin(), unique.end(), std::size_t{0});
    std::sort(unique.begin(), unique.end(),
        [&](std::size_t a, std::size_t b) { return coordinate_less(points, a, b); });
    unique.erase(std::unique(unique.begin(), unique.end(),
        [&](std::size_t a, std::size_t b) { return points[a] == points[b]; }), unique.end());

    const auto left = unique.front();
    result.vertex_indices.push_back(left);
    if (unique.size() == 1) return result;
    const auto right = unique.back();
    std::vector<std::size_t> below;
    std::vector<std::size_t> above;
    for (const auto index : unique) {
        if (index == left || index == right) continue;
        const int side = orientation_sign(orientation(points[left], points[right], points[index]));
        if (side < 0) below.push_back(index);
        else if (side > 0) above.push_back(index);
    }
    append_chain(points, left, right, -1, below, result.vertex_indices);
    result.vertex_indices.push_back(right);
    append_chain(points, right, left, -1, above, result.vertex_indices);
    return result;
}

} // namespace csl::geometry
