#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>

using namespace csl;
using namespace csl::geometry;
using namespace csl::geometry::approximation;

namespace {

SetHandle diamond_v() {
    const Matrix vertices{4, 2, {0, 2, 2, 0, 0, -2, -2, 0}};
    const auto points = numeric::snapshot(vertices);
    const auto rays = numeric::snapshot(Matrix{0, 2, {}});
    if (!std::holds_alternative<numeric::MatrixView>(points) ||
        !std::holds_alternative<numeric::MatrixView>(rays))
        throw std::runtime_error("Unable to store diamond vertices");
    const auto made = sets::make_v({{"approx-pilot-diamond-v"}, 2, {"x", "y"}},
        {std::get<numeric::MatrixView>(points), std::get<numeric::MatrixView>(rays)});
    if (!std::holds_alternative<sets::SetData>(made))
        throw std::runtime_error("Unable to construct diamond V set");
    return std::get<sets::SetData>(made).as_handle();
}

SetHandle diamond_generators() {
    // Splitting one generator preserves the same diamond and makes the
    // two-generator output budget force an axis-cover approximation.
    const auto made = sets::make_generator_set({{"approx-pilot-diamond-z"}, {0, 0},
        Matrix{2, 3, {0.5, 0.5, 1, 0.5, 0.5, -1}},
        {{"g1a"}, {"g1b"}, {"g2"}}, Matrix{0, 3, {}}, {}, {"x", "y"}});
    if (!std::holds_alternative<sets::GeneratorSet>(made))
        throw std::runtime_error("Unable to construct diamond generator set");
    return std::get<sets::GeneratorSet>(made).as_handle();
}

bool exact_h(const SetHandle& output, const Matrix& rows, const Vector& bounds) {
    const auto native = sets::from_handle(output);
    const auto* data = std::get_if<sets::SetData>(&native);
    if (!data) return false;
    const auto representation = data->representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->inequalities.rows() != rows.rows ||
        h->inequalities.cols() != rows.cols || h->upper_bounds.size() != bounds.size() ||
        h->equalities.rows() != 0) return false;
    for (std::size_t row = 0; row < rows.rows; ++row) {
        if (h->upper_bounds[row] != bounds[row]) return false;
        for (std::size_t column = 0; column < rows.cols; ++column)
            if (h->inequalities(row, column) != rows.values[row * rows.cols + column])
                return false;
    }
    return true;
}

struct Result {
    const char* method;
    double area{};
    long long elapsed_ns{};
    bool passed{};
    const char* evidence{};
};

Result exact_hull() {
    constexpr double expected_area = 8.0;
    const std::vector<Vector> points{{0, 2}, {2, 0}, {0, -2}, {-2, 0}};
    const auto start = std::chrono::steady_clock::now();
    auto result = quickhull_2d(points);
    const auto stop = std::chrono::steady_clock::now();
    if (!std::holds_alternative<QuickHull2D>(result))
        return {"exact-polygon-quickhull", 0, 0, false, "unsupported"};
    auto actual = std::get<QuickHull2D>(result).vertex_indices;
    std::vector<Vector> vertices;
    for (const auto id : actual) {
        if (id >= points.size()) return {"exact-polygon-quickhull", 0, 0, false, "bad-index"};
        vertices.push_back(points[id]);
    }
    std::sort(vertices.begin(), vertices.end());
    const std::vector<Vector> expected{{-2, 0}, {0, -2}, {0, 2}, {2, 0}};
    return {"exact-polygon-quickhull", expected_area,
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count(),
        vertices == expected, "exact-literal-hull"};
}

Result box(const SetHandle& input) {
    registry::Registry<registry::ApproximationPort> methods;
    if (methods.add(make_box_registration({"approx-pilot-box"})))
        throw std::runtime_error("Box registration failed");
    const registry::Method method{{"csl.approximation.box"}, std::nullopt};
    const ApproximationRequest request{{{"approx-pilot"}, {"box"}, {"diamond"}},
        input, {"csl.polyhedron.h"}, SetRelation::outer, 4, Assurance::numerical};
    const auto start = std::chrono::steady_clock::now();
    const auto outcome = run_registered(methods, method, request, ExecutionContext{});
    const auto stop = std::chrono::steady_clock::now();
    const auto* enclosed = std::get_if<EnclosedApproximation>(&outcome);
    const bool valid = enclosed && enclosed->basis == StructuralBasis::v_h_containment &&
        enclosed->result.relation == SetRelation::outer &&
        enclosed->result.evidence.reference.identity == request.identity &&
        exact_h(enclosed->result.output, Matrix{4, 2, {1, 0, -1, 0, 0, 1, 0, -1}},
                {2, 2, 2, 2});
    return {"axis-box", valid ? 16.0 : 0.0,
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count(), valid,
        valid ? "exact-v-h-containment" : "failed"};
}

