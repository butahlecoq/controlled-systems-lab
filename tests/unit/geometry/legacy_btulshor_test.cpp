#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/legacy_btulshor.hpp>

#include <limits>

using namespace csl::geometry::legacy_btulshor;

TEST_CASE("MODIF preserves the source p=2 status for a zero-column request") {
    const ModifRequest request{.a = {3, 0, {}}, .x = {1, 0, -1}};
    const auto result = modif(request);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    CHECK(std::get<ModifResult>(result).original_status == 2);
}

TEST_CASE("MODIF preserves the source p=1 status for a zero-column request") {
    const ModifRequest request{.a = {3, 0, {}}, .x = {1, 0, 0}};
    const auto result = modif(request);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    const auto &raw = std::get<ModifResult>(result);
    CHECK(raw.original_status == 1);
}

TEST_CASE("MODIF preserves the source p=3 status when no ratio pivot exists") {
    const ModifRequest request{.a = {3, 1, {-1, 0, -1}}, .x = {1, 0, -1}};
    const auto result = modif(request);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    CHECK(std::get<ModifResult>(result).original_status == 3);
}

TEST_CASE("MODIF entry status preserves the objective row with zero structural columns") {
    const ModifRequest request{.a = {3, 0, {}}, .x = {1, 2, 0}, .initial_status = 1};
    const auto result = modif(request);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    const auto &raw = std::get<ModifResult>(result);
    CHECK(raw.original_status == 1);
    CHECK(raw.x[1] == 2);
}

TEST_CASE("MODIF entry status negates the source objective row in every column") {
    const ModifRequest request{.a = {3, 1, {1, 2, -1}}, .x = {1, 2, -1}, .initial_status = 1};
    const auto result = modif(request);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    const auto &raw = std::get<ModifResult>(result);
    CHECK(raw.original_status == 1);
    CHECK(raw.x == csl::Vector{1, 4, 0});
    CHECK(raw.basis == std::vector<int>{1, -2, -3});
}

TEST_CASE("MODIF keeps the first entering and leaving columns on exact ties") {
    const ModifRequest request{.a = {4, 2, {1, 1, 1, 1, 0, 0, -2, -2}}, .x = {1, 1, 0, -2}};
    Limits limits;
    limits.capture_trace = true;
    const auto result = modif(request, limits);
    REQUIRE(std::holds_alternative<ModifResult>(result));
    const auto &raw = std::get<ModifResult>(result);
    CHECK(raw.original_status == 1);
    CHECK(raw.basis.front() == 1);
    CHECK(raw.pivots == 1);
    REQUIRE(raw.pivot_trace.size() == 1);
    CHECK(raw.pivot_trace.front().entering == 1);
    CHECK(raw.pivot_trace.front().leaving == 1);
    CHECK(raw.phase_sequence == std::vector<int>{1, 2, 3});
}

TEST_CASE("KPABEP retains the source ordered vertices and original indices") {
    const std::vector<csl::Vector> points{{0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 0.5}, {1, 0}};
    const auto result = kpabep(points);
    REQUIRE(std::holds_alternative<KpabepResult>(result));
    const auto &raw = std::get<KpabepResult>(result);
    CHECK(raw.points == std::vector<csl::Vector>{{0, 1}, {0, 0}, {1, 0}, {1, 1}});
    CHECK(raw.retained_indices == std::vector<std::size_t>{3, 0, 1, 2});
}

TEST_CASE("KPABEP preserves the source j=2 retained-count shortcut") {
    const std::vector<csl::Vector> points{{2, -3}, {2, -3}, {2, -3}};
    const auto output = kpabep(points);
    REQUIRE(std::holds_alternative<KpabepResult>(output));
    const auto &raw = std::get<KpabepResult>(output);
    CHECK(raw.points == std::vector<csl::Vector>{{2, -3}});
    CHECK(raw.modif_calls == 2);
}

TEST_CASE("MODIF keeps caller matrices and vectors by value and enforces pivot budget") {
    const ModifRequest request{.a = {4, 2, {1, 1, 1, 1, 0, 0, -2, -2}}, .x = {1, 1, 0, -2}};
    const auto original_a = request.a.values;
    const auto original_x = request.x;
    Limits limits;
    limits.max_pivots = 0;
    const auto stopped = modif(request, limits);
    REQUIRE(std::holds_alternative<Stopped>(stopped));
    CHECK(std::get<Stopped>(stopped).reason == StopReason::pivot_limit);
    CHECK(request.a.values == original_a);
    CHECK(request.x == original_x);
    limits.max_pivots = 1;
    const auto exact_budget = modif(request, limits);
    REQUIRE(std::holds_alternative<ModifResult>(exact_budget));
    CHECK(std::get<ModifResult>(exact_budget).pivots == 1);
}

