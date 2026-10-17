#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/geometry/quickhull_2d.hpp>

#include "exact_dyadic.hpp"

#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string_view>

namespace csl::geometry {
namespace {
using detail::exact_detail::Integer;
using Clock = std::chrono::steady_clock;

bool budget_expired(const Clock::time_point start, const std::chrono::milliseconds budget) {
    const auto elapsed_ms = std::chrono::duration<long double, std::milli>(Clock::now() - start);
    return elapsed_ms.count() >= static_cast<long double>(budget.count());
}

void append_u64(std::vector<std::byte>& bytes, std::uint64_t value) {
    for (unsigned shift = 0; shift < 64; shift += 8)
        bytes.push_back(static_cast<std::byte>((value >> shift) & 0xffU));
}

// The six expanded products avoid rounded binary64 subtraction. This
// arithmetic primitive is shared; the containment oracle is independent of
// QuickHull's endpoint, side, farthest-point, and recursive hull algorithm.
bool orientation(const Vector& a, const Vector& b, const Vector& c, int& sign) {
    Integer value;
    const auto term = [&](double x, double y, bool negative) {
        auto left = detail::exact_detail::decode(x);
        if (negative) left.negative = !left.negative;
        return detail::exact_detail::add_product(value, left, detail::exact_detail::decode(y));
    };
    if (!term(b[0], c[1], false) || !term(b[1], a[0], false) ||
        !term(a[1], c[0], false) || !term(b[0], a[1], true) ||
        !term(a[0], c[1], true) || !term(b[1], c[0], true)) return false;
    sign = detail::exact_detail::is_zero(value) ? 0 : (value.negative ? -1 : 1);
    return true;
}

bool on_segment(const Vector& point, const Vector& a, const Vector& b, bool& certain) {
    int turn = 0;
    if (!orientation(a, b, point, turn)) { certain = false; return false; }
    return turn == 0 && point[0] >= std::min(a[0], b[0]) &&
        point[0] <= std::max(a[0], b[0]) &&
        point[1] >= std::min(a[1], b[1]) && point[1] <= std::max(a[1], b[1]);
}

bool in_triangle(const Vector& point, const Vector& a, const Vector& b,
                 const Vector& c, bool& certain) {
    int ab = 0, bc = 0, ca = 0, area = 0;
    if (!orientation(a, b, c, area) || !orientation(a, b, point, ab) ||
        !orientation(b, c, point, bc) || !orientation(c, a, point, ca)) {
        certain = false; return false;
    }
    if (area == 0) return false; // pairs handle degenerate triples
    return area > 0 ? (ab >= 0 && bc >= 0 && ca >= 0) :
                      (ab <= 0 && bc <= 0 && ca <= 0);
}

bool covered(const Vector& point, std::span<const Vector> input,
             const std::vector<std::size_t>& indices, bool& certain,
             const Clock::time_point start, const std::chrono::milliseconds budget,
             bool& timed_out) {
    for (std::size_t i = 0; i < indices.size(); ++i) {
        if (budget_expired(start, budget)) { timed_out = true; return false; }
        const auto& a = input[indices[i]];
        if (point == a) return true;
        for (std::size_t j = i + 1; j < indices.size(); ++j) {
            if (on_segment(point, a, input[indices[j]], certain)) return true;
            if (!certain) return false;
            for (std::size_t k = j + 1; k < indices.size(); ++k) {
                if (budget_expired(start, budget)) { timed_out = true; return false; }
                if (in_triangle(point, a, input[indices[j]], input[indices[k]], certain))
                    return true;
                if (!certain) return false;
            }
        }
    }
    return false;
}
} // namespace

HullInputDigestResult digest_hull_input(std::span<const Vector> points) {
    try {
        constexpr std::string_view tag = "csl.hull-input/binary64-le/1";
        if (points.size() > std::numeric_limits<std::uint64_t>::max())
            return std::string{"Point count exceeds manifest capacity"};
        std::vector<std::byte> bytes;
        bytes.reserve(tag.size() + 8);
        for (const char ch : tag) bytes.push_back(static_cast<std::byte>(ch));
        append_u64(bytes, static_cast<std::uint64_t>(points.size()));
        for (const auto& point : points) {
            if (point.size() > std::numeric_limits<std::uint64_t>::max())
                return std::string{"Dimension exceeds manifest capacity"};
            append_u64(bytes, static_cast<std::uint64_t>(point.size()));
            for (const double coordinate : point) {
                if (!std::isfinite(coordinate)) return std::string{"Nonfinite input coordinate"};
                append_u64(bytes, std::bit_cast<std::uint64_t>(coordinate));
            }
        }
        auto content = problem::snapshot_content(bytes);
        if (const auto* owned = std::get_if<problem::ResolvedContent>(&content))
            return owned->digest();
        return std::string{"Manifest digest unavailable"};
    } catch (const std::bad_alloc&) {
        return std::string{"Manifest allocation failed"};
    }
}

HullCheckRecord check_source_index_hull(std::span<const Vector> input,
    const SourceIndexHull& output, HullCheckBudget budget) {
    const auto start = Clock::now();
    HullCheckRecord record;
    record.budget = budget;
    const auto finish = [&]() {
        record.elapsed = Clock::now() - start;
        return record;
    };
    const auto check_budget = [&]() -> bool {
        if (budget_expired(start, budget.wall)) {
            record.reason = "checker timeout";
            return true;
        }
        return false;
    };
    try {
        if (budget.wall <= std::chrono::milliseconds::zero()) {
            record.reason = "checker timeout"; return finish();
        }
        if (input.size() > budget.max_points || output.indices.size() > budget.max_points) {
            record.reason = "checker point capacity exceeded"; return finish();
        }
        for (const auto& point : input) {
            if (point.size() != 2) { record.reason = "unsupported dimension"; return finish(); }
            if (!std::isfinite(point[0]) || !std::isfinite(point[1])) {
                record.reason = "nonfinite input; exact evidence unavailable"; return finish();
            }
        }
        if (check_budget()) return finish();
        const auto digest = digest_hull_input(input);
        if (const auto* failure = std::get_if<std::string>(&digest)) {
            record.reason = *failure; return finish();
        }
        record.input_digest = std::get<HullInputDigest>(digest);
        if (check_budget()) return finish();
        if (std::get<HullInputDigest>(digest) != output.input_digest) {
            record.status = HullCheckStatus::incorrect;
            record.reason = "output input digest does not match the exact ordered input manifest";
            return finish();
        }
        std::vector<bool> seen(input.size());
        for (const auto index : output.indices) {
            if (check_budget()) return finish();
            if (index >= input.size() || seen[index]) {
                record.status = HullCheckStatus::incorrect;
                record.reason = index >= input.size() ? "source index out of range" : "duplicate source index";
                record.counterexample_index = index;
                return finish();
            }
            seen[index] = true;
        }
        for (std::size_t i = 0; i < input.size(); ++i) {
            bool certain = true, timed_out = false;
            if (!covered(input[i], input, output.indices, certain, start, budget.wall, timed_out)) {
                if (timed_out) record.reason = "checker timeout";
                else if (!certain) record.reason = "exact arithmetic capacity exceeded";
                else if (budget_expired(start, budget.wall)) record.reason = "checker timeout";
                else {
                    record.status = HullCheckStatus::incorrect;
                    record.reason = "input point lies outside reported convex hull";
                    record.counterexample_index = i;
                }
                return finish();
            }
        }
        if (check_budget()) return finish();
        record.status = HullCheckStatus::verified;
        record.reason = "every source point is in the exact convex hull of reported source points";
        return finish();
    } catch (const std::exception& failure) {
        record.reason = std::string{"checker failure: "} + failure.what();
        return finish();
    }
}

HullSmokeRecord record_bounded_hull_attempt(std::span<const Vector> input,
    std::variant<SourceIndexHull, std::string> algorithm_result,
    std::string algorithm_label, HullCheckBudget budget) {
    HullSmokeRecord record;
    record.algorithm = std::move(algorithm_label);
    if (const auto* failure = std::get_if<std::string>(&algorithm_result)) {
        record.algorithm_status = "failed";
        record.algorithm_failure = *failure;
        record.checker.budget = budget;
        record.checker.reason = "algorithm produced no source-index hull";
        return record;
    }
    record.algorithm_status = "completed";
    record.checker = check_source_index_hull(input,
        std::get<SourceIndexHull>(algorithm_result), budget);
    return record;
}

HullSmokeRecord run_bounded_square_smoke(HullCheckBudget budget) {
    const std::vector<Vector> square{{0,0}, {2,0}, {2,2}, {0,2},
        {1,1}, {1,0}, {2,1}, {1,2}, {0,1}};
    const auto output = quickhull_2d(square);
    if (const auto* failure = std::get_if<Diagnostics>(&output))
        return record_bounded_hull_attempt(square,
            failure->empty() ? std::string{"unknown algorithm failure"} : failure->front().explanation,
            "modern QuickHull2D", budget);
    const auto digest = digest_hull_input(square);
    if (const auto* failure = std::get_if<std::string>(&digest))
        return record_bounded_hull_attempt(square, *failure, "modern QuickHull2D", budget);
    const auto& hull = std::get<QuickHull2D>(output);
    return record_bounded_hull_attempt(square,
        SourceIndexHull{std::get<HullInputDigest>(digest), hull.vertex_indices}, "modern QuickHull2D", budget);
}

} // namespace csl::geometry
