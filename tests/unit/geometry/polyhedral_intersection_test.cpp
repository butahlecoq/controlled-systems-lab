#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>

#include <array>
#include <utility>

using namespace csl;

namespace {
template<class T, class... U> T take(std::variant<T, U...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
numeric::MatrixView matrix(std::size_t rows, std::size_t cols, Vector values) {
    return take(numeric::snapshot(Matrix{rows, cols, std::move(values)}));
}
numeric::VectorView vector(Vector values) { return take(numeric::snapshot_vector(values)); }
sets::SetData hset(std::string id, Matrix a, Vector b, Matrix e = {0, 2, {}}, Vector f = {}) {
    return take(sets::make_h({{std::move(id)}, 2, {"x", "y"}},
        {matrix(a.rows, a.cols, std::move(a.values)), vector(std::move(b)),
         matrix(e.rows, e.cols, std::move(e.values)), vector(std::move(f))}));
}
struct FixedBoundWorkspace final : LPWorkspace {
    EvidenceSupport support;
    explicit FixedBoundWorkspace(EvidenceSupport evidence) : support(std::move(evidence)) {}
protected:
    ProgramOutcome do_solve(const LinearProgram& p, const ExecutionContext&) override {
        // This test oracle supplies the analytically known lower bound 0 for
        // the equality-implied y<=0 row; other rows receive no bound.
        if (p.identity().program.value != "halfspace-2")
            return ProgramResult{Termination::completed,
                {p.identity(), MathematicalOutcome::optimal, Unestablished{}, {}}, {}, {}, "no bound"};
        ProgramResult r{Termination::completed,
            {p.identity(), MathematicalOutcome::optimal, support, {}}, {}, {}, "literal fixture"};
        r.objective.lower = ProgramObjectiveBound{0.0,
            {p.identity(), support, {}}};
        return r;
    }
};
}

TEST_CASE("H intersection discovers new vertices when no input corner is feasible") {
    // The square [-1,1]^2 and diamond |x|+|y|<=1.5 have no vertex in
    // common, but their intersection is a nonempty octagon of edge crossings.
    const auto left = hset("left", {4,2,{1,0,-1,0,0,1,0,-1}}, {1,1,1,1});
    const auto right = hset("right", {4,2,{1,1,1,-1,-1,1,-1,-1}}, {1.5,1.5,1.5,1.5});
    const std::array<std::array<double,2>,4> left_corners{{{1,1},{-1,1},{-1,-1},{1,-1}}};
    for (const auto& corner : left_corners) {
        const bool outside_right = std::abs(corner[0]) + std::abs(corner[1]) > 1.5;
        CHECK(outside_right);
    }
    const std::array<std::array<double,2>,4> right_corners{{{1.5,0},{0,1.5},{-1.5,0},{0,-1.5}}};
    for (const auto& corner : right_corners) {
        const bool outside_left = std::abs(corner[0]) > 1.0 || std::abs(corner[1]) > 1.0;
        CHECK(outside_left);
    }
    const auto result = take(geometry::polyhedral::intersect_h(left, right, {"overlap"}));
    const auto rep = result.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
    const auto& h = std::get<sets::HRepresentation>(rep);
    CHECK(h.inequalities.rows() == 8);
    CHECK(h.equalities.rows() == 0);

    auto highs = take(adapters::lp::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(highs));
    registry::Registry<registry::ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(std::move(converter)).has_value());
    ConversionRequest request{{{"geo04-tests"},{"overlap-to-v"},{"overlap-ideal"}},
        result.as_handle(), {"csl.polyhedron.v"}, Assurance::numerical};
    registry::Requirements required;
    required.output = {{"csl.polyhedron.v"}, Assurance::numerical, SetRelation::equivalent, {}, {}};
    auto prepared = registry::prepare_pipeline(registry::select(conversions,
        {{"csl.conversion.qhull"}, {}}, request, required));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(prepared));
    auto [workspace] = std::get<registry::PreparedPipeline<registry::ConversionPort>>(prepared).create();
    auto converted = workspace->run(ExecutionContext{});
    REQUIRE(std::holds_alternative<OperationResult>(converted));
    const auto vdata = take(sets::from_handle(std::get<OperationResult>(converted).output));
    const auto vrep = vdata.representation();
    REQUIRE(std::holds_alternative<sets::VRepresentation>(vrep));
    const auto& v = std::get<sets::VRepresentation>(vrep);
    REQUIRE(v.vertices.rows() == 8);
    for (std::size_t i = 0; i < v.vertices.rows(); ++i) {
        CHECK(std::abs(v.vertices(i,0)) <= 1.0 + 1e-7);
        CHECK(std::abs(v.vertices(i,1)) <= 1.0 + 1e-7);
        CHECK(std::abs(v.vertices(i,0)) + std::abs(v.vertices(i,1)) <= 1.5 + 1e-7);
    }
}

