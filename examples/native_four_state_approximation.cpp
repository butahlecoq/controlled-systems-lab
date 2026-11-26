#include "native_catalogue_projection.hpp"

#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/geometry/generators.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numbers>
#include <numeric>
#include <optional>
#include <string>
#include <string_view>
#include <stdexcept>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using native_catalogue_example::Cloud;
using Clock = std::chrono::steady_clock;
using Point = std::array<double, 2>;

constexpr std::size_t repetitions = 5;
constexpr std::size_t support_directions = 64;
constexpr std::size_t zonotope_budget = 8;
constexpr double orientation_component = 0.7071067811865475244;
const Matrix rotated_axes{
    2,
    2,
    {orientation_component, orientation_component, -orientation_component, orientation_component}};

struct ProjectedSet {
    std::size_t stage;
    std::string id;
    std::string x_name;
    std::string y_name;
    sets::GeneratorSet exact;
    std::vector<Point> boundary;
    sets::SetData vertices;
    double area{};
};

struct Approximation {
    std::string method;
    std::string version;
    std::string representation;
    std::string admission;
    double area{};
    double area_ratio{};
    std::size_t primitives{};
    std::vector<Point> boundary;
    std::array<std::int64_t, repetitions> elapsed_ns{};
};

template <class T, class... Errors> T take(std::variant<T, Errors...> result, const char *label) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    throw std::runtime_error(std::string("Four-state approximation failed: ") + label);
}

double signed_area(const std::vector<Point> &polygon) {
    if (polygon.size() < 3)
        return 0.0;
    long double twice = 0.0L;
    for (std::size_t i = 0; i < polygon.size(); ++i) {
        const auto &p = polygon[i];
        const auto &q = polygon[(i + 1) % polygon.size()];
        twice += static_cast<long double>(p[0]) * q[1] - static_cast<long double>(p[1]) * q[0];
    }
    return static_cast<double>(std::abs(twice) / 2.0L);
}

std::vector<Point> hull(const Cloud &points) {
    const auto result = native_catalogue_example::projected_hull(points);
    std::vector<Point> polygon;
    polygon.reserve(result.vertex_indices.size());
    for (const auto index : result.vertex_indices)
        polygon.push_back({points[index][0], points[index][1]});
    return polygon;
}

std::vector<Point> zonotope_boundary(const sets::GeneratorSet &set) {
    const auto &matrix = set.generators();
    const auto count = set.factor_ids().size();
    if (matrix.rows != 2 || matrix.cols != count)
        throw std::runtime_error("Projected zonotope shape differs from its factor IDs");
    Cloud current{{set.center()[0], set.center()[1]}};
    for (std::size_t factor = 0; factor < count; ++factor) {
        Cloud candidates;
        candidates.reserve(current.size() * 2);
        for (const auto &point : current) {
            for (const double sign : {-1.0, 1.0}) {
                candidates.push_back({point[0] + sign * matrix.values[factor],
                                      point[1] + sign * matrix.values[count + factor]});
            }
        }
        const auto vertices = native_catalogue_example::projected_hull(candidates);
        current.clear();
        current.reserve(vertices.vertex_indices.size());
        for (const auto index : vertices.vertex_indices)
            current.push_back(std::move(candidates[index]));
    }
    return hull(current);
}

sets::GeneratorSet project(const sets::GeneratorSet &set, std::size_t x, std::size_t y,
                           const std::string &id) {
    const auto count = set.factor_ids().size();
    sets::GeneratorInput input{};
    input.id.value = id;
    input.center = {set.center()[x], set.center()[y]};
    input.generators.rows = 2;
    input.generators.cols = count;
    input.generators.values.resize(2 * count);
    input.factor_ids = set.factor_ids();
    input.equalities.rows = 0;
    input.equalities.cols = count;
    input.coordinate_labels = {"x" + std::to_string(x + 1), "x" + std::to_string(y + 1)};
    for (std::size_t column = 0; column < count; ++column) {
        input.generators.values[column] = set.generators().values[x * count + column];
        input.generators.values[count + column] = set.generators().values[y * count + column];
    }
    return take(sets::make_generator_set(std::move(input)), "project generator set");
}

