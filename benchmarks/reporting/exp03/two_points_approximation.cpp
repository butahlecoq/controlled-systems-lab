#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <fstream>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

using namespace csl;
using namespace csl::geometry::approximation;
using Json = nlohmann::json;

namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("A required geometry operation was not accepted");
    return std::get<T>(std::move(value));
}

sets::SetData make_v(std::string id, std::size_t dimension, Matrix points,
                     std::vector<std::string> labels) {
    const auto vertices = numeric::snapshot(points);
    const auto rays = numeric::snapshot(Matrix{0, dimension, {}});
    const auto vertex_view = take<numeric::MatrixView>(vertices);
    const auto ray_view = take<numeric::MatrixView>(rays);
    return take<sets::SetData>(sets::make_v(
        {{std::move(id)}, dimension, std::move(labels)}, {vertex_view, ray_view}));
}

sets::GeneratorSet make_zonotope(std::string id, const Json& source,
                                 const std::vector<std::string>& labels,
                                 std::size_t scale) {
    // The rational reference is serialized as binary64. Inflate each lattice
    // generator slightly so the binary64 source zonotope encloses those
    // serialized reference vertices despite independent rounding of the
    // center, generators, and point coordinates.
    constexpr double outward_padding = 1.0 + 0x1p-32;
    Vector center;
    for (const auto& coordinate : source.at("center"))
        center.push_back(coordinate.get<double>() / static_cast<double>(scale));
    const auto& columns = source.at("generator_columns");
    Matrix generators{2, columns.size(), Vector(2 * columns.size())};
    std::vector<sets::FactorId> factors;
    for (std::size_t column = 0; column < columns.size(); ++column) {
        factors.push_back({"two-points-factor-" + std::to_string(column)});
        for (std::size_t row = 0; row < 2; ++row)
            generators.values[row * columns.size() + column] =
                columns.at(column).at(row).get<double>() /
                static_cast<double>(scale) * outward_padding;
    }
    return take<sets::GeneratorSet>(sets::make_generator_set(
        {{std::move(id)}, std::move(center), std::move(generators), std::move(factors),
         Matrix{0, columns.size(), {}}, {}, labels}));
}

Json vector_json(const Vector& values) { return Json(values); }
Json vector_json(const numeric::VectorView& values) {
    Json result = Json::array();
    for (std::size_t index = 0; index < values.size(); ++index) result.push_back(values[index]);
    return result;
}
Json points_json(const std::vector<Vector>& points) {
    Json result = Json::array();
    for (const auto& point : points) result.push_back(point);
    return result;
}
Json matrix_json(const Matrix& matrix) {
    Json rows = Json::array();
    for (std::size_t row = 0; row < matrix.rows; ++row) {
        Json values = Json::array();
        for (std::size_t column = 0; column < matrix.cols; ++column)
            values.push_back(matrix.values[row * matrix.cols + column]);
        rows.push_back(std::move(values));
    }
    return rows;
}
Json matrix_json(const numeric::MatrixView& matrix) {
    Json rows = Json::array();
    for (std::size_t row = 0; row < matrix.rows(); ++row) {
        Json values = Json::array();
        for (std::size_t column = 0; column < matrix.cols(); ++column)
            values.push_back(matrix(row, column));
        rows.push_back(std::move(values));
    }
    return rows;
}

struct ProjectedInput {
    SetHandle set;
    std::vector<Vector> points;
    std::size_t projection_ns{};
    Json projection_evidence;
};