Result parallelotope(const SetHandle& input) {
    registry::Registry<registry::ApproximationPort> methods;
    if (methods.add(make_parallelotope_registration({"approx-pilot-parallelotope"},
            Matrix{2, 2, {1, 1, 1, -1}})))
        throw std::runtime_error("Parallelotope registration failed");
    const registry::Method method{{"csl.approximation.parallelotope"}, std::nullopt};
    const ApproximationRequest request{{{"approx-pilot"}, {"parallelotope"}, {"diamond"}},
        input, {"csl.polyhedron.h"}, SetRelation::outer, 4, Assurance::numerical};
    const auto start = std::chrono::steady_clock::now();
    const auto outcome = run_registered(methods, method, request, ExecutionContext{});
    const auto stop = std::chrono::steady_clock::now();
    const auto* enclosed = std::get_if<EnclosedApproximation>(&outcome);
    const bool valid = enclosed && enclosed->basis == StructuralBasis::v_h_containment &&
        enclosed->result.relation == SetRelation::outer &&
        enclosed->result.evidence.reference.identity == request.identity &&
        exact_h(enclosed->result.output,
            Matrix{4, 2, {1, 1, -1, -1, 1, -1, -1, 1}}, {2, 2, 2, 2});
    return {"rotated-parallelotope", valid ? 8.0 : 0.0,
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count(), valid,
        valid ? "exact-v-h-containment" : "failed"};
}

Result zonotope_cover(const SetHandle& input) {
    registry::Registry<registry::ApproximationPort> methods;
    if (methods.add(make_axis_cover_registration({"approx-pilot-zonotope-cover"})))
        throw std::runtime_error("Zonotope cover registration failed");
    const registry::Method method{{"csl.geometry.zonotope.axis-cover"}, std::nullopt};
    const ApproximationRequest request{{{"approx-pilot"}, {"zonotope-cover"}, {"diamond"}},
        input, {"csl.zonotope"}, SetRelation::outer, 2, Assurance::numerical};
    const auto start = std::chrono::steady_clock::now();
    const auto outcome = run_registered(methods, method, request, ExecutionContext{});
    const auto stop = std::chrono::steady_clock::now();
    const auto* enclosed = std::get_if<EnclosedApproximation>(&outcome);
    bool valid = enclosed && enclosed->basis == StructuralBasis::generator_axis_cover &&
        enclosed->result.relation == SetRelation::outer &&
        enclosed->result.evidence.reference.identity == request.identity;
    double area = 0;
    if (valid) {
        const auto native = sets::from_generator_handle(enclosed->result.output);
        const auto* output = std::get_if<sets::GeneratorSet>(&native);
        valid = output && output->center() == Vector{0, 0} &&
            output->factor_ids().size() == 2 && output->generators().rows == 2 &&
            output->generators().cols == 2;
        if (valid) {
            const auto& g = output->generators().values;
            area = 4.0 * std::abs(g[0] * g[3] - g[1] * g[2]);
            const bool diagonal_axes = g[1] == 0 && g[2] == 0 &&
                std::abs(g[0]) == 2 && std::abs(g[3]) == 2;
            const bool swapped_axes = g[0] == 0 && g[3] == 0 &&
                std::abs(g[1]) == 2 && std::abs(g[2]) == 2;
            valid = area == 16.0 && (diagonal_axes || swapped_axes);
        }
    }
    return {"zonotope-axis-cover", valid ? area : 0.0,
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count(), valid,
        valid ? "exact-generator-axis-cover" : "failed"};
}

