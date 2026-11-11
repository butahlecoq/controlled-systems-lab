#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/composition_catalogue.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/optimization/phase_one.hpp>

#include <algorithm>
#include <array>
#include <set>

using namespace csl;

namespace {
geometry::PointCloud fixture_cloud() {
    return {{"composition-catalogue-square-v1"},{{0,0},{1,0},{1,1},{0,1},{0.5,0.5}}};
}

std::vector<registry::Registration<registry::LPPort>> vertex_lp_methods() {
    auto highs_result = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(highs_result));
    auto phase_one_result = optimization::phase_one::make_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(phase_one_result));
    std::vector<registry::Registration<registry::LPPort>> result;
    result.push_back(std::get<registry::Registration<registry::LPPort>>(std::move(highs_result)));
    result.push_back(std::get<registry::Registration<registry::LPPort>>(std::move(phase_one_result)));
    return result;
}

const std::set<std::string> expected_hull_methods{
    "csl.hull.grouped-membership",
    "csl.hull.itis17.a43-artificial-basis",
    "csl.hull.itis17.a43-certified-basis-reuse",
    "csl.hull.itis17.a43-largest-norm-tie",
    "csl.hull.itis17.a44-incremental-lp",
    "csl.hull.itis17.a44-paper-farthest-incremental-lp",
    "csl.hull.lp-membership",
    "csl.hull.phase-one-basis-bulk",
    "csl.hull.ordered-membership",
    "csl.hull.recursive-split-merge"};
}

TEST_CASE("catalogue resolves every expected vertex reducer and selected LP provider") {
    std::set<std::string> observed_hull_methods;
    std::size_t admitted_graphs = 0;
    for (auto lp_registration : vertex_lp_methods()) {
        const auto expected_lp = lp_registration.identity;
        auto catalogue = geometry::make_hull_reducer_catalogue(std::move(lp_registration));
        const auto candidates = geometry::enumerate_hull_candidates(catalogue,2);
        REQUIRE(candidates.size() == expected_hull_methods.size());
        std::set<std::string> candidate_ids;
        for (const auto& candidate : candidates) {
            CHECK(candidate.vertex_lp.id == expected_lp.id);
            CHECK(candidate.vertex_lp.version == expected_lp.version);
            CHECK(candidate.representation == "csl.polyhedron.v");
            CHECK(candidate.controller == "not_used");
            CHECK(candidate.supporting_operations == "not_used");
            CHECK(candidate.terminal_optimizer == "not_used");
            CHECK(candidate.input_dimension == 2);
            CHECK(candidate.request_profile == "finite-binary64-point-cloud-v1");
            CHECK(candidate_ids.insert(candidate.id).second);
            observed_hull_methods.insert(candidate.vertex_reducer.id.value);

            auto prepared = geometry::prepare_hull_candidate(catalogue,candidate,fixture_cloud());
            REQUIRE(std::holds_alternative<geometry::PreparedHullCandidate>(prepared));
            auto execution = geometry::run_hull_candidate(
                std::get<geometry::PreparedHullCandidate>(std::move(prepared)));
            REQUIRE(std::holds_alternative<geometry::HullReduction>(execution.reduction));
            const auto& reduction = std::get<geometry::HullReduction>(execution.reduction);
            // Preparation proves this concrete module tuple is admitted. A
            // finite fixture run is separate evidence and may conservatively
            // retain a point when a numerical query is inconclusive.
            CHECK(std::all_of(reduction.retained.begin(), reduction.retained.end(),
                [&](std::size_t index) { return index < fixture_cloud().points.size(); }));
            REQUIRE(execution.provenance.size() == 2);
            CHECK(execution.provenance[0].actual->id == candidate.vertex_reducer.id);
            CHECK(execution.provenance[0].actual->version == candidate.vertex_reducer.version);
            CHECK(execution.provenance[1].actual->id == candidate.vertex_lp.id);
            CHECK(execution.provenance[1].actual->version == candidate.vertex_lp.version);
            for (const auto& query : execution.vertex_lp_queries)
                if (const auto* completed = std::get_if<registry::LPQueryCompleted>(&query)) {
                    CHECK(completed->provider.actual->id == candidate.vertex_lp.id);
                    CHECK(completed->provider.actual->version == candidate.vertex_lp.version);
                }
            ++admitted_graphs;
        }
        CHECK(candidate_ids.size() == expected_hull_methods.size());

        auto invalid_profile = candidates.front();
        invalid_profile.request_profile = "arbitrary-cloud";
        CHECK(std::holds_alternative<registry::Rejection>(
            geometry::prepare_hull_candidate(catalogue,invalid_profile,fixture_cloud())));

        auto wrong_dimension = fixture_cloud();
        wrong_dimension.points.front().push_back(0);
        CHECK(std::holds_alternative<registry::Rejection>(
            geometry::prepare_hull_candidate(catalogue,candidates.front(),wrong_dimension)));

        auto optimizer_as_hull_lp = candidates.front();
        optimizer_as_hull_lp.vertex_lp.id = {"csl.convex.highs"};
        optimizer_as_hull_lp.id = candidates.front().id;
        CHECK(std::holds_alternative<registry::Rejection>(
            geometry::prepare_hull_candidate(catalogue,optimizer_as_hull_lp,fixture_cloud())));
    }
    CHECK(observed_hull_methods == expected_hull_methods);
    CHECK(admitted_graphs == expected_hull_methods.size() * vertex_lp_methods().size());
}

TEST_CASE("catalogue resolver accepts a concrete four-dimensional point cloud profile") {
    auto lp_result = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result));
    auto catalogue = geometry::make_hull_reducer_catalogue(
        std::get<registry::Registration<registry::LPPort>>(std::move(lp_result)));
    const auto candidates = geometry::enumerate_hull_candidates(catalogue,4);
    REQUIRE_FALSE(candidates.empty());
    const geometry::PointCloud cloud{{"composition-catalogue-four-dimensional"},
        {{0,0,0,0},{1,0,0,0},{1,1,0,0},{0,1,1,1},{0.5,0.5,0.5,0.5}}};
    auto prepared = geometry::prepare_hull_candidate(catalogue,candidates.front(),cloud);
    REQUIRE(std::holds_alternative<geometry::PreparedHullCandidate>(prepared));
}

TEST_CASE("QuickHull2D rejects a dimension-invalid candidate without projecting it") {
    const std::array<Vector,3> three_dimensional{{{0,0,0},{1,0,0},{0,1,0}}};
    const auto result = geometry::quickhull_2d(three_dimensional);
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field == "points");
}