ProjectedInput project_input(const Json& layer, const std::vector<std::size_t>& pair,
                             const std::vector<std::string>& labels,
                             std::size_t projection_index, std::size_t scale,
                             bool measure) {
    const auto& states = layer.at("finite_states_scaled");
    constexpr std::size_t dimension = 4;
    const auto scale_value = static_cast<double>(scale);
    Matrix source_points{states.size(), dimension,
                         Vector(states.size() * dimension)};
    for (std::size_t row = 0; row < states.size(); ++row)
        for (std::size_t column = 0; column < dimension; ++column)
            source_points.values[row * dimension + column] =
                states.at(row).at(column).get<double>() / scale_value;
    auto source = make_v("env717-two-points-stage-3-v", dimension,
        std::move(source_points), {"position_1", "velocity_1", "position_2", "velocity_2"});
    auto registration = geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::v, {}});
    registry::Registry<registry::GeometryPort> registry;
    if (registry.add(std::move(registration)))
        throw std::runtime_error("Projection registration failed");
    const registry::Method method{{"csl.geometry.polyhedral-projection"}, "1.0.0"};
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.relation = SetRelation::equivalent;
    auto provider = take<registry::PreparedProvider<registry::GeometryPort>>(
        registry::prepare_provider(registry::select_provider(registry, method, requirements)));
    const auto request_id = "env717-projection-" + std::to_string(projection_index);
    OperationRequest request{{{"env717-exp03"}, {request_id}, {"projected-reference"}},
        {"csl.geometry.polyhedral-projection"},
        Projection{source.as_handle(), pair}, SetRelation::equivalent, Assurance::numerical};
    const auto start = std::chrono::steady_clock::now();
    auto prepared = take(provider.prepare(request));
    auto [workspace] = prepared.create();
    auto outcome = workspace->run(ExecutionContext{});
    const auto stop = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
    auto result = take<OperationResult>(std::move(outcome));
    if (result.relation != SetRelation::equivalent)
        throw std::runtime_error("Projection provider changed the requested relation");
    auto data = take<sets::SetData>(sets::from_handle(result.output));
    const auto representation = data.representation();
    const auto* v = std::get_if<sets::VRepresentation>(&representation);
    if (!v || v->rays.rows() != 0)
        throw std::runtime_error("Projected reference is not bounded native V data");
    std::set<std::pair<double, double>> unique;
    for (std::size_t row = 0; row < v->vertices.rows(); ++row)
        unique.emplace(v->vertices(row, 0), v->vertices(row, 1));
    Matrix projected{unique.size(), 2, {}};
    std::vector<Vector> points;
    for (const auto& [x, y] : unique) {
        projected.values.push_back(x);
        projected.values.push_back(y);
        points.push_back({x, y});
    }
    auto projected_set = make_v("env717-two-points-phase-plane-" +
        std::to_string(projection_index), 2, std::move(projected), labels);
    return {projected_set.as_handle(), std::move(points),
        measure ? static_cast<std::size_t>(elapsed) : 0,
        {{"module", "csl.geometry.polyhedral-projection"}, {"version", "1.0.0"},
         {"request", request_id}, {"relation", "equivalent"},
         {"input_states", states.size()}, {"projected_unique_points", unique.size()},
         {"labels", labels}}};
}

struct Attempt {
    std::string id;
    Json shape;
    std::function<std::pair<Json, std::int64_t>(bool)> run;
};

Json approx_shape(const EnclosedApproximation& enclosed) {
    const auto native = sets::from_handle(enclosed.result.output);
    if (const auto* data = std::get_if<sets::SetData>(&native)) {
        const auto representation = data->representation();
        if (const auto* h = std::get_if<sets::HRepresentation>(&representation))
            return {{"kind", "h_polytope"}, {"inequality_rows", matrix_json(h->inequalities)},
                {"inequality_bounds", vector_json(h->upper_bounds)},
                {"equality_rows", matrix_json(h->equalities)},
                {"equality_bounds", vector_json(h->equality_values)},
                {"coordinate_labels", data->metadata()->coordinate_labels}};
    }
    const auto ellipse = geometry::ellipsoidal::from_ellipsoid_handle(enclosed.result.output);
    if (const auto* value = std::get_if<geometry::ellipsoidal::EllipsoidSet>(&ellipse))
        return {{"kind", "directional_ellipsoid"}, {"center", vector_json(value->center())},
            {"orientation", matrix_json(value->orientation())},
            {"projected_bounds", vector_json(value->projected_bounds())},
            {"radii", vector_json(value->radii())},
            {"coordinate_labels", value->coordinate_labels()}};
    const auto zonotope = sets::from_generator_handle(enclosed.result.output);
    if (const auto* value = std::get_if<sets::GeneratorSet>(&zonotope)) {
        Json factors = Json::array();
        for (const auto& factor : value->factor_ids()) factors.push_back(factor.value);
        return {{"kind", "zonotope"}, {"center", vector_json(value->center())},
            {"generators", matrix_json(value->generators())}, {"factors", factors},
            {"coordinate_labels", value->coordinate_labels()}};
    }
    throw std::runtime_error("Approximation returned an unsupported native output shape");
}