sets::SetData vertex_set(const std::vector<Point> &polygon, const std::string &id,
                         const std::string &x_name, const std::string &y_name) {
    if (polygon.size() < 3)
        throw std::runtime_error("Projected reference is degenerate");
    Vector values;
    values.reserve(polygon.size() * 2);
    for (const auto &point : polygon) {
        values.push_back(point[0]);
        values.push_back(point[1]);
    }
    const auto vertices = numeric::snapshot(Matrix{polygon.size(), 2, std::move(values)});
    const auto rays = numeric::snapshot(Matrix{0, 2, {}});
    if (!std::holds_alternative<numeric::MatrixView>(vertices) ||
        !std::holds_alternative<numeric::MatrixView>(rays))
        throw std::runtime_error("Projected V representation could not be snapshotted");
    return take(sets::make_v({{id}, 2, {x_name, y_name}}, {std::get<numeric::MatrixView>(vertices),
                                                           std::get<numeric::MatrixView>(rays)}),
                "make projected V set");
}

std::vector<Point> h_polygon(const SetHandle &handle) {
    const auto native = sets::from_handle(handle);
    const auto *data = std::get_if<sets::SetData>(&native);
    if (!data)
        throw std::runtime_error("H approximation output is not a native set");
    const auto representation = data->representation();
    const auto *h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->inequalities.cols() != 2 || h->equalities.rows() != 0)
        throw std::runtime_error("Expected a two-dimensional bounded H output");
    Cloud candidates;
    for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
        for (std::size_t j = i + 1; j < h->inequalities.rows(); ++j) {
            const double a = h->inequalities(i, 0), b = h->inequalities(i, 1);
            const double c = h->inequalities(j, 0), d = h->inequalities(j, 1);
            const double determinant = a * d - b * c;
            if (std::abs(determinant) <= 64 * std::numeric_limits<double>::epsilon())
                continue;
            const double u = (h->upper_bounds[i] * d - b * h->upper_bounds[j]) / determinant;
            const double v = (a * h->upper_bounds[j] - h->upper_bounds[i] * c) / determinant;
            bool feasible = true;
            for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
                const double lhs = h->inequalities(row, 0) * u + h->inequalities(row, 1) * v;
                const double tolerance = 1e-10 * (1.0 + std::abs(h->upper_bounds[row]));
                feasible &= lhs <= h->upper_bounds[row] + tolerance;
            }
            if (feasible)
                candidates.push_back({u, v});
        }
    }
    return hull(candidates);
}

std::vector<Point> ellipsoid_boundary(const geometry::ellipsoidal::EllipsoidSet &set,
                                      std::size_t samples = 128) {
    const auto &b = set.orientation().values;
    const double determinant = b[0] * b[3] - b[1] * b[2];
    if (determinant == 0.0)
        throw std::runtime_error("Ellipsoid orientation is singular");
    const auto &r = set.radii();
    std::vector<Point> result;
    result.reserve(samples);
    for (std::size_t i = 0; i < samples; ++i) {
        const double angle = 2 * std::numbers::pi * static_cast<double>(i) / samples;
        const double y = r[0] * std::cos(angle), z = r[1] * std::sin(angle);
        result.push_back({set.center()[0] + (b[3] * y - b[1] * z) / determinant,
                          set.center()[1] + (-b[2] * y + b[0] * z) / determinant});
    }
    return result;
}

double support(const sets::GeneratorSet &set, const Point &direction) {
    long double result = direction[0] * set.center()[0] + direction[1] * set.center()[1];
    const auto count = set.factor_ids().size();
    for (std::size_t j = 0; j < count; ++j)
        result += std::abs(direction[0] * set.generators().values[j] +
                           direction[1] * set.generators().values[count + j]);
    return static_cast<double>(result);
}

