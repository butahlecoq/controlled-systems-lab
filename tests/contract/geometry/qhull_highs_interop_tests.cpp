#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>

using namespace csl;
using namespace csl::registry;
using namespace csl::optimization;

namespace {
template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(std::size_t rows, std::size_t cols, Vector values) {
    return take(numeric::snapshot(Matrix{rows, cols, std::move(values)}));
}
numeric::VectorView vector(Vector values) {
    return take(numeric::snapshot_vector(values));
}

csl::SetHandle ordered_square(std::array<std::array<double, 2>, 4> vertices, std::string id) {
    Vector values;
    for (const auto& vertex : vertices) values.insert(values.end(), vertex.begin(), vertex.end());
    return take(sets::make_v({{std::move(id)}, 2, {}},
        {matrix(4, 2, std::move(values)), matrix(0, 2, {})})).as_handle();
}

ExecutionContext context() {
    return {std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}), {}, {},
        {1e-8, 1e-8}, "qhull-highs-interop"};
}

Requirements conversion_requirements() {
    Requirements r;
    r.output.representation = {"csl.polyhedron.h"};
    r.output.assurance = Assurance::numerical;
    r.output.relation = SetRelation::equivalent;
    return r;
}

sets::SetData convert_to_h(const csl::SetHandle& input, std::string id) {
    const auto conversion = take(csl::adapters::polyhedral::make_qhull_registration(
        take(csl::adapters::lp::make_highs_registration())));
    Registry<ConversionPort> conversions;
    REQUIRE_FALSE(conversions.add(conversion).has_value());
    ConversionRequest request{{{"qhull-highs-interop"}, {std::move(id)}, {"unit-square-h"}},
        input, {"csl.polyhedron.h"}, Assurance::numerical};
    auto prepared = prepare_pipeline(select(conversions, {{"csl.conversion.qhull"}, {}}, request,
        conversion_requirements()));
    REQUIRE(std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared));
    auto [worker] = std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    auto outcome = worker->run(context());
    REQUIRE(std::holds_alternative<OperationResult>(outcome));
    auto output = sets::from_handle(std::get<OperationResult>(outcome).output);
    REQUIRE(std::holds_alternative<sets::SetData>(output));
    return std::get<sets::SetData>(std::move(output));
}

SparseMatrix control_csr(const sets::HRepresentation& h) {
    SparseMatrix a{h.inequalities.rows() + 2, 4, {0}, {}, {}};
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i) {
        for (std::size_t j = 0; j < h.inequalities.cols(); ++j) {
            const double value = h.inequalities(i, j);
            if (value != 0) {
                a.column_indices.push_back(j);
                a.values.push_back(value);
            }
        }
        a.row_offsets.push_back(a.values.size());
    }
    a.column_indices.insert(a.column_indices.end(), {0, 2, 1, 3});
    a.values.insert(a.values.end(), {1, -1, 1, -1});
    a.row_offsets.push_back(a.values.size() - 2);
    a.row_offsets.push_back(a.values.size());
    return a;
}

std::vector<Interval> control_row_bounds(const sets::HRepresentation& h) {
    std::vector<Interval> rows(h.inequalities.rows() + 2);
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i)
        rows[i].upper = h.upper_bounds[i];
    rows[h.inequalities.rows()] = {0, 0};
    rows[h.inequalities.rows() + 1] = {0, 0};
    return rows;
}

ProgramOutcome solve_lp(const sets::HRepresentation& h) {
    auto program = take(make_linear_program({{{"qhull-highs-interop"}, {"square-lp"}},
        {1, 1, 0, 0}, 0, control_csr(h), {Interval{}, Interval{}, Interval{}, Interval{}}, control_row_bounds(h)}));
    auto registration = take(csl::adapters::lp::make_highs_registration());
    auto workspace = registration.factory(program);
    auto outcome = workspace->solve(program, context());
    if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        for (const auto& d : unsupported->diagnostics)
            std::cout << "LP refusal: " << d.field << ": " << d.explanation << '\n';
        return outcome;
    }
    auto result = std::get<ProgramResult>(std::move(outcome));
    REQUIRE(result.primal.has_value());
    const auto evaluated = take(evaluate_primal(program, *result.primal, {1e-8, 1e-8}, {{"independent-lp"}, "1"}));
    CHECK(evaluated.objective == doctest::Approx(0).epsilon(1e-8));
    std::cout << "LP: x*= (" << (*result.primal)[0] << ", " << (*result.primal)[1]
              << "), u*= (" << (*result.primal)[2] << ", " << (*result.primal)[3]
              << "), J*= " << evaluated.objective << '\n';
    return result;
}

