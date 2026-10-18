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
    static bool is_expected_implication_program(const LinearProgram& p) {
        if (p.identity().problem.value != "geo04:bounded" ||
            p.identity().program.value != "halfspace-2" || p.offset() != 0.0 ||
            p.objective().size() != 2 || p.objective()[0] != 0.0 || p.objective()[1] != -1.0 ||
            p.variables().size() != 2 || p.rows().size() != 3) return false;
        const auto csr = std::get<numeric::CsrInput>(p.constraints().descriptor());
        if (csr.rows != 3 || csr.cols != 2 || csr.row_offsets.size() != 4 ||
            csr.column_indices.size() != 3 || csr.values.size() != 3 ||
            csr.row_offsets[0] != 0 || csr.row_offsets[1] != 1 ||
            csr.row_offsets[2] != 2 || csr.row_offsets[3] != 3 ||
            csr.column_indices[0] != 0 || csr.values[0] != 1.0 ||
            csr.column_indices[1] != 0 || csr.values[1] != -1.0 ||
            csr.column_indices[2] != 1 || csr.values[2] != 1.0) return false;
        return !p.rows()[0].lower && p.rows()[0].upper == 1.0 &&
            !p.rows()[1].lower && p.rows()[1].upper == 0.0 &&
            p.rows()[2].lower == 0.0 && p.rows()[2].upper == 0.0;
    }
    ProgramOutcome do_solve(const LinearProgram& p, const ExecutionContext&) override {
        // Only the expected implication LP receives the analytic lower bound.
        if (!is_expected_implication_program(p))
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
    const std::array<std::array<double,2>,8> expected{{
        {{1.0,0.5}}, {{1.0,-0.5}}, {{-1.0,0.5}}, {{-1.0,-0.5}},
        {{0.5,1.0}}, {{-0.5,1.0}}, {{0.5,-1.0}}, {{-0.5,-1.0}}
    }};
    std::array<bool,8> matched{};
    for (std::size_t i = 0; i < v.vertices.rows(); ++i) {
        std::size_t match_count = 0;
        std::size_t match_index = 0;
        for (std::size_t j = 0; j < expected.size(); ++j) {
            if (std::abs(v.vertices(i,0) - expected[j][0]) <= 1e-7 &&
                std::abs(v.vertices(i,1) - expected[j][1]) <= 1e-7) {
                ++match_count;
                match_index = j;
            }
        }
        CHECK(match_count == 1);
        if (match_count == 1) {
            CHECK_FALSE(matched[match_index]);
            matched[match_index] = true;
        }
        for (std::size_t j = 0; j < i; ++j) {
            const bool distinct = std::abs(v.vertices(i,0) - v.vertices(j,0)) > 1e-7 ||
                std::abs(v.vertices(i,1) - v.vertices(j,1)) > 1e-7;
            CHECK(distinct);
        }
        CHECK(std::abs(v.vertices(i,0)) <= 1.0 + 1e-7);
        CHECK(std::abs(v.vertices(i,1)) <= 1.0 + 1e-7);
        CHECK(std::abs(v.vertices(i,0)) + std::abs(v.vertices(i,1)) <= 1.5 + 1e-7);
    }
    for (const bool found : matched) CHECK(found);
}

TEST_CASE("unit square intersected with x+y<=1 matches the independent rational triangle") {
    const auto square=hset("rational-unit-square",
        {4,2,{1,0,-1,0,0,1,0,-1}},{1,0,1,0});
    const auto lower_triangle=hset("rational-x-plus-y-halfspace",
        {3,2,{1,1,-1,0,0,-1}},{1,0,0});
    const auto result=take(geometry::polyhedral::intersect_h(square,lower_triangle,
        {"rational-unit-triangle"}));
    const auto rep=result.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
    const auto& h=std::get<sets::HRepresentation>(rep);
    const auto inside=[&](const std::array<double,2>& point) {
        for (std::size_t row=0;row<h.inequalities.rows();++row)
            if (h.inequalities(row,0)*point[0]+h.inequalities(row,1)*point[1]
                >h.upper_bounds[row]) return false;
        for (std::size_t row=0;row<h.equalities.rows();++row)
            if (h.equalities(row,0)*point[0]+h.equalities(row,1)*point[1]
                !=h.equality_values[row]) return false;
        return true;
    };
    // Independently enumerate the rational triangle's vertices. Every point
    // in the expected triangle must satisfy all returned rows, and the five
    // square/diagonal facets must all be present, proving set equality while
    // allowing redundant or positively scaled rows.
    const std::array<std::array<double,2>,3> vertices{{{0,0},{1,0},{0,1}}};
    for (const auto& point : vertices) CHECK(inside(point));
    const std::array<std::array<double,3>,5> facets{{
        {{1,0,1}}, {{-1,0,0}}, {{0,1,1}}, {{0,-1,0}}, {{1,1,1}}}};
    for (const auto& facet : facets) {
        bool represented=false;
        for (std::size_t row=0;row<h.inequalities.rows();++row) {
            const auto scale=facet[0]!=0 ? h.inequalities(row,0)/facet[0] :
                h.inequalities(row,1)/facet[1];
            if (scale>0 && h.inequalities(row,0)==scale*facet[0] &&
                h.inequalities(row,1)==scale*facet[1] &&
                h.upper_bounds[row]==scale*facet[2]) represented=true;
        }
        CHECK(represented);
    }
    // Check interior, edges, and excluded points against the returned rows.
    const std::array<std::array<double,2>,6> inside_points{{
        {0,0}, {1,0}, {0,1}, {0.25,0.25}, {0.5,0.5}, {0.25,0.75}}};
    for (const auto& point : inside_points) {
        CHECK(inside(point));
    }
    const std::array<std::array<double,2>,3> outside_points{{
        {0.75,0.75}, {1,1}, {-0.25,0.25}}};
    for (const auto& point : outside_points) {
        CHECK_FALSE(inside(point));
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

TEST_CASE("analytic LP fixture rejects a matching ID with malformed implication rows") {
    const auto make_program = [](SparseMatrix rows, Vector objective,
            std::vector<Interval> row_bounds) {
        auto result = optimization::make_linear_program({{{"geo04:bounded"},{"halfspace-2"}},
            std::move(objective), 0.0, std::move(rows), std::vector<Interval>(2),
            std::move(row_bounds)});
        return take(std::move(result));
    };
    const EvidenceSupport support = NumericalCheck{0.0, 0.0, 0.0, {"test.lp-bound"}};
    const std::array<LinearProgram,2> malformed{{
        // Candidate y<=0 leaked into the implication constraints.
        make_program({4,2,{0,1,2,3,4},{0,0,1,1},{1,-1,1,1}}, {0,-1},
            {{ {},1.0 },{{},0.0},{{},0.0},{0.0,0.0}}),
        // Equality y=0 was omitted, so y<=0 is not implied by the remaining rows.
        make_program({2,2,{0,1,2},{0,0},{1,-1}}, {0,-1}, {{ {},1.0 },{{},0.0}})
    }};
    for (const auto& program : malformed) {
        FixedBoundWorkspace oracle{support};
        const auto result = oracle.solve(program, {});
        REQUIRE(std::holds_alternative<ProgramResult>(result));
        CHECK_FALSE(std::get<ProgramResult>(result).objective.lower.has_value());
    }
}