double support(const std::vector<Point> &polygon, const Point &direction) {
    double result = -std::numeric_limits<double>::infinity();
    for (const auto &point : polygon)
        result = std::max(result, point[0] * direction[0] + point[1] * direction[1]);
    return result;
}

template <class Factory>
Approximation
run_v_adapter(const ProjectedSet &projection, const std::string &method, const std::string &version,
              const std::string &output_rep, const std::string &admission, std::size_t budget,
              Factory make_registration, const registry::Method &selected, std::size_t repetition) {
    registry::Registry<registry::ApproximationPort> registry;
    const auto output_id = projection.id + "/" + method + "/output";
    if (registry.add(make_registration({output_id})))
        throw std::runtime_error("Approximation registration failed: " + method);
    const auto request_id = projection.id + "/" + method + "/request";
    const ApproximationRequest request{{{"archival-2017-4d-projection-approx"},
                                        {request_id},
                                        {projection.id + "/exact-generator-projection"}},
                                       projection.vertices.as_handle(),
                                       {output_rep},
                                       SetRelation::outer,
                                       budget,
                                       Assurance::numerical};
    const auto start = Clock::now();
    const auto outcome =
        geometry::approximation::run_registered(registry, selected, request, ExecutionContext{});
    const auto elapsed =
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    const auto *enclosed = std::get_if<geometry::approximation::EnclosedApproximation>(&outcome);
    if (!enclosed)
        throw std::runtime_error("Approximation was not independently admitted: " + method);

    Approximation result{method, version, output_rep, admission, 0.0, 0.0, 0, {}, {}};
    if (output_rep == "csl.polyhedron.h") {
        result.boundary = h_polygon(enclosed->result.output);
        const auto data = take(sets::from_handle(enclosed->result.output), "read H output");
        result.primitives =
            std::get<sets::HRepresentation>(data.representation()).inequalities.rows();
    } else if (output_rep == "csl.ellipsoid.directional2d") {
        const auto ellipsoid =
            take(geometry::ellipsoidal::from_ellipsoid_handle(enclosed->result.output),
                 "read ellipsoid output");
        result.boundary = ellipsoid_boundary(ellipsoid);
        const auto &b = ellipsoid.orientation().values;
        result.area = std::numbers::pi * ellipsoid.radii()[0] * ellipsoid.radii()[1] /
                      std::abs(b[0] * b[3] - b[1] * b[2]);
        result.primitives = 1;
    } else {
        const auto zonotope =
            take(sets::from_generator_handle(enclosed->result.output), "read zonotope output");
        result.boundary = zonotope_boundary(zonotope);
        result.primitives = zonotope.factor_ids().size();
    }
    if (result.area == 0.0)
        result.area = signed_area(result.boundary);
    result.elapsed_ns[repetition] = elapsed;
    return result;
}

Approximation run_zonotope_adapter(const ProjectedSet &projection, std::size_t repetition) {
    constexpr std::string_view id = "csl.geometry.zonotope.axis-cover";
    registry::Registry<registry::ApproximationPort> registry;
    if (registry.add(geometry::approximation::make_axis_cover_registration(
            {projection.id + "/zonotope-axis-cover/output"})))
        throw std::runtime_error("Zonotope cover registration failed");
    const registry::Method method{{std::string(id)}, "1.0.0"};
    const ApproximationRequest request{{{"archival-2017-4d-projection-approx"},
                                        {projection.id + "/zonotope-axis-cover/request"},
                                        {projection.id + "/exact-generator-projection"}},
                                       projection.exact.as_handle(),
                                       {"csl.zonotope"},
                                       SetRelation::outer,
                                       zonotope_budget,
                                       Assurance::numerical};
    const auto start = Clock::now();
    const auto outcome =
        geometry::approximation::run_registered(registry, method, request, ExecutionContext{});
    const auto elapsed =
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    const auto *enclosed = std::get_if<geometry::approximation::EnclosedApproximation>(&outcome);
    if (!enclosed ||
        enclosed->basis != geometry::approximation::StructuralBasis::generator_axis_cover)
        throw std::runtime_error("Zonotope axis-cover inclusion admission failed");
    const auto output =
        take(sets::from_generator_handle(enclosed->result.output), "read zonotope cover output");
    Approximation result{"zonotope-axis-cover",
                         "1.0.0",
                         "csl.zonotope",
                         "generator_axis_cover",
                         0.0,
                         0.0,
                         output.factor_ids().size(),
                         zonotope_boundary(output),
                         {}};
    result.area = signed_area(result.boundary);
    result.elapsed_ns[repetition] = elapsed;
    return result;
}

