#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <limits>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"hull"},{"seed"}}, {}, 0,
        {0,0,{0},{},{ }}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

bool independent_membership(LPWorkspace& workspace, const geometry::PointCloud& source,
        const std::vector<std::size_t>& hull, std::size_t candidate) {
    const auto dimension = source.points[candidate].size();
    const auto variables = hull.size();
    SparseMatrix a{dimension + 1, variables, {0}, {}, {}};
    Vector rhs = source.points[candidate];
    rhs.push_back(1.0);
    for (std::size_t row = 0; row <= dimension; ++row) {
        for (std::size_t col = 0; col < variables; ++col) {
            a.column_indices.push_back(col);
            a.values.push_back(row == dimension ? 1.0 : source.points[hull[col]][row]);
        }
        a.row_offsets.push_back(a.values.size());
    }
    std::vector<Interval> equalities;
    for (const double value : rhs) equalities.push_back({value, value});
    auto program = optimization::make_linear_program({
        {source.problem,{"independent-membership-" + std::to_string(candidate)}},
        Vector(variables, 0.0), 0.0, std::move(a),
        std::vector<Interval>(variables, {0.0, std::nullopt}), std::move(equalities)});
    if (!std::holds_alternative<LinearProgram>(program)) return false;
    auto outcome = workspace.solve(std::get<LinearProgram>(program), {});
    if (!std::holds_alternative<ProgramResult>(outcome)) return false;
    const auto& result = std::get<ProgramResult>(outcome);
    if (result.termination != Termination::completed || result.outcome.value != MathematicalOutcome::optimal ||
        !result.primal || result.primal->size() != variables) return false;
    double total = 0.0;
    Vector point(dimension, 0.0);
    for (std::size_t col = 0; col < variables; ++col) {
        if ((*result.primal)[col] < 0.0) return false;
        total += (*result.primal)[col];
        for (std::size_t row = 0; row < dimension; ++row)
            point[row] += (*result.primal)[col] * source.points[hull[col]][row];
    }
    if (std::abs(total - 1.0) > 1e-9) return false;
    for (std::size_t row = 0; row < dimension; ++row)
        if (std::abs(point[row] - source.points[candidate][row]) > 1e-9) return false;
    return true;
}

class LimitedWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::resource_limit,
            {program.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
            {}, {}, "test resource limit", {}};
    }
};
} // namespace

TEST_CASE("LP hull reduction removes a point only with a barycentric certificate") {
    auto workspace = highs_workspace();
    REQUIRE(workspace != nullptr);

    const geometry::PointCloud cloud{{"square"}, {
        {0,0}, {1,0}, {1,1}, {0,1}, {0.5,0.5}, {0.5,0}
    }};
    auto result = geometry::reduce_hull(cloud, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::complete);
    CHECK(reduction.retained.size() == 4);
    CHECK(reduction.attempts.size() == 6);
    CHECK(reduction.lp_calls == 6);
    CHECK(reduction.removed.size() == 2);
    for (const auto& certificate : reduction.removed) {
        CHECK(certificate.program.problem == cloud.problem);
        CHECK(certificate.program.program.value == "hull-membership-" + std::to_string(certificate.removed));
        double total = 0;
        Vector reconstructed(2, 0);
        for (const auto& term : certificate.combination) {
            CHECK(term.point != certificate.removed);
            REQUIRE(term.weight >= 0);
            total += term.weight;
            reconstructed[0] += term.weight * cloud.points[term.point][0];
            reconstructed[1] += term.weight * cloud.points[term.point][1];
        }
        CHECK(total == doctest::Approx(1).epsilon(1e-10));
        CHECK(reconstructed[0] == doctest::Approx(cloud.points[certificate.removed][0]).epsilon(1e-10));
        CHECK(reconstructed[1] == doctest::Approx(cloud.points[certificate.removed][1]).epsilon(1e-10));
    }

    // Independent LP construction/membership queries establish conv(original)
    // is contained in conv(retained); the reverse inclusion follows because
    // every retained point is an original point.
    auto oracle = highs_workspace();
    for (std::size_t point = 0; point < cloud.points.size(); ++point)
        CHECK(independent_membership(*oracle, cloud, reduction.retained, point));
}

TEST_CASE("LP hull reduction handles empty, singleton, duplicate and flat clouds") {
    auto workspace = highs_workspace();
    const geometry::PointCloud empty{{"empty"}, {}};
    auto empty_result = geometry::reduce_hull(empty, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(empty_result));
    CHECK(std::get<geometry::HullReduction>(empty_result).retained.empty());
    CHECK(std::get<geometry::HullReduction>(empty_result).lp_calls == 0);

    const geometry::PointCloud singleton{{"singleton"}, {{3.0, -2.0}}};
    auto singleton_result = geometry::reduce_hull(singleton, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(singleton_result));
    CHECK(std::get<geometry::HullReduction>(singleton_result).retained == std::vector<std::size_t>{0});
    CHECK(std::get<geometry::HullReduction>(singleton_result).lp_calls == 0);

    const geometry::PointCloud duplicates{{"duplicates"}, {{2.0}, {2.0}, {2.0}}};
    auto duplicate_result = geometry::reduce_hull(duplicates, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(duplicate_result));
    CHECK(std::get<geometry::HullReduction>(duplicate_result).retained.size() == 1);
    CHECK(std::get<geometry::HullReduction>(duplicate_result).removed.size() == 2);

    const geometry::PointCloud segment{{"flat"}, {{-2.0, 1.0, 4.0}, {0.0, 1.0, 4.0},
        {2.0, 1.0, 4.0}, {1.0, 1.0, 4.0}}};
    auto segment_result = geometry::reduce_hull(segment, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(segment_result));
    const auto& reduced = std::get<geometry::HullReduction>(segment_result);
    CHECK(reduced.retained.size() == 2);
    CHECK(reduced.removed.size() == 2);

    const geometry::PointCloud zero_dimensional{{"zero-dimensional"}, {{}, {}, {}}};
    auto zero_result = geometry::reduce_hull(zero_dimensional, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(zero_result));
    CHECK(std::get<geometry::HullReduction>(zero_result).retained.size() == 1);
}

TEST_CASE("uncertain membership never removes a point and reports an incomplete reduction") {
    LimitedWorkspace workspace;
    const geometry::PointCloud cloud{{"stopped"}, {{0.0}, {1.0}, {0.5}}};
    auto result = geometry::reduce_hull(cloud, workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained == std::vector<std::size_t>{0,1,2});
    CHECK(reduction.removed.empty());
    CHECK(reduction.lp_calls == 1);
    REQUIRE(reduction.attempts.size() == 1);
    CHECK(reduction.attempts.front().outcome == geometry::MembershipOutcome::stopped);
}

TEST_CASE("hull reducer rejects inconsistent and non-finite point clouds") {
    auto workspace = highs_workspace();
    const geometry::PointCloud inconsistent{{"bad-dimension"}, {{0.0}, {0.0, 1.0}}};
    CHECK(std::holds_alternative<Diagnostics>(geometry::reduce_hull(inconsistent, *workspace, {})));
    const geometry::PointCloud non_finite{{"non-finite"}, {{std::numeric_limits<double>::infinity()}}};
    CHECK(std::holds_alternative<Diagnostics>(geometry::reduce_hull(non_finite, *workspace, {})));
}