Json method_description(const EnclosedApproximation& enclosed) {
    std::string basis;
    switch (enclosed.basis) {
    case StructuralBasis::identical_set: basis = "identical_set"; break;
    case StructuralBasis::empty_subset: basis = "empty_subset"; break;
    case StructuralBasis::universal_superset: basis = "universal_superset"; break;
    case StructuralBasis::h_constraint_containment: basis = "h_constraint_containment"; break;
    case StructuralBasis::h_point_containment: basis = "h_point_containment"; break;
    case StructuralBasis::v_h_containment: basis = "v_h_containment"; break;
    case StructuralBasis::h_v_containment: basis = "h_v_containment"; break;
    case StructuralBasis::generator_axis_cover: basis = "generator_axis_cover"; break;
    case StructuralBasis::v_ellipsoid_containment: basis = "v_ellipsoid_containment"; break;
    }
    return {{"status", "completed"}, {"direction", "outer"},
        {"relation_basis", basis},
        {"shape", approx_shape(enclosed)},
        {"evidence_assumptions", enclosed.result.evidence.assumptions}};
}

Json diagnostics_json(const Diagnostics& diagnostics) {
    Json result = Json::array();
    for (const auto& diagnostic : diagnostics)
        result.push_back({{"code", static_cast<int>(diagnostic.code)},
            {"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
    return result;
}

Json registered_outcome_description(const RunOutcome& outcome) {
    if (const auto* enclosed = std::get_if<EnclosedApproximation>(&outcome))
        return method_description(*enclosed);
    if (const auto* heuristic = std::get_if<HeuristicApproximation>(&outcome))
        return {{"status", "heuristic"}, {"direction", "heuristic"},
            {"evidence_assumptions", heuristic->result.evidence.assumptions}};
    if (const auto* rejected = std::get_if<registry::Rejection>(&outcome))
        return {{"status", "rejected"}, {"requested_method", rejected->provenance.requested.id.value},
            {"diagnostics", diagnostics_json(rejected->diagnostics)}};
    if (const auto* stopped = std::get_if<OperationStopped>(&outcome))
        return {{"status", "stopped"}, {"reason", static_cast<int>(stopped->reason)},
            {"diagnostics", stopped->diagnostics}};
    const auto& unsupported = std::get<Unsupported>(outcome);
    return {{"status", "unsupported"}, {"diagnostics", diagnostics_json(unsupported.diagnostics)}};
}

Attempt exact_hull(const std::vector<Vector>& points) {
    const auto id = std::string("exact-polytope-quickhull");
    auto run = [points](bool timed) {
        const auto start = std::chrono::steady_clock::now();
        auto outcome = geometry::quickhull_2d(points);
        const auto stop = std::chrono::steady_clock::now();
        const auto* hull = std::get_if<geometry::QuickHull2D>(&outcome);
        if (!hull) {
            const auto& diagnostics = std::get<Diagnostics>(outcome);
            return std::pair<Json, std::int64_t>{
                {{"status", "refused"}, {"direction", "equivalent"},
                 {"diagnostics", diagnostics_json(diagnostics)}},
                timed ? std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count() : 0};
        }
        Json vertices = Json::array();
        for (const auto index : hull->vertex_indices) {
            if (index >= points.size()) throw std::runtime_error("QuickHull returned an invalid index");
            vertices.push_back(points[index]);
        }
        return std::pair<Json, std::int64_t>{
            {{"status", "completed"}, {"direction", "equivalent"},
             {"method_id", "csl.quickhull_2d"}, {"method_version", "unregistered"},
             {"shape", {{"kind", "v_polytope"}, {"vertices", std::move(vertices)}}},
             {"output_vertices", hull->vertex_indices.size()}},
            timed ? std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count() : 0};
    };
    return {id, Json::object(), std::move(run)};
}

Attempt approximation(std::string id, const SetHandle& input,
                      registry::Registry<registry::ApproximationPort> methods,
                      registry::Method method, std::string representation,
                      std::size_t budget, Json extra = Json::object()) {
    const ApproximationRequest request{{{"env717-exp03"}, {id}, {"phase-plane-reference"}},
        input, {representation}, SetRelation::outer, budget, Assurance::numerical};
    auto run = [methods = std::move(methods), method = std::move(method), request, budget,
                extra = std::move(extra)](bool timed) mutable {
        const auto start = std::chrono::steady_clock::now();
        auto outcome = run_registered(methods, method, request, ExecutionContext{});
        const auto stop = std::chrono::steady_clock::now();
        auto description = registered_outcome_description(outcome);
        description["method_id"] = method.id.value;
        description["method_version"] = method.version.value_or("");
        description["size_budget"] = budget;
        if (!extra.empty()) description["method_parameters"] = extra;
        return std::pair<Json, std::int64_t>{description,
            timed ? std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count() : 0};
    };
    return {std::move(id), Json::object(), std::move(run)};
}

std::vector<Attempt> methods_for(ProjectedInput& input, const Json& projected_zonotope,
                                 const std::vector<std::string>& labels,
                                 std::size_t scale) {
    std::vector<Attempt> methods;
    methods.push_back(exact_hull(input.points));

    registry::Registry<registry::ApproximationPort> box_methods;
    if (box_methods.add(geometry::approximation::make_box_registration({"exp03-box-output"})))
        throw std::runtime_error("Box registration failed");
    methods.push_back(approximation("axis-box", input.set, std::move(box_methods),
        {{"csl.approximation.box"}, "1"}, "csl.polyhedron.h", 4));

    const Matrix orientation{2, 2, {1.0, 0.3, 0.4, 1.0}};
    registry::Registry<registry::ApproximationPort> parallelotope_methods;
    if (parallelotope_methods.add(geometry::approximation::make_parallelotope_registration(
            {"exp03-parallelotope-output"}, orientation)))
        throw std::runtime_error("Parallelotope registration failed");
    methods.push_back(approximation("rotated-parallelotope", input.set,
        std::move(parallelotope_methods), {{"csl.approximation.parallelotope"}, "1"},
        "csl.polyhedron.h", 4, {{"orientation", matrix_json(orientation)}}));

    registry::Registry<registry::ApproximationPort> ellipsoid_methods;
    const registry::Method ellipsoid_method{{"csl.approximation.ellipsoid.exp03"}, "1"};
    if (ellipsoid_methods.add(geometry::approximation::make_directional_ellipsoid_registration(
            ellipsoid_method, {"exp03-ellipsoid-output"}, orientation)))
        throw std::runtime_error("Ellipsoid registration failed");
    methods.push_back(approximation("directional-ellipsoid", input.set,
        std::move(ellipsoid_methods), ellipsoid_method, "csl.ellipsoid.directional2d", 1,
        {{"orientation", matrix_json(orientation)}}));

    auto zonotope = make_zonotope("exp03-exact-projected-zonotope", projected_zonotope,
        labels, scale);
    registry::Registry<registry::ApproximationPort> zonotope_methods;
    if (zonotope_methods.add(geometry::approximation::make_axis_cover_registration(
            {"exp03-zonotope-cover-output"})))
        throw std::runtime_error("Zonotope registration failed");
    const auto zone_method = registry::Method{{"csl.geometry.zonotope.axis-cover"}, "1.0.0"};
    const ApproximationRequest zone_request{{{"env717-exp03"}, {"zonotope-axis-cover"},
        {"phase-plane-reference"}}, zonotope.as_handle(), {"csl.zonotope"},
        SetRelation::outer, 4, Assurance::numerical};
    const auto source_center = zonotope.center();
    const auto source_generators = zonotope.generators();
    Json source_factors = Json::array();
    for (const auto& factor : zonotope.factor_ids()) source_factors.push_back(factor.value);
    const Json source_description{{"center", vector_json(source_center)},
        {"generators", matrix_json(source_generators)}, {"factors", source_factors},
        {"outer_padding_factor", 1.0 + 0x1p-32}};
    auto zone_run = [methods = std::move(zonotope_methods), zone_method, zone_request,
                     source_description](bool timed) mutable {
        const auto start = std::chrono::steady_clock::now();
        auto outcome = run_registered(methods, zone_method, zone_request, ExecutionContext{});
        const auto stop = std::chrono::steady_clock::now();
        auto zone_description = registered_outcome_description(outcome);
        zone_description["method_id"] = zone_method.id.value;
        zone_description["method_version"] = zone_method.version.value_or("");
        zone_description["size_budget"] = zone_request.size_budget;
        zone_description["source_zonotope"] = source_description;
        return std::pair<Json, std::int64_t>{zone_description,
            timed ? std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count() : 0};
    };
    methods.push_back({"zonotope-axis-cover", Json::object(), std::move(zone_run)});
    return methods;
}

Json run(const Json& reference, bool measure) {
    const auto stage = reference.at("layers").size() - 1;
    const auto scale = reference.at("finite_game").at("state_scale").get<std::size_t>();
    const auto& pairs = reference.at("projection_pairs");
    const auto& labels = reference.at("projection_labels");
    const auto& stage_data = reference.at("layers").at(stage);
    Json projection_data = Json::array();
    Json measurements = Json::array();
    for (std::size_t projection_index = 0; projection_index < pairs.size(); ++projection_index) {
        const auto pair = pairs.at(projection_index).get<std::vector<std::size_t>>();
        const auto projection_labels = labels.at(projection_index).get<std::vector<std::string>>();
        auto input = project_input(stage_data, pair, projection_labels, projection_index,
            scale, measure);
        const auto& zone = stage_data.at("projected_zonotopes_scaled").at(projection_index);
        auto methods = methods_for(input, zone, projection_labels, scale);
        Json method_results = Json::array();
        const auto invoke = [](Attempt& method, bool timed) {
            try {
                return method.run(timed);
            } catch (const std::exception& error) {
                return std::pair<Json, std::int64_t>{
                    {{"status", "failed"}, {"reason", error.what()}}, -1};
            }
        };
        if (measure) {
            for (auto& method : methods) {
                const auto warmup = invoke(method, false).first;
                measurements.push_back({{"projection_index", projection_index},
                    {"method", method.id}, {"phase", "warmup"},
                    {"status", warmup.at("status")}, {"result", warmup}});
            }
            constexpr int repetitions = 7;
            for (int repetition = 0; repetition < repetitions; ++repetition) {
                for (std::size_t offset = 0; offset < methods.size(); ++offset) {
                    auto& method = methods[(offset + static_cast<std::size_t>(repetition)) % methods.size()];
                    auto [outcome, elapsed_ns] = invoke(method, true);
                    measurements.push_back({{"projection_index", projection_index},
                        {"method", method.id}, {"phase", "measured"},
                        {"repetition", repetition}, {"elapsed_ns", elapsed_ns},
                        {"status", outcome.at("status")}, {"result", outcome}});
                    if (repetition == 0)
                        method_results.push_back({{"method", method.id}, {"result", outcome}});
                }
            }
        } else {
            for (auto& method : methods) {
                auto [outcome, _] = invoke(method, false);
                method_results.push_back({{"method", method.id}, {"result", outcome}});
            }
        }
        projection_data.push_back({{"coordinate_indices", pair}, {"coordinate_labels", projection_labels},
            {"input_point_count", input.points.size()}, {"input_points", points_json(input.points)},
            {"projection_elapsed_ns", input.projection_ns},
            {"projection_evidence", input.projection_evidence}, {"methods", method_results}});
    }
    const Json inner_methods = Json::array({Json{{"method", "native-inscribed-box"},
        {"status", "not-requested; this run compares exact and outer sets"}}});
    return {{"schema", "csl.exp03-two-points-approximation-run/1"},
        {"case_id", reference.at("case_id")}, {"environment_report", reference.at("environment_report")},
        {"reference_source_figure_data_sha256", reference.at("source_figure_data_sha256")},
        {"stage", stage}, {"set_meaning", reference.at("finite_game").at("set_meaning")},
        {"measurement_policy", measure ? Json{{"warmup_per_method", 1},
            {"measured_repetitions_per_method", 7}, {"method_order", "rotating alternating order"},
            {"timed_scope", "native public hull or approximation operation call; input construction and JSON output excluded"},
            {"requested_outer_workers", 1}, {"actual_outer_workers", 1},
            {"requested_native_threads", 1}, {"actual_native_threads", 1},
            {"actual_native_threads_status", "inferred; OS thread count not observed"},
            {"thread_evidence", "single-threaded driver; no parallel executor invoked"},
            {"workspace_policy", {
                {"quickhull", "stateless direct call; no workspace"},
                {"registered_approximation", "run_registered prepares a fresh pipeline workspace for each warmup and measured call; no workspace reuse"}}}}
            : Json{{"status", "smoke-only; no performance measurements"}}},
        {"projections", projection_data}, {"measurements", measurements},
        {"inner_methods", inner_methods}};
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3 || (std::string_view(argv[1]) != "smoke" &&
                          std::string_view(argv[1]) != "measure"))
            throw std::invalid_argument("usage: csl_exp03_two_points_approximation <smoke|measure> <reference.json>");
        std::ifstream input(argv[2]);
        if (!input) throw std::runtime_error("Cannot open the verified reference input");
        Json reference;
        input >> reference;
        std::cout << run(reference, std::string_view(argv[1]) == "measure").dump(2) << '\n';
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "EXP-03 TwoPoints approximation failed: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