Approximation run_box(const ProjectedSet &projection, std::size_t repetition) {
    const registry::Method method{{"csl.approximation.box"}, "1"};
    return run_v_adapter(projection, "box", "1", "csl.polyhedron.h", "v_h_containment", 4,
                         geometry::approximation::make_box_registration, method, repetition);
}

Approximation run_parallelotope(const ProjectedSet &projection, std::size_t repetition) {
    const registry::Method method{{"csl.approximation.parallelotope"}, "1"};
    return run_v_adapter(
        projection, "parallelotope-fixed-45deg", "1", "csl.polyhedron.h", "v_h_containment", 4,
        [orientation = rotated_axes](SetId output) {
            return geometry::approximation::make_parallelotope_registration(std::move(output),
                                                                            orientation);
        },
        method, repetition);
}

Approximation run_ellipsoid(const ProjectedSet &projection, std::size_t repetition) {
    const registry::Method method{{"csl.example.four-state.ellipsoid-fixed-45deg"}, "1"};
    return run_v_adapter(
        projection, "ellipsoid-fixed-45deg", "1", "csl.ellipsoid.directional2d",
        "v_ellipsoid_containment", 1,
        [method, orientation = rotated_axes](SetId output) {
            return geometry::approximation::make_directional_ellipsoid_registration(
                method, std::move(output), orientation);
        },
        method, repetition);
}

std::array<std::string, 4> method_names() {
    return {"box", "parallelotope-fixed-45deg", "zonotope-axis-cover", "ellipsoid-fixed-45deg"};
}

std::vector<Approximation> approximate(const ProjectedSet &projection) {
    std::array<std::array<std::optional<Approximation>, repetitions>, 4> saved{};
    for (std::size_t repetition = 0; repetition < repetitions; ++repetition) {
        for (std::size_t offset = 0; offset < 4; ++offset) {
            const auto method = (offset + repetition + projection.stage) % 4;
            Approximation result;
            switch (method) {
            case 0:
                result = run_box(projection, repetition);
                break;
            case 1:
                result = run_parallelotope(projection, repetition);
                break;
            case 2:
                result = run_zonotope_adapter(projection, repetition);
                break;
            case 3:
                result = run_ellipsoid(projection, repetition);
                break;
            default:
                throw std::runtime_error("Unexpected approximation method index");
            }
            if (repetition != 0) {
                const auto &first = *saved[method][0];
                if (std::abs(result.area - first.area) > 1e-10 * (1.0 + first.area) ||
                    result.primitives != first.primitives || result.admission != first.admission)
                    throw std::runtime_error("Repeated approximation output changed");
            }
            saved[method][repetition] = std::move(result);
        }
    }
    std::vector<Approximation> results;
    for (std::size_t method = 0; method < saved.size(); ++method) {
        auto result = std::move(*saved[method][0]);
        result.method = method_names()[method];
        result.area_ratio = result.area / projection.area;
        for (std::size_t repetition = 1; repetition < repetitions; ++repetition)
            result.elapsed_ns[repetition] = saved[method][repetition]->elapsed_ns[repetition];
        results.push_back(std::move(result));
    }
    return results;
}

double median(std::array<std::int64_t, repetitions> values) {
    std::sort(values.begin(), values.end());
    return static_cast<double>(values[repetitions / 2]);
}

Matrix copy_matrix(const numeric::MatrixView &view) {
    Vector values;
    values.reserve(view.rows() * view.cols());
    for (std::size_t row = 0; row < view.rows(); ++row)
        for (std::size_t column = 0; column < view.cols(); ++column)
            values.push_back(view(row, column));
    return Matrix{view.rows(), view.cols(), std::move(values)};
}