TEST_CASE("MODIF bounds optional traces without changing the raw status") {
    Limits limits;
    limits.capture_trace = true;
    limits.max_trace_events = 0;
    const auto output = modif({.a = {3, 0, {}}, .x = {1, 0, 0}}, limits);
    REQUIRE(std::holds_alternative<ModifResult>(output));
    const auto &raw = std::get<ModifResult>(output);
    CHECK(raw.original_status == 1);
    CHECK(raw.pivot_trace.empty());
    CHECK(raw.phase_sequence.empty());
    CHECK(raw.trace_truncated);
}

TEST_CASE("KPABEP calls the explicitly supplied MODIF port") {
    std::size_t calls = 0;
    ModifPort replacement{
        "test.modif", [&](const ModifRequest &request, const Limits &) -> Outcome<ModifResult> {
            ++calls;
            return ModifResult{2,  request.x, std::vector<int>(request.x.size(), -1), 0, {},
                               {}, false};
        }};
    const std::vector<csl::Vector> points{{0}, {1}, {0.5}};
    const auto output = kpabep(points, replacement);
    REQUIRE(std::holds_alternative<KpabepResult>(output));
    CHECK(calls > 0);
    CHECK(std::get<KpabepResult>(output).modif_calls == calls);
}

TEST_CASE("KPABEP refuses malformed MODIF dependency results") {
    ModifPort malformed{"test.bad-modif",
                        [](const ModifRequest &, const Limits &) -> Outcome<ModifResult> {
                            return ModifResult{2, {}, {}, 0, {}, {}, false};
                        }};
    const std::vector<csl::Vector> points{{0}, {1}};
    const auto output = kpabep(points, malformed);
    REQUIRE(std::holds_alternative<Stopped>(output));
    CHECK(std::get<Stopped>(output).reason == StopReason::invalid_dependency_result);
}

TEST_CASE("KPABEP accepts raw MODIF status 3 without treating it as a certificate") {
    ModifPort status_three{"test.status-three",
                           [](const ModifRequest &request, const Limits &) -> Outcome<ModifResult> {
                               return ModifResult{
                                   3,  request.x, std::vector<int>(request.x.size(), -1), 0, {},
                                   {}, false};
                           }};
    const std::vector<csl::Vector> points{{0}, {1}};
    const auto output = kpabep(points, status_three);
    REQUIRE(std::holds_alternative<KpabepResult>(output));
    CHECK(std::get<KpabepResult>(output).points.size() == 1);
}

TEST_CASE("KPABEP retains the source epsilon outcome for a near-extreme point") {
    const std::vector<csl::Vector> points{{0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 1.00000001}};
    const auto output = kpabep(points);
    REQUIRE(std::holds_alternative<KpabepResult>(output));
    const auto &raw = std::get<KpabepResult>(output);
    CHECK(raw.points == std::vector<csl::Vector>{{0, 1}, {0, 0}, {1, 0}, {1, 1}});
}

TEST_CASE("REACH pads primitive controls to n stride and places the last control first") {
    const ReachRequest request{.a = {2, 2, {1, 0, 0, 1}},
                               .b = {2, 1, {1, 2}},
                               .initial_points = {{0, 0}, {1, 1}},
                               .control_points = {{0}, {1}}};
    const auto output = reach(request);
    REQUIRE(std::holds_alternative<ReachResult>(output));
    const auto &raw = std::get<ReachResult>(output);
    REQUIRE(raw.points.size() == 4);
    CHECK(raw.points == std::vector<csl::Vector>{{1, 1}, {1, 2}, {2, 3}, {0, 0}});
    CHECK(raw.source_vertices[0].control_point_index == 0);
}

TEST_CASE("REACH refuses nr greater than n for the literal BEP stride") {
    const ReachRequest request{
        .a = {1, 1, {1}}, .b = {1, 2, {1, 0}}, .initial_points = {{0}}, .control_points = {{0, 0}}};
    const auto output = reach(request);
    REQUIRE(std::holds_alternative<Stopped>(output));
    CHECK(std::get<Stopped>(output).reason == StopReason::invalid_input);
}

