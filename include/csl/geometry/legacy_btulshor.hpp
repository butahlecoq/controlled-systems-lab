#pragma once

#include <csl/core/values.hpp>

#include <cstddef>
#include <chrono>
#include <functional>
#include <optional>
#include <span>
#include <stop_token>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace csl::geometry::legacy_btulshor {

inline constexpr std::string_view reach_source_id = "csl.legacy.btulshor.reach.source-v1";

struct Limits {
    std::size_t max_pivots{100000};
    std::size_t max_dense_entries{1048576};
    bool capture_trace{false};
    std::size_t max_trace_events{4096};
    std::stop_token cancellation;
    std::optional<std::chrono::steady_clock::time_point> deadline;
};

enum class StopReason {
    invalid_input,
    capacity_limit,
    pivot_limit,
    non_finite_arithmetic,
    invalid_dependency_result,
    cancelled,
    deadline_expired,
};

struct Stopped {
    StopReason reason;
    std::string message;
};

template <class T>
using Outcome = std::variant<T, Stopped>;

struct ModifRequest {
    Matrix a;
    Vector x;
    double epsilon{1e-5};
    int initial_status{0};
};

struct PivotStep {
    std::size_t entering{};
    std::size_t leaving{};
    int phase{};
    double ratio{};
};

struct ModifResult {
    int original_status{};
    Vector x;
    std::vector<int> basis;
    std::size_t pivots{};
    std::vector<PivotStep> pivot_trace;
    std::vector<int> phase_sequence;
    bool trace_truncated{false};
};

struct ModifPort {
    std::string id;
    std::function<Outcome<ModifResult>(const ModifRequest&, const Limits&)> run;
};

struct KpabepCandidateStep {
    std::size_t candidate_index{};
    int original_status{};
    std::size_t pivots{};
};

struct KpabepResult {
    std::vector<Vector> points;
    std::vector<std::size_t> retained_indices;
    std::size_t modif_calls{};
    std::size_t pivots{};
    std::vector<KpabepCandidateStep> candidate_trace;
    bool trace_truncated{false};
};

struct KpabepPort {
    std::string id;
    std::function<Outcome<KpabepResult>(std::span<const Vector>, const ModifPort&, const Limits&)> run;
};

struct ReachRequest {
    Matrix a;
    Matrix b;
    std::vector<Vector> initial_points;
    std::vector<Vector> control_points;
};

struct ReachVertexSource {
    std::size_t initial_point_index{};
    std::size_t control_point_index{};
};

struct ReachResult {
    std::vector<Vector> points;
    std::vector<ReachVertexSource> source_vertices;
    std::size_t kpabep_calls{};
    std::size_t modif_calls{};
    std::size_t pivots{};
};

Outcome<ModifResult> modif(const ModifRequest& request, const Limits& limits = {});
ModifPort source_modif_port();
Outcome<KpabepResult> kpabep(std::span<const Vector> points,
                             const ModifPort& modif_port = source_modif_port(),
                             const Limits& limits = {});
KpabepPort source_kpabep_port();
Outcome<ReachResult> reach(const ReachRequest& request,
                           const KpabepPort& kpabep_port = source_kpabep_port(),
                           const ModifPort& modif_port = source_modif_port(),
                           const Limits& limits = {});

} // namespace csl::geometry::legacy_btulshor