double support_of_ellipsoid(const Approximation &approximation, const Point &direction) {
    // Ellipsoid curves use 128 points for drawing; sampled support is retained as
    // a diagnostic only. The policy's structural admission is the enclosure claim.
    return support(approximation.boundary, direction);
}

void write_csv(const std::filesystem::path &output,
               const std::vector<std::pair<ProjectedSet, std::vector<Approximation>>> &rows) {
    std::ofstream summary(output / "approximation-summary.csv");
    std::ofstream support_rows(output / "support-samples.csv");
    summary.exceptions(std::ios::badbit | std::ios::failbit);
    support_rows.exceptions(std::ios::badbit | std::ios::failbit);
    summary
        << std::setprecision(17)
        << "stage,projection,reference_vertices,reference_area,method,version,representation,output_primitives,admission,output_area,area_ratio,repetitions,median_ns,min_ns,max_ns,rep0_ns,rep1_ns,rep2_ns,rep3_ns,rep4_ns\n";
    support_rows
        << std::setprecision(17)
        << "stage,projection,method,direction_x,direction_y,reference_generator_support,sampled_boundary_support,sampled_gap\n";
    for (const auto &[projection, approximations] : rows) {
        const auto minmax = [](const auto &values) {
            const auto [minimum, maximum] = std::minmax_element(values.begin(), values.end());
            return std::pair{*minimum, *maximum};
        };
        for (const auto &result : approximations) {
            const auto [minimum, maximum] = minmax(result.elapsed_ns);
            summary << projection.stage << ',' << projection.id << ',' << projection.boundary.size()
                    << ',' << projection.area << ',' << result.method << ',' << result.version
                    << ',' << result.representation << ',' << result.primitives << ','
                    << result.admission << ',' << result.area << ',' << result.area_ratio << ','
                    << repetitions << ',' << median(result.elapsed_ns) << ',' << minimum << ','
                    << maximum;
            for (const auto elapsed : result.elapsed_ns)
                summary << ',' << elapsed;
            summary << '\n';
            for (std::size_t direction = 0; direction < support_directions; ++direction) {
                const double angle =
                    2 * std::numbers::pi * static_cast<double>(direction) / support_directions;
                const Point normal{std::cos(angle), std::sin(angle)};
                const auto exact = support(projection.exact, normal);
                const auto outer = result.method.starts_with("ellipsoid")
                                       ? support_of_ellipsoid(result, normal)
                                       : support(result.boundary, normal);
                support_rows << projection.stage << ',' << projection.id << ',' << result.method
                             << ',' << normal[0] << ',' << normal[1] << ',' << exact << ',' << outer
                             << ',' << outer - exact << '\n';
            }
        }
    }
}

std::string color(std::string_view method) {
    if (method == "generator projection")
        return "#f5f5f5";
    if (method == "box")
        return "#60a5fa";
    if (method.starts_with("parallelotope"))
        return "#fbbf24";
    if (method == "zonotope-axis-cover")
        return "#34d399";
    return "#f87171";
}