ProgramOutcome solve_qp(const sets::HRepresentation& h) {
    auto program = take(make_convex_program({{{"qhull-highs-interop"}, {"square-qp"}},
        QuadraticTerminal{{4, 4, {2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}},
            {-0.5, -1.5, 0, 0}, 0.625}, control_csr(h),
        {Interval{}, Interval{}, Interval{}, Interval{}}, control_row_bounds(h), {}}));
    auto registration = take(csl::adapters::convex::make_highs_registration());
    auto workspace = registration.factory(program);
    auto outcome = workspace->solve(program, context());
    if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        for (const auto& d : unsupported->diagnostics)
            std::cout << "QP refusal: " << d.field << ": " << d.explanation << '\n';
        return outcome;
    }
    auto result = std::get<ProgramResult>(std::move(outcome));
    REQUIRE(result.primal.has_value());
    const auto evaluated = take(evaluate_primal(program, *result.primal, {1e-8, 1e-8}, {{"independent-qp"}, "1"}));
    CHECK(evaluated.original_objective == doctest::Approx(0).epsilon(1e-8));
    std::cout << "QP: x*= (" << (*result.primal)[0] << ", " << (*result.primal)[1]
              << "), u*= (" << (*result.primal)[2] << ", " << (*result.primal)[3]
              << "), J*= " << evaluated.original_objective << '\n';
    return result;
}

void check_point_and_objective(const ProgramResult& result, std::array<double, 2> expected,
                               double expected_objective) {
    INFO(result.raw_diagnostics);
    REQUIRE(result.termination == Termination::completed);
    REQUIRE(result.outcome.value == MathematicalOutcome::optimal);
    REQUIRE(result.primal.has_value());
    REQUIRE(result.primal->size() == 4);
    CHECK((*result.primal)[0] == doctest::Approx(expected[0]).epsilon(1e-8));
    CHECK((*result.primal)[1] == doctest::Approx(expected[1]).epsilon(1e-8));
    CHECK((*result.primal)[2] == doctest::Approx(expected[0]).epsilon(1e-8));
    CHECK((*result.primal)[3] == doctest::Approx(expected[1]).epsilon(1e-8));
    const double actual_objective = expected[0] == 0.25
        ? std::pow((*result.primal)[0] - 0.25, 2) + std::pow((*result.primal)[1] - 0.75, 2)
        : (*result.primal)[0] + (*result.primal)[1];
    CHECK(actual_objective == doctest::Approx(expected_objective).epsilon(1e-8));
}

bool satisfies(const sets::HRepresentation& h, double x, double y) {
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i)
        if (h.inequalities(i, 0)*x + h.inequalities(i, 1)*y > h.upper_bounds[i] + 1e-10) return false;
    return true;
}

void check_square_h(const sets::HRepresentation& h) {
    CHECK(h.inequalities.rows() == 4);
    CHECK(h.equalities.rows() == 0);
    const std::array<std::array<double, 3>, 4> expected{{
        {1, 0, 1}, {-1, 0, 0}, {0, 1, 1}, {0, -1, 0}}};
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i) {
        bool matched = false;
        for (const auto& row : expected)
            matched = matched || (std::abs(h.inequalities(i, 0) - row[0]) < 1e-10 &&
                std::abs(h.inequalities(i, 1) - row[1]) < 1e-10 &&
                std::abs(h.upper_bounds[i] - row[2]) < 1e-10);
        CHECK(matched);
    }
    for (const auto& p : {std::array{0.0, 0.0}, std::array{1.0, 0.0},
                          std::array{0.0, 1.0}, std::array{1.0, 1.0}})
        CHECK(satisfies(h, p[0], p[1]));
    for (const auto& outside : {std::array{-0.01, 0.5}, std::array{1.01, 0.5},
                                std::array{0.5, -0.01}, std::array{0.5, 1.01}})
        CHECK_FALSE(satisfies(h, outside[0], outside[1]));
}
}

TEST_CASE("ordered unit square Qhull output composes with public HiGHS LP and QP interfaces") {
    const std::array<std::array<double, 2>, 4> vertices{{{0, 1}, {1, 1}, {0, 0}, {1, 0}}};
    const auto output = convert_to_h(ordered_square(vertices, "source-square"), "ordered-square");
    const auto rep = output.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
    const auto& h = std::get<sets::HRepresentation>(rep);
    check_square_h(h);
    std::cout << std::setprecision(17) << "V = [(0,1),(1,1),(0,0),(1,0)]\nH: A x <= b\nA = [";
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i) {
        if (i) std::cout << "; ";
        std::cout << h.inequalities(i, 0) << ", " << h.inequalities(i, 1);
    }
    std::cout << "]\nb = [";
    for (std::size_t i = 0; i < h.upper_bounds.size(); ++i) {
        if (i) std::cout << ", ";
        std::cout << h.upper_bounds[i];
    }
    std::cout << "]\n";

    const auto lp = solve_lp(h);
    CHECK(std::holds_alternative<ProgramResult>(lp));
    if (const auto* result = std::get_if<ProgramResult>(&lp))
        check_point_and_objective(*result, {0, 0}, 0);
    const auto qp = solve_qp(h);
    CHECK(std::holds_alternative<ProgramResult>(qp));
    if (const auto* result = std::get_if<ProgramResult>(&qp))
        check_point_and_objective(*result, {0.25, 0.75}, 0);
}