Result ellipsoid(const SetHandle& input) {
    registry::Registry<registry::ApproximationPort> methods;
    const registry::Method method{{"approx-pilot.ellipsoid"}, "1"};
    if (methods.add(make_directional_ellipsoid_registration(method,
            {"approx-pilot-ellipsoid"}, Matrix{2, 2, {1, 0, 0, 1}})))
        throw std::runtime_error("Ellipsoid registration failed");
    const ApproximationRequest request{{{"approx-pilot"}, {"ellipsoid"}, {"diamond"}},
        input, {"csl.ellipsoid.directional2d"}, SetRelation::outer, 1,
        Assurance::numerical};
    const auto start = std::chrono::steady_clock::now();
    const auto outcome = run_registered(methods, method, request, ExecutionContext{});
    const auto stop = std::chrono::steady_clock::now();
    const auto* enclosed = std::get_if<EnclosedApproximation>(&outcome);
    bool valid = enclosed && enclosed->basis == StructuralBasis::v_ellipsoid_containment &&
        enclosed->result.relation == SetRelation::outer &&
        enclosed->result.evidence.reference.identity == request.identity;
    double area = 0;
    if (valid) {
        const auto imported = ellipsoidal::from_ellipsoid_handle(enclosed->result.output);
        const auto* ellipse = std::get_if<ellipsoidal::EllipsoidSet>(&imported);
        valid = ellipse && ellipse->center() == Vector{0, 0} &&
            ellipse->orientation().values == Vector{1, 0, 0, 1} &&
            ellipse->projected_bounds() == Vector{2, 2} &&
            ellipse->radii()[0] >= std::sqrt(8.0) &&
            ellipse->radii()[1] >= std::sqrt(8.0);
        if (valid) area = std::acos(-1.0) * ellipse->radii()[0] * ellipse->radii()[1];
    }
    return {"directional-ellipsoid", valid ? area : 0.0,
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count(), valid,
        valid ? "exact-dyadic-v-ellipsoid-check" : "failed"};
}

void print(bool warmup, int round, const Result& result) {
    std::cout << "{\"schema\":\"csl.approximation-matched-pilot-row/1\",\"source_commit\":\""
              << CSL_SOURCE_COMMIT << "\",\"fixture\":\"diamond\",\"method\":\""
              << result.method << "\",\"warmup\":" << (warmup ? "true" : "false")
              << ",\"round\":" << round << ",\"elapsed_ns\":" << result.elapsed_ns
              << ",\"area\":" << result.area << ",\"area_ratio\":" << result.area / 8.0
              << ",\"passed\":" << (result.passed ? "true" : "false")
              << ",\"evidence\":\"" << result.evidence << "\"}\n";
}

using MethodFunction = Result (*)(const SetHandle&);
constexpr std::array<std::pair<const char*, MethodFunction>, 5> methods{{
    {"exact-polygon-quickhull", [](const SetHandle&) { return exact_hull(); }},
    {"axis-box", box},
    {"rotated-parallelotope", parallelotope},
    {"zonotope-axis-cover", zonotope_cover},
    {"directional-ellipsoid", ellipsoid},
}};

} // namespace

int main(int argc, char** argv) {
    std::cout << std::setprecision(std::numeric_limits<double>::max_digits10);
    int repetitions = 7;
    if (argc == 2 && std::string(argv[1]) == "--smoke") repetitions = 0;
    else if (argc == 2 && std::string(argv[1]) == "--measure") repetitions = 7;
    else if (argc != 1) return 2;
    try {
        const auto v = diamond_v();
        const auto z = diamond_generators();
        for (std::size_t i = 0; i < methods.size(); ++i) {
            const auto result = i == 0 ? methods[i].second(v) :
                (i == 3 ? methods[i].second(z) : methods[i].second(v));
            print(true, 0, result);
            if (!result.passed) throw std::runtime_error("warmup oracle failed");
        }
        for (int round = 1; round <= repetitions; ++round) {
            for (std::size_t offset = 0; offset < methods.size(); ++offset) {
                const auto i = (offset + static_cast<std::size_t>(round - 1)) % methods.size();
                const auto result = i == 0 ? methods[i].second(v) :
                    (i == 3 ? methods[i].second(z) : methods[i].second(v));
                print(false, round, result);
                if (!result.passed) throw std::runtime_error("measured output oracle failed");
            }
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