void write_svg(const std::filesystem::path &output, std::string_view projection_name,
               const std::vector<std::pair<ProjectedSet, std::vector<Approximation>>> &rows,
               std::size_t plane_index) {
    const int panel_width = 360, panel_height = 270, columns = 4, rows_count = 4;
    const int width = panel_width * columns, height = panel_height * rows_count + 75;
    double xmin = std::numeric_limits<double>::infinity(), xmax = -xmin;
    double ymin = xmin, ymax = -xmin;
    for (const auto &[projection, results] : rows) {
        if (projection.id.find(projection_name) == std::string::npos)
            continue;
        const auto include = [&](const std::vector<Point> &points) {
            for (const auto &p : points) {
                xmin = std::min(xmin, p[0]);
                xmax = std::max(xmax, p[0]);
                ymin = std::min(ymin, p[1]);
                ymax = std::max(ymax, p[1]);
            }
        };
        include(projection.boundary);
        for (const auto &result : results)
            include(result.boundary);
    }
    const double xpad = (xmax - xmin) * 0.05, ypad = (ymax - ymin) * 0.05;
    xmin -= xpad;
    xmax += xpad;
    ymin -= ypad;
    ymax += ypad;
    std::ofstream svg(output);
    svg.exceptions(std::ios::badbit | std::ios::failbit);
    svg << std::setprecision(6) << "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 "
        << width << ' ' << height
        << "\" role=\"img\" aria-labelledby=\"title desc\"><title id=\"title\">Reachable-set generator projection and outer approximations</title>"
        << "<desc id=\"desc\">Sixteen stages from the full four-state model, with computed generator projections and four outer approximation families.</desc>"
        << "<rect width=\"100%\" height=\"100%\" fill=\"#16161e\"/><g font-family=\"sans-serif\" fill=\"#e0def4\">"
        << "<text x=\"" << width / 2 << "\" y=\"28\" text-anchor=\"middle\" font-size=\"22\">x"
        << (plane_index == 0 ? "1-x2" : "3-x4")
        << " projection · reference and outer approximations</text>";
    const std::array<std::string_view, 5> legend{"generator projection", "box", "parallelotope 45°",
                                                 "zonotope axis cover", "ellipsoid 45°"};
    for (std::size_t i = 0; i < legend.size(); ++i) {
        const int x = 22 + static_cast<int>(i) * 235;
        svg << "<path d=\"M " << x << " 52 h 24\" stroke=\"" << color(legend[i])
            << "\" stroke-width=\"3\"/><text x=\"" << x + 30 << "\" y=\"56\" font-size=\"13\">"
            << legend[i] << "</text>";
    }
    std::size_t panel = 0;
    for (const auto &[projection, results] : rows) {
        if (projection.id.find(projection_name) == std::string::npos)
            continue;
        const int col = static_cast<int>(panel % columns), row = static_cast<int>(panel / columns);
        const double left = col * panel_width + 38, top = row * panel_height + 115;
        const double plot_width = 300, plot_height = 205;
        const auto px = [&](double value) {
            return left + plot_width * (value - xmin) / (xmax - xmin);
        };
        const auto py = [&](double value) {
            return top + plot_height * (ymax - value) / (ymax - ymin);
        };
        svg << "<text x=\"" << left + plot_width / 2 << "\" y=\"" << top - 10
            << "\" text-anchor=\"middle\" font-size=\"15\">stage " << projection.stage << "</text>";
        for (int tick = 0; tick <= 2; ++tick) {
            const double xv = xmin + (xmax - xmin) * tick / 2.0;
            const double yv = ymin + (ymax - ymin) * tick / 2.0;
            svg << "<path d=\"M " << px(xv) << ' ' << top << " v " << plot_height << " M " << left
                << ' ' << py(yv) << " h " << plot_width
                << "\" stroke=\"#e0def4\" opacity=\"0.13\"/>";
        }
        const auto draw = [&](const std::vector<Point> &polygon, std::string_view method,
                              double opacity, double stroke_width) {
            if (polygon.empty())
                return;
            svg << "<polygon points=\"";
            for (const auto &p : polygon)
                svg << px(p[0]) << ',' << py(p[1]) << ' ';
            svg << "\" fill=\"" << color(method) << "\" fill-opacity=\"" << opacity
                << "\" stroke=\"" << color(method) << "\" stroke-width=\"" << stroke_width
                << "\"/>";
        };
        draw(projection.boundary, "generator projection", 0.02, 2.2);
        for (const auto &result : results)
            draw(result.boundary, result.method, 0.01, 1.4);
        svg << "<rect x=\"" << left << "\" y=\"" << top << "\" width=\"" << plot_width
            << "\" height=\"" << plot_height
            << "\" fill=\"none\" stroke=\"#e0def4\" opacity=\"0.55\"/>";
        ++panel;
    }
    svg << "<text x=\"" << width / 2 << "\" y=\"" << height - 12
        << "\" text-anchor=\"middle\" font-size=\"12\">All panels share axes. Projections are from the 4D generator sets; no objective is defined.</text></g></svg>\n";
}

}