TEST_CASE("full-rank square conversion does not depend on vertex ordering") {
    const std::array<std::array<double, 2>, 4> source{{{0, 1}, {1, 1}, {0, 0}, {1, 0}}};
    for (const auto order : {std::array{0, 1, 2, 3}, std::array{1, 3, 0, 2},
                             std::array{2, 0, 3, 1}, std::array{3, 2, 1, 0}}) {
        std::array<std::array<double, 2>, 4> vertices{};
        for (std::size_t i = 0; i < order.size(); ++i) vertices[i] = source[order[i]];
        const auto converted = convert_to_h(ordered_square(vertices, "permuted-square"), "permuted");
        const auto rep = converted.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
        const auto& h = std::get<sets::HRepresentation>(rep);
        check_square_h(h);
        for (std::size_t i = 0; i < h.inequalities.rows(); ++i)
            for (std::size_t j = 0; j < h.inequalities.cols(); ++j)
                CHECK((h.inequalities(i, j) == 0 || std::abs(h.inequalities(i, j)) > 1e-12));
    }
}

TEST_CASE("genuine small nonzero facet coefficients remain explicit and unsupported by HiGHS") {
    constexpr double epsilon = 5e-13;
    const std::array<std::array<double, 2>, 4> thin_shear{{
        {0, 0}, {1, 0}, {1 - epsilon, 1}, {-epsilon, 1}}};
    const auto converted = convert_to_h(ordered_square(thin_shear, "thin-shear"), "thin-shear");
    const auto rep = converted.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rep));
    const auto& h = std::get<sets::HRepresentation>(rep);
    const std::array<std::array<double, 2>, 4> expected_vertices{{
        {0, 0}, {1, 0}, {1 - epsilon, 1}, {-epsilon, 1}}};
    const std::array<std::array<double, 3>, 4> expected_facets{{
        {1, epsilon, 1}, {-1, -epsilon, 0}, {0, 1, 1}, {0, -1, 0}}};
    CHECK(h.inequalities.rows() == expected_facets.size());
    for (const auto& vertex : expected_vertices)
        CHECK(satisfies(h, vertex[0], vertex[1]));
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i) {
        bool matched = false;
        for (const auto& expected : expected_facets)
            matched = matched || (std::abs(h.inequalities(i, 0) - expected[0]) < 1e-10 &&
                std::abs(h.inequalities(i, 1) - expected[1]) < 1e-13 &&
                std::abs(h.upper_bounds[i] - expected[2]) < 1e-10);
        CHECK(matched);
    }
    bool retained_small_nonzero = false;
    bool retained_geometric_shear = false;
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i)
        for (std::size_t j = 0; j < h.inequalities.cols(); ++j)
            retained_small_nonzero = retained_small_nonzero ||
                (h.inequalities(i, j) != 0 && std::abs(h.inequalities(i, j)) < 1e-12);
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i)
        retained_geometric_shear = retained_geometric_shear ||
            (std::abs(std::abs(h.inequalities(i, 0)) - 1) < 1e-10 &&
             std::abs(std::abs(h.inequalities(i, 1)) - epsilon) < 1e-13);
    CHECK(retained_small_nonzero);
    CHECK(retained_geometric_shear);
    const auto program = take(make_linear_program({{{"qhull-highs-interop"}, {"thin-shear-lp"}},
        {1, 1, 0, 0}, 0, control_csr(h), {Interval{}, Interval{}, Interval{}, Interval{}}, control_row_bounds(h)}));
    auto registration = take(csl::adapters::lp::make_highs_registration());
    auto workspace = registration.factory(program);
    const auto rejected = workspace->solve(program, context());
    CHECK(std::holds_alternative<Unsupported>(rejected));
    if (const auto* unsupported = std::get_if<Unsupported>(&rejected)) {
        for (const auto& d : unsupported->diagnostics) INFO(d.field << ": " << d.explanation);
        REQUIRE_FALSE(unsupported->diagnostics.empty());
        CHECK(unsupported->diagnostics.front().field == "highs.matrix");
    }
}