TEST_CASE("REACH uses its injected KPABEP port and rejects bad retained indices") {
    std::size_t calls = 0;
    KpabepPort replacement{"test.kpabep",
                           [&](std::span<const csl::Vector> points, const ModifPort &,
                               const Limits &) -> Outcome<KpabepResult> {
                               ++calls;
                               return KpabepResult{{points.front()}, {0}, 0, 0, {}, false};
                           }};
    const ReachRequest request{.a = {1, 1, {1}},
                               .b = {1, 1, {1}},
                               .initial_points = {{0}},
                               .control_points = {{0}, {1}, {2}}};
    const auto output = reach(request, replacement);
    REQUIRE(std::holds_alternative<ReachResult>(output));
    CHECK(calls == 1);
    CHECK(std::get<ReachResult>(output).kpabep_calls == 1);

    KpabepPort malformed{"test.bad-kpabep",
                         [](std::span<const csl::Vector> points, const ModifPort &,
                            const Limits &) -> Outcome<KpabepResult> {
                             return KpabepResult{{points.front()}, {99}, 0, 0, {}, false};
                         }};
    const auto invalid = reach(request, malformed);
    REQUIRE(std::holds_alternative<Stopped>(invalid));
    CHECK(std::get<Stopped>(invalid).reason == StopReason::invalid_dependency_result);

    KpabepPort changed_coordinate{"test.changed-coordinate",
                                  [](std::span<const csl::Vector> points, const ModifPort &,
                                     const Limits &) -> Outcome<KpabepResult> {
                                      auto changed = points.front();
                                      changed.front() += 1;
                                      return KpabepResult{{changed}, {0}, 0, 0, {}, false};
                                  }};
    const ReachRequest first_filter_request{.a = {1, 1, {1}},
                                            .b = {1, 1, {0}},
                                            .initial_points = {{0}, {1}, {2}},
                                            .control_points = {{0}}};
    const auto changed = reach(first_filter_request, changed_coordinate);
    REQUIRE(std::holds_alternative<Stopped>(changed));
    CHECK(std::get<Stopped>(changed).reason == StopReason::invalid_dependency_result);

    KpabepPort duplicate_index{"test.duplicate-index",
                               [](std::span<const csl::Vector> points, const ModifPort &,
                                  const Limits &) -> Outcome<KpabepResult> {
                                   return KpabepResult{
                                       {points.front(), points.front()}, {0, 0}, 0, 0, {}, false};
                               }};
    const auto duplicated = reach(request, duplicate_index);
    REQUIRE(std::holds_alternative<Stopped>(duplicated));
    CHECK(std::get<Stopped>(duplicated).reason == StopReason::invalid_dependency_result);
}

TEST_CASE("REACH stops when finite inputs overflow during a transform") {
    const ReachRequest request{.a = {1, 1, {std::numeric_limits<double>::max()}},
                               .b = {1, 1, {0}},
                               .initial_points = {{2}},
                               .control_points = {{0}}};
    const auto output = reach(request);
    REQUIRE(std::holds_alternative<Stopped>(output));
    CHECK(std::get<Stopped>(output).reason == StopReason::non_finite_arithmetic);

    const ReachRequest overflow_on_translation{
        .a = {1, 1, {1}},
        .b = {1, 1, {1}},
        .initial_points = {{std::numeric_limits<double>::max()}},
        .control_points = {{std::numeric_limits<double>::max()}}};
    const auto translated = reach(overflow_on_translation);
    REQUIRE(std::holds_alternative<Stopped>(translated));
    CHECK(std::get<Stopped>(translated).reason == StopReason::non_finite_arithmetic);
}

TEST_CASE("MODIF rejects malformed dense input and respects allocation capacity") {
    const auto malformed = modif({.a = {3, 1, {1, 2}}, .x = {1, 0, 0}});
    REQUIRE(std::holds_alternative<Stopped>(malformed));
    CHECK(std::get<Stopped>(malformed).reason == StopReason::invalid_input);
    Limits limits;
    limits.max_dense_entries = 2;
    const auto over_capacity = modif({.a = {3, 1, {1, 0, -1}}, .x = {1, 0, -1}}, limits);
    REQUIRE(std::holds_alternative<Stopped>(over_capacity));
    CHECK(std::get<Stopped>(over_capacity).reason == StopReason::capacity_limit);
}
