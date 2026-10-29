#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <memory>
#include <variant>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"itis17-hull-test"}, {"seed"}}, {}, 0,
        {0,0,{0},{},{}}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

class StopWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::resource_limit,
            {program.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
            {}, {}, "test stop", {}};
    }
};

geometry::PointCloud square_cloud() {
    return {{"itis17-square"}, {{0,0}, {2,0}, {2,2}, {0,2}, {1,1}, {1,0}, {0,0}}};
}
} // namespace

TEST_CASE("ITIS17 reducer registrations preserve distinct method identities") {
    const auto a43 = geometry::make_itis17_a43_hull_reducer_registration();
    const auto a44 = geometry::make_itis17_a44_hull_reducer_registration();
    const auto paper_a44 = geometry::make_itis17_a44_paper_hull_reducer_registration();
    const auto opt06 = geometry::make_basis_reuse_hull_reducer_registration();
    const auto opt07 = geometry::make_ordered_hull_reducer_registration();
    CHECK(a43.identity.id.value == "csl.hull.itis17.a43-certified-basis-reuse");
    CHECK(a44.identity.id.value == "csl.hull.itis17.a44-incremental-lp");
    CHECK(paper_a44.identity.id.value == "csl.hull.itis17.a44-paper-farthest-incremental-lp");
    CHECK(a44.identity.id != paper_a44.identity.id);
    CHECK(a43.identity.id != opt06.identity.id);
    CHECK(a44.identity.id != opt07.identity.id);
}

TEST_CASE("A44 incremental LP adaptation preserves the exact hull and records both passes") {
    const auto cloud = square_cloud();
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);

    const auto result = geometry::reduce_itis17_a44_hull(cloud, *lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.status == geometry::ReductionStatus::complete);
    REQUIRE(reduction.itis17_a44.has_value());
    CHECK(reduction.itis17_a44->processing_order.size() == cloud.points.size());
    CHECK(reduction.itis17_a44->processing_order ==
          std::vector<std::size_t>{0, 1, 2, 3, 6, 5, 4});
    CHECK(reduction.itis17_a44->seeded_candidates == 3);
    CHECK(reduction.itis17_a44->incremental_membership_calls > 0);
    CHECK(reduction.itis17_a44->final_recheck_calls > 0);
    CHECK(reduction.lp_calls == reduction.itis17_a44->incremental_membership_calls +
          reduction.itis17_a44->final_recheck_calls);

    const auto digest = geometry::digest_hull_input(cloud.points);
    REQUIRE(std::holds_alternative<geometry::HullInputDigest>(digest));
    const auto checked = geometry::check_source_index_hull(cloud.points,
        {std::get<geometry::HullInputDigest>(digest), reduction.retained});
    CHECK(checked.status == geometry::HullCheckStatus::verified);
    for (const auto& certificate : reduction.removed)
        CHECK(certificate.evidence.verifier.value.ends_with(
            "exact-binary64-convex-combination"));

    const auto registration = geometry::make_itis17_a44_hull_reducer_registration();
    CHECK(registration.identity.id.value == "csl.hull.itis17.a44-incremental-lp");
    CHECK(registration.identity.version == "2.0.0");
}

TEST_CASE("A44 zero-width axes keep deterministic order and verify a collinear hull") {
    const geometry::PointCloud cloud{{"itis17-zero-width"},
        {{0,0}, {0,2}, {0,1}, {0,1}, {0,0}}};
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);
    const auto result = geometry::reduce_itis17_a44_hull(cloud, *lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.status == geometry::ReductionStatus::complete);
    REQUIRE(reduction.itis17_a44.has_value());
    CHECK(reduction.itis17_a44->zero_width_coordinates == 1);
    CHECK(reduction.itis17_a44->processing_order ==
          std::vector<std::size_t>{0, 1, 4, 2, 3});
    const auto digest = geometry::digest_hull_input(cloud.points);
    REQUIRE(std::holds_alternative<geometry::HullInputDigest>(digest));
    CHECK(geometry::check_source_index_hull(cloud.points,
        {std::get<geometry::HullInputDigest>(digest), reduction.retained}).status ==
        geometry::HullCheckStatus::verified);
}

TEST_CASE("A44 keeps uncertain candidates and reports an incomplete two-pass result") {
    const geometry::PointCloud cloud{{"itis17-stopped"}, {{0,0}, {2,0}, {1,0}}};
    StopWorkspace lp;
    const auto result = geometry::reduce_itis17_a44_hull(cloud, lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained.size() == cloud.points.size());
    REQUIRE(reduction.itis17_a44.has_value());
    CHECK(reduction.itis17_a44->seeded_candidates == cloud.points.size());
    CHECK(reduction.itis17_a44->incremental_membership_calls == 0);
}

