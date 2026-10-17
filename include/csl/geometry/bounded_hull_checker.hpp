#pragma once

#include <csl/core/values.hpp>
#include <csl/problem/resolved_problem.hpp>

#include <chrono>
#include <cstddef>
#include <optional>
#include <span>
#include <string>
#include <variant>
#include <vector>

namespace csl::geometry {

// SHA-256 of a versioned, binary64-bit-exact, ordered point manifest.
// Source indices are positions in this manifest, including duplicate points.
using HullInputDigest = problem::ContentDigest;
using HullInputDigestResult = std::variant<HullInputDigest, std::string>;
HullInputDigestResult digest_hull_input(std::span<const Vector> points);

struct SourceIndexHull {
    HullInputDigest input_digest;
    std::vector<std::size_t> indices;
};

enum class HullCheckStatus { verified, incorrect, inconclusive };

struct HullCheckBudget {
    std::chrono::milliseconds wall{5000};
    std::size_t max_points{64};
};

struct HullCheckRecord {
    HullCheckStatus status{HullCheckStatus::inconclusive};
    std::optional<HullInputDigest> input_digest;
    std::chrono::nanoseconds elapsed{};
    HullCheckBudget budget{};
    std::string evidence_scope{"exact represented binary64 2D finite hull"};
    std::string reason;
    std::optional<std::size_t> counterexample_index;
};

// Independent bounded oracle: exact dyadic point-in-segment/triangle tests
// enumerate convex combinations of at most three reported source points.
// It does not invoke a hull algorithm, reducer, LP, or sampled support test.
HullCheckRecord check_source_index_hull(std::span<const Vector> input,
    const SourceIndexHull& output, HullCheckBudget budget = {});

struct HullSmokeRecord {
    // This is a modern-only smoke, with no historical side or timing claim.
    std::string algorithm{"modern QuickHull2D"};
    std::string algorithm_status;
    std::string algorithm_failure;
    HullCheckRecord checker;
};
HullSmokeRecord record_bounded_hull_attempt(std::span<const Vector> input,
    std::variant<SourceIndexHull, std::string> algorithm_result,
    std::string algorithm_label, HullCheckBudget budget = {});
HullSmokeRecord run_bounded_square_smoke(HullCheckBudget budget = {});

} // namespace csl::geometry