int main(int argc, char **argv) try {
    if (argc > 2 || (argc == 2 && std::string_view(argv[1]).starts_with("--")))
        throw std::runtime_error("Usage: native_four_state_approximation [new-output-directory]");
    const auto data = take(
        model::catalogue::make_discrete_reachability_case("archival-2017-4d-scalar-reachability/1"),
        "load source model");
    const auto system = take(model::snapshot(data.model, data.time_grid), "snapshot source model");
    std::vector<sets::GeneratorSet> full_sets{data.initial};
    for (std::size_t k = 0; k < system.horizon(); ++k) {
        const auto stage = take(system.stage({k}), "read source model stage");
        const auto prefix = std::string(data.info.id) + "/approx-stage/" + std::to_string(k + 1);
        const auto state =
            take(geometry::generators::affine_image(
                     full_sets.back(), copy_matrix(stage.A),
                     Vector(stage.offset.values().begin(), stage.offset.values().end()),
                     {prefix + "/state"}),
                 "propagate state");
        const auto control =
            take(geometry::generators::affine_image(data.controls[k], copy_matrix(stage.B),
                                                    Vector(4, 0.0), {prefix + "/control"}),
                 "map input interval");
        full_sets.push_back(
            take(geometry::generators::minkowski_sum(state, control, {prefix + "/reachable"}),
                 "add independent input"));
    }

    std::vector<std::pair<ProjectedSet, std::vector<Approximation>>> rows;
    for (std::size_t stage = 0; stage < full_sets.size(); ++stage) {
        for (std::size_t plane = 0; plane < 2; ++plane) {
            const std::size_t x = plane * 2, y = x + 1;
            const auto id = "stage-" + std::to_string(stage) + (plane == 0 ? "-x1-x2" : "-x3-x4");
            auto exact = project(full_sets[stage], x, y, id + "/exact-generator-projection");
            auto boundary = zonotope_boundary(exact);
            auto vertices = vertex_set(boundary, id + "/exact-v-projection",
                                       "x" + std::to_string(x + 1), "x" + std::to_string(y + 1));
            ProjectedSet projection{stage,
                                    id,
                                    "x" + std::to_string(x + 1),
                                    "x" + std::to_string(y + 1),
                                    std::move(exact),
                                    std::move(boundary),
                                    std::move(vertices),
                                    0.0};
            projection.area = signed_area(projection.boundary);
            if (!(projection.area > 0.0))
                throw std::runtime_error("Exact projection has no area");
            auto methods = approximate(projection);
            rows.emplace_back(std::move(projection), std::move(methods));
        }
    }

    std::optional<std::filesystem::path> output;
    if (argc == 2) {
        output = std::filesystem::path(argv[1]);
        if (!std::filesystem::create_directory(*output))
            throw std::runtime_error("Output directory must be new");
        write_csv(*output, rows);
        write_svg(*output / "x1-x2-approximation-stages.svg", "x1-x2", rows, 0);
        write_svg(*output / "x3-x4-approximation-stages.svg", "x3-x4", rows, 1);
    }
    std::size_t admitted = 0;
    double maximum_ratio = 0.0;
    for (const auto &[projection, methods] : rows) {
        admitted += methods.size();
        for (const auto &method : methods)
            maximum_ratio = std::max(maximum_ratio, method.area_ratio);
    }
    std::cout << "case=" << data.info.id << " dimension=4 controls=1 transitions=15 stages=16"
              << " projections=2 approximations=" << admitted << " repetitions=" << repetitions
              << " maximum_area_ratio=" << std::setprecision(10) << maximum_ratio << '\n'
              << "scope=outer approximations of the x1-x2 and x3-x4 projections;"
              << " full-state propagation retains an unreduced stored-binary64 generator set"
              << "; no objective or controller is defined\n"
              << "Native four-state projection approximation comparison passed\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