TEST_CASE("H intersection retains empty results and affine equalities") {
    const auto left = hset("left", {1,2,{1,0}}, {0});
    const auto right = hset("right", {1,2,{-1,0}}, {-1});
    auto empty_h = take(geometry::polyhedral::intersect_h(left, right, {"empty"}));
    auto highs = take(adapters::lp::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(highs));
    registry::Registry<registry::ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(std::move(converter)).has_value());
    ConversionRequest request{{{"geo04-tests"},{"empty-to-v"},{"empty-ideal"}},
        empty_h.as_handle(), {"csl.polyhedron.v"}, Assurance::numerical};
    registry::Requirements required;
    required.output = {{"csl.polyhedron.v"}, Assurance::numerical, SetRelation::equivalent, {}, {}};
    auto prepared = registry::prepare_pipeline(registry::select(conversions,
        {{"csl.conversion.qhull"}, {}}, request, required));
    auto [workspace] = std::get<registry::PreparedPipeline<registry::ConversionPort>>(prepared).create();
    const auto empty_v = workspace->run(ExecutionContext{});
    REQUIRE(std::holds_alternative<OperationResult>(empty_v));
    const auto empty_data = take(sets::from_handle(std::get<OperationResult>(empty_v).output));
    REQUIRE(std::holds_alternative<sets::VRepresentation>(empty_data.representation()));
    CHECK(std::get<sets::VRepresentation>(empty_data.representation()).vertices.rows() == 0);

    const auto band = hset("band", {2,2,{1,0,-1,0}}, {2,0}, {1,2,{0,1}}, {1});
    const auto merged = take(geometry::polyhedral::intersect_h(band, band, {"band-copy"}));
    const auto rep = std::get<sets::HRepresentation>(merged.representation());
    CHECK(rep.inequalities.rows() == 4);
    REQUIRE(rep.equalities.rows() == 2);
    CHECK(rep.equalities(0,0) == 0.0);
    CHECK(rep.equalities(0,1) == 1.0);
    CHECK(rep.equality_values[0] == 1.0);
}

TEST_CASE("halfspace deletion requires a supported implication bound and preserves equalities") {
    const auto set = hset("bounded", {3,2,{1,0,-1,0,0,1}}, {1,0,0}, {1,2,{0,1}}, {0});
    FixedBoundWorkspace lp{NumericalCheck{0.0, 0.0, 0.0, {"test.lp-bound"}}};
    const auto reduced = geometry::polyhedral::remove_redundant_halfspaces(set, {"reduced"}, lp, {});
    REQUIRE(std::holds_alternative<geometry::polyhedral::HalfspaceReduction>(reduced));
    const auto& output = std::get<geometry::polyhedral::HalfspaceReduction>(reduced);
    CHECK(output.status == geometry::polyhedral::HalfspaceReductionStatus::incomplete);
    CHECK(output.retained_inequalities == std::vector<std::size_t>{0,1});
    CHECK(output.removed_inequalities == std::vector<std::size_t>{2});
    CHECK(output.lp_calls == 3);
    const auto rep = std::get<sets::HRepresentation>(output.set.representation());
    CHECK(rep.inequalities.rows() == 2);
    CHECK(rep.equalities.rows() == 1);
    CHECK(rep.equality_values[0] == 0.0);
    for (const auto& point : std::array<std::array<double,2>,3>{{{0.0,0.0},{0.5,0.0},{1.0,0.0}}}) {
        CHECK(rep.inequalities(0,0) * point[0] + rep.inequalities(0,1) * point[1] <= rep.upper_bounds[0]);
        CHECK(rep.inequalities(1,0) * point[0] + rep.inequalities(1,1) * point[1] <= rep.upper_bounds[1]);
        CHECK(rep.equalities(0,0) * point[0] + rep.equalities(0,1) * point[1] == rep.equality_values[0]);
    }
    CHECK(rep.inequalities(0,0) * 1.5 > rep.upper_bounds[0]);
    CHECK(rep.inequalities(1,0) * -0.5 > rep.upper_bounds[1]);

    FixedBoundWorkspace symbolic_lp{SymbolicArgument{"test fixture", "unverified statement"}};
    const auto unverified = geometry::polyhedral::remove_redundant_halfspaces(set, {"unverified"}, symbolic_lp, {});
    REQUIRE(std::holds_alternative<geometry::polyhedral::HalfspaceReduction>(unverified));
    const auto& conservative = std::get<geometry::polyhedral::HalfspaceReduction>(unverified);
    CHECK(conservative.removed_inequalities.empty());
    CHECK(conservative.retained_inequalities == std::vector<std::size_t>{0,1,2});
}