TEST_CASE("A43 certificate-safe basis adaptation rechecks and preserves hull equality") {
    const auto cloud = square_cloud();
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);

    const auto result = geometry::reduce_itis17_a43_hull(cloud, *lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.status == geometry::ReductionStatus::complete);
    REQUIRE(reduction.itis17_a43.has_value());
    CHECK_FALSE(reduction.itis17_a43->largest_norm_tie_policy_applied);
    CHECK(reduction.itis17_a43->final_recheck_calls > 0);
    const auto digest = geometry::digest_hull_input(cloud.points);
    REQUIRE(std::holds_alternative<geometry::HullInputDigest>(digest));
    CHECK(geometry::check_source_index_hull(cloud.points,
        {std::get<geometry::HullInputDigest>(digest), reduction.retained}).status ==
        geometry::HullCheckStatus::verified);
}

TEST_CASE("A43 artificial-basis variants retain only independently certified hulls") {
    const auto cloud = square_cloud();
    const auto digest = geometry::digest_hull_input(cloud.points);
    REQUIRE(std::holds_alternative<geometry::HullInputDigest>(digest));
    for (const auto rule : {geometry::A43PivotRule::phase_one_order,
                            geometry::A43PivotRule::largest_norm_tie}) {
        auto lp = highs_workspace();
        REQUIRE(lp != nullptr);
        const auto result = geometry::reduce_itis17_a43_paper_hull(cloud, *lp, {}, rule);
        REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
        const auto& reduction = std::get<geometry::HullReduction>(result);
        REQUIRE(reduction.status == geometry::ReductionStatus::complete);
        REQUIRE(reduction.itis17_a43_paper.has_value());
        CHECK(reduction.itis17_a43_paper->candidate_solves > 0);
        CHECK(reduction.lp_calls == reduction.itis17_a43_paper->candidate_solves +
              reduction.itis17_a43_paper->final_recheck_calls);
        CHECK(reduction.itis17_a43_paper->phase_one_pivots > 0);
        CHECK(reduction.itis17_a43_paper->largest_norm_tie_rule ==
              (rule == geometry::A43PivotRule::largest_norm_tie));
        CHECK(geometry::check_source_index_hull(cloud.points,
            {std::get<geometry::HullInputDigest>(digest), reduction.retained}).status ==
            geometry::HullCheckStatus::verified);
        for (const auto& certificate : reduction.removed)
            CHECK(certificate.evidence.verifier.value.ends_with(
                "exact-binary64-convex-combination"));
    }

    const auto standard = geometry::make_itis17_a43_paper_hull_reducer_registration(
        geometry::A43PivotRule::phase_one_order);
    const auto tied = geometry::make_itis17_a43_paper_hull_reducer_registration(
        geometry::A43PivotRule::largest_norm_tie);
    CHECK(standard.identity.id.value == "csl.hull.itis17.a43-artificial-basis");
    CHECK(tied.identity.id.value == "csl.hull.itis17.a43-largest-norm-tie");
    CHECK(standard.identity.id != tied.identity.id);

    const geometry::PointCloud tie_cloud{{"itis17-a43-paper-tie"},
        {{1,1}, {2,2}, {0,1.5}, {1,0.5}, {3,1}, {1,3}, {-1,0}}};
    auto tie_lp = highs_workspace();
    REQUIRE(tie_lp != nullptr);
    const auto tie_result = geometry::reduce_itis17_a43_paper_hull(tie_cloud, *tie_lp, {},
        geometry::A43PivotRule::largest_norm_tie);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(tie_result));
    const auto& tie_reduction = std::get<geometry::HullReduction>(tie_result);
    REQUIRE(tie_reduction.itis17_a43_paper.has_value());
    CHECK(tie_reduction.itis17_a43_paper->candidate_solves > 0);
    CHECK(tie_reduction.itis17_a43_paper->largest_norm_tie_breaks > 0);
    const auto tie_digest = geometry::digest_hull_input(tie_cloud.points);
    REQUIRE(std::holds_alternative<geometry::HullInputDigest>(tie_digest));
    CHECK(geometry::check_source_index_hull(tie_cloud.points,
        {std::get<geometry::HullInputDigest>(tie_digest), tie_reduction.retained}).status ==
        geometry::HullCheckStatus::verified);
}
