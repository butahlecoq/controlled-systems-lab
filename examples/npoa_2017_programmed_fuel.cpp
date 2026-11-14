#include <csl/adapters/convex/highs.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
using Polygon = std::vector<Vector>;

Polygon hull(Polygon cloud) {
    if (cloud.size() <= 2)
        return cloud;
    const auto result = geometry::quickhull_2d(cloud);
    const auto *polygon = std::get_if<geometry::QuickHull2D>(&result);
    if (!polygon)
        throw std::runtime_error("Projected reachable-set hull failed");
    Polygon ordered;
    ordered.reserve(polygon->vertex_indices.size());
    for (const auto index : polygon->vertex_indices)
        ordered.push_back(cloud.at(index));
    return ordered;
}

Polygon clip_x(const Polygon &polygon, double boundary, bool keep_greater) {
    Polygon clipped;
    if (polygon.empty())
        return clipped;
    auto inside = [&](const Vector &point) {
        return keep_greater ? point[0] >= boundary : point[0] <= boundary;
    };
    for (std::size_t i = 0; i < polygon.size(); ++i) {
        const auto &from = polygon[i];
        const auto &to = polygon[(i + 1) % polygon.size()];
        const bool from_inside = inside(from), to_inside = inside(to);
        if (from_inside)
            clipped.push_back(from);
        if (from_inside != to_inside) {
            const double fraction = (boundary - from[0]) / (to[0] - from[0]);
            clipped.push_back({boundary, from[1] + fraction * (to[1] - from[1])});
        }
    }
    return clipped.size() >= 3 ? hull(std::move(clipped)) : clipped;
}

std::vector<Polygon> projected_reachability(double initial_flow, double initial_tank,
                                            double flow_increment, double flow_lower,
                                            double flow_upper) {
    std::vector<Polygon> stages{{{initial_flow, initial_tank}}};
    const std::array<double, 2> input_image{flow_increment, 0};
    for (std::size_t stage = 0; stage < 10; ++stage) {
        Polygon candidates;
        for (const auto &point : stages.back()) {
            const Vector image{point[0], point[1] - point[0]};
            for (const double sign : {-1.0, 1.0})
                candidates.push_back(
                    {image[0] + sign * input_image[0], image[1] + sign * input_image[1]});
        }
        auto next = hull(std::move(candidates));
        next = clip_x(next, flow_lower, true);
        next = clip_x(next, flow_upper, false);
        if (next.empty())
            throw std::runtime_error("Source flow constraints emptied a reachable set");
        stages.push_back(std::move(next));
    }
    return stages;
}

void write_projection(const std::filesystem::path &file, const std::vector<Polygon> &stages,
                      const Vector &trajectory, std::size_t first, std::size_t second,
                      const std::string &title, const std::string &horizontal,
                      const std::string &vertical) {
    double xmin = std::numeric_limits<double>::infinity(), xmax = -xmin;
    double ymin = xmin, ymax = -xmin;
    for (const auto &polygon : stages)
        for (const auto &point : polygon) {
            xmin = std::min(xmin, point[0]);
            xmax = std::max(xmax, point[0]);
            ymin = std::min(ymin, point[1]);
            ymax = std::max(ymax, point[1]);
        }
    for (std::size_t stage = 0; stage <= 10; ++stage) {
        const auto x = trajectory.at(stage * 4 + first), y = trajectory.at(stage * 4 + second);
        xmin = std::min(xmin, x);
        xmax = std::max(xmax, x);
        ymin = std::min(ymin, y);
        ymax = std::max(ymax, y);
    }
    const double dx = std::max(1e-9, (xmax - xmin) * 0.06);
    const double dy = std::max(1e-9, (ymax - ymin) * 0.06);
    xmin -= dx;
    xmax += dx;
    ymin -= dy;
    ymax += dy;
    constexpr double left = 90, top = 70, width = 760, height = 520;
    const auto sx = [&](double value) { return left + width * (value - xmin) / (xmax - xmin); };
    const auto sy = [&](double value) { return top + height * (ymax - value) / (ymax - ymin); };
    const auto label = [](double value) {
        std::ostringstream text;
        text << std::setprecision(4) << value;
        return text.str();
    };
    std::ofstream out(file);
    out.exceptions(std::ios::badbit | std::ios::failbit);
    out << std::setprecision(12)
        << "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 940 720\" role=\"img\" aria-labelledby=\"title desc\">"
        << "<title id=\"title\">" << title
        << "</title><desc id=\"desc\">Exact two-dimensional marginal reachable polygons at stages zero through ten, clipped by both source flow constraints, with the optimized state trajectory overlaid.</desc>"
        << "<rect width=\"940\" height=\"720\" fill=\"#fff\"/><g font-family=\"sans-serif\" fill=\"#202124\">"
        << "<text x=\"470\" y=\"34\" text-anchor=\"middle\" font-size=\"23\">" << title
        << "</text>";
    for (int tick = 0; tick <= 4; ++tick) {
        const double x_value = xmin + (xmax - xmin) * tick / 4;
        const double y_value = ymin + (ymax - ymin) * tick / 4;
        out << "<path d=\"M " << sx(x_value) << ' ' << top << " v " << height << " M " << left
            << ' ' << sy(y_value) << " h " << width
            << "\" fill=\"none\" stroke=\"#202124\" opacity=\"0.14\"/>"
            << "<text x=\"" << sx(x_value)
            << "\" y=\"610\" text-anchor=\"middle\" font-size=\"13\">" << label(x_value)
            << "</text>"
            << "<text x=\"80\" y=\"" << sy(y_value) + 4
            << "\" text-anchor=\"end\" font-size=\"13\">" << label(y_value) << "</text>";
    }
    const std::array<int, 3> start{39, 76, 119}, finish{180, 70, 45};
    for (std::size_t stage = 0; stage < stages.size(); ++stage) {
        const double weight = static_cast<double>(stage) / 10;
        std::array<int, 3> rgb{};
        for (std::size_t channel = 0; channel < 3; ++channel)
            rgb[channel] =
                static_cast<int>(start[channel] + weight * (finish[channel] - start[channel]));
        out << "<polygon points=\"";
        for (const auto &point : stages[stage])
            out << sx(point[0]) << ',' << sy(point[1]) << ' ';
        out << "\" fill=\"rgb(" << rgb[0] << ',' << rgb[1] << ',' << rgb[2]
            << ")\" fill-opacity=\"0.10\" stroke=\"rgb(" << rgb[0] << ',' << rgb[1] << ',' << rgb[2]
            << ")\" stroke-width=\"2\"/>";
    }
    out << "<polyline points=\"";
    for (std::size_t stage = 0; stage <= 10; ++stage)
        out << sx(trajectory.at(stage * 4 + first)) << ',' << sy(trajectory.at(stage * 4 + second))
            << ' ';
    out << "\" fill=\"none\" stroke=\"#111\" stroke-width=\"3\"/>";
    for (std::size_t stage = 0; stage <= 10; ++stage)
        out << "<circle cx=\"" << sx(trajectory.at(stage * 4 + first)) << "\" cy=\""
            << sy(trajectory.at(stage * 4 + second))
            << "\" r=\"4\" fill=\"#111\"><title>optimized stage " << stage << "</title></circle>";
    out << "<rect x=\"" << left << "\" y=\"" << top << "\" width=\"" << width << "\" height=\""
        << height << "\" fill=\"none\" stroke=\"#202124\"/>"
        << "<text x=\"470\" y=\"630\" text-anchor=\"middle\" font-size=\"17\">" << horizontal
        << " (source unit unspecified)</text>"
        << "<text transform=\"translate(25 330) rotate(-90)\" text-anchor=\"middle\" font-size=\"17\">"
        << vertical << " (source unit unspecified)</text>"
        << "<text x=\"90\" y=\"658\" font-size=\"14\">Reachable-set stage:</text>";
    for (std::size_t stage = 0; stage < stages.size(); ++stage) {
        const double weight = static_cast<double>(stage) / 10;
        std::array<int, 3> rgb{};
        for (std::size_t channel = 0; channel < 3; ++channel)
            rgb[channel] =
                static_cast<int>(start[channel] + weight * (finish[channel] - start[channel]));
        const auto legend_x = 230 + 61 * stage;
        out << "<rect x=\"" << legend_x << "\" y=\"646\" width=\"19\" height=\"16\" fill=\"rgb("
            << rgb[0] << ',' << rgb[1] << ',' << rgb[2] << ")\"/><text x=\"" << legend_x + 24
            << "\" y=\"659\" font-size=\"13\">" << stage << "</text>";
    }
    out << "<path d=\"M 90 690 h 32\" stroke=\"#111\" stroke-width=\"3\"/>"
        << "<text x=\"130\" y=\"695\" font-size=\"14\">optimal open-loop state trajectory</text>"
        << "</g></svg>\n";
}

NominalQuadraticHistoryTask make_task() {
    constexpr std::size_t horizon = 10;
    const Matrix a{4, 4, {1, 0, 0, 0, -1, 1, 0, 0, 0, 0, 1, 0, 0, 0, -1, 1}};
    const Matrix b{4, 1, {5.0 / 12.0, 0, -1.0 / 3.0, 0}};
    const Matrix e{4, 0, {}};
    std::vector<LinearStage> dynamics(horizon, {a, b, e, Vector(4, 0)});
    std::vector<std::vector<Interval>> state_bounds(horizon + 1, std::vector<Interval>(4));
    for (auto &stage : state_bounds) {
        stage[0] = {24.167, 25.833};
        stage[2] = {19.33, 20.66};
    }
    std::vector<std::vector<Interval>> control_bounds(horizon, {{-1.0, 1.0}});
    return {{{"npoa-2017-programmed-fuel"}, {"article-task-v1"}},
            std::move(dynamics),
            KnownInitial{{25.14, 247, 19.915, 199.92}},
            std::move(state_bounds),
            std::move(control_bounds),
            std::nullopt,
            {},
            {{4, 4, {2, 0, 0, 0, 0, 4, 0, -2, 0, 0, 2, 0, 0, -2, 0, 4}}, {-50, 0, -40, 0}, 1025},
            {}};
}

std::array<double, 4> affine_terminal_oracle() {
    // Every terminal control column is affine in (1, 9-j), so columns j=0,9
    // span the entire two-dimensional terminal affine hull independently of
    // the history-QP compiler and its backend.
    constexpr std::array<double, 4> initial{25.14, 247, 19.915, 199.92};
    constexpr std::array<std::array<double, 4>, 4> q{
        {{{2, 0, 0, 0}}, {{0, 4, 0, -2}}, {{0, 0, 2, 0}}, {{0, -2, 0, 4}}}};
    constexpr std::array<double, 4> linear{-50, 0, -40, 0};
    std::array<std::array<double, 2>, 4> basis{};
    for (std::size_t k = 0; k < 2; ++k) {
        const double remaining = k == 0 ? 9.0 : 0.0;
        basis[0][k] = 5.0 / 12.0;
        basis[1][k] = -(5.0 / 12.0) * remaining;
        basis[2][k] = -1.0 / 3.0;
        basis[3][k] = (1.0 / 3.0) * remaining;
    }
    std::array<std::array<double, 2>, 2> hessian{};
    std::array<double, 2> gradient{};
    for (std::size_t i = 0; i < 2; ++i) {
        for (std::size_t row = 0; row < 4; ++row) {
            double q_initial = linear[row];
            for (std::size_t column = 0; column < 4; ++column)
                q_initial += q[row][column] * initial[column];
            gradient[i] += basis[row][i] * q_initial;
            for (std::size_t j = 0; j < 2; ++j)
                for (std::size_t column = 0; column < 4; ++column)
                    hessian[i][j] += basis[row][i] * q[row][column] * basis[column][j];
        }
    }
    const double determinant = hessian[0][0] * hessian[1][1] - hessian[0][1] * hessian[1][0];
    const std::array<double, 2> coefficient{
        (-gradient[0] * hessian[1][1] + hessian[0][1] * gradient[1]) / determinant,
        (-hessian[0][0] * gradient[1] + hessian[1][0] * gradient[0]) / determinant};
    std::array<double, 4> terminal = initial;
    for (std::size_t coordinate = 0; coordinate < 4; ++coordinate)
        for (std::size_t k = 0; k < 2; ++k)
            terminal[coordinate] += basis[coordinate][k] * coefficient[k];
    return terminal;
}

double terminal_objective(const std::array<double, 4> &terminal) {
    return std::pow(25 - terminal[0], 2) + std::pow(terminal[1], 2) +
           std::pow(20 - terminal[2], 2) + std::pow(terminal[3], 2) +
           std::pow(terminal[1] - terminal[3], 2);
}

void write_result(const HistoryVariableLayout &layout, const Vector &primal,
                  const std::filesystem::path &output) {
    std::ofstream trace(output);
    if (!trace)
        throw std::runtime_error("Could not create trajectory CSV");
    trace << std::setprecision(17) << "stage,x1,x2,x3,x4\n";
    for (std::size_t stage = 0; stage <= layout.horizon; ++stage) {
        trace << stage;
        for (std::size_t coordinate = 0; coordinate < layout.state_dimension; ++coordinate)
            trace << ',' << primal.at(*layout.state_index(stage, coordinate));
        trace << '\n';
    }
}
}

int main(int argc, char **argv) try {
    if (argc != 2)
        throw std::runtime_error("Usage: npoa_2017_programmed_fuel OUTPUT_DIRECTORY");
    const std::filesystem::path output(argv[1]);
    std::filesystem::create_directories(output);
    const auto task = make_task();
    auto compiled = compile_nominal_quadratic_history(task);
    if (!std::holds_alternative<CompiledNominalQuadraticHistory>(compiled))
        throw std::runtime_error("Task compilation failed");
    const auto &history = std::get<CompiledNominalQuadraticHistory>(compiled);
    Registry<ConvexPort> registry;
    auto registration = adapters::convex::make_highs_registration();
    if (!std::holds_alternative<Registration<ConvexPort>>(registration) ||
        registry.add(std::get<Registration<ConvexPort>>(std::move(registration))))
        throw std::runtime_error("HiGHS registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto selected = prepare_pipeline(
        select(registry, {{"csl.convex.highs"}, {}}, history.program, requirements));
    if (!std::holds_alternative<PreparedPipeline<ConvexPort>>(selected))
        throw std::runtime_error("HiGHS selection failed");
    auto [workspace] = std::get<PreparedPipeline<ConvexPort>>(selected).create();
    const auto outcome =
        workspace->run({std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
                        {},
                        {},
                        {1e-8, 1e-8},
                        "npoa-2017-fuel"});
    const auto *result = std::get_if<ProgramResult>(&outcome);
    if (!result || !result->primal || !result->objective.upper ||
        result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal ||
        !history.layout.accepts_primal_size(result->primal->size()) ||
        !check_program_result(*result, history.program, Assurance::numerical).empty())
        throw std::runtime_error("HiGHS returned no checked numerical optimum");
    Vector trajectory;
    trajectory.reserve(44);
    for (std::size_t stage = 0; stage <= 10; ++stage)
        for (std::size_t coordinate = 0; coordinate < 4; ++coordinate)
            trajectory.push_back(
                result->primal->at(*history.layout.state_index(stage, coordinate)));
    for (std::size_t stage = 0; stage < 10; ++stage) {
        const auto state = stage * 4;
        const auto control = history.layout.control_index(stage, 0).value();
        const double u = result->primal->at(control);
        if (u < -1.0 - 1e-8 || u > 1.0 + 1e-8)
            throw std::runtime_error("Saved control violates the source interval");
        const std::array<double, 4> expected{
            trajectory[state] + (5.0 / 12.0) * u, trajectory[state + 1] - trajectory[state],
            trajectory[state + 2] - (1.0 / 3.0) * u, trajectory[state + 3] - trajectory[state + 2]};
        for (std::size_t coordinate = 0; coordinate < 4; ++coordinate)
            if (std::abs(trajectory[state + 4 + coordinate] - expected[coordinate]) > 1e-7)
                throw std::runtime_error("Saved trajectory does not satisfy the printed dynamics");
    }
    for (std::size_t stage = 0; stage <= 10; ++stage)
        if (trajectory[stage * 4] < 24.167 - 1e-8 || trajectory[stage * 4] > 25.833 + 1e-8 ||
            trajectory[stage * 4 + 2] < 19.33 - 1e-8 || trajectory[stage * 4 + 2] > 20.66 + 1e-8)
            throw std::runtime_error("Saved state violates a source flow interval");
    const std::array<double, 4> terminal{trajectory[40], trajectory[41], trajectory[42],
                                         trajectory[43]};
    const double recomputed = terminal_objective(terminal);
    const auto objective = result->objective.upper->value;
    if (std::abs(recomputed - objective) > 1e-7 * (1 + std::abs(recomputed)))
        throw std::runtime_error("Terminal objective does not match its independent recomputation");
    const auto oracle = affine_terminal_oracle();
    for (std::size_t coordinate = 0; coordinate < 4; ++coordinate)
        if (std::abs(terminal[coordinate] - oracle[coordinate]) > 1e-5)
            throw std::runtime_error(
                "Optimizer differs from independent terminal-affine-hull oracle");
    const auto oracle_objective = terminal_objective(oracle);
    if (std::abs(recomputed - oracle_objective) > 1e-7 * (1 + std::abs(oracle_objective)))
        throw std::runtime_error(
            "Feasible optimizer witness does not attain the independent lower bound");
    write_result(history.layout, *result->primal, output / "trajectory.csv");
    const auto x1_lower = std::max(24.167, 25.14 + (19.915 - 20.66) / 0.8);
    const auto x1_upper = std::min(25.833, 25.14 + (19.915 - 19.33) / 0.8);
    const auto x3_lower = std::max(19.33, 19.915 - 0.8 * (25.833 - 25.14));
    const auto x3_upper = std::min(20.66, 19.915 - 0.8 * (24.167 - 25.14));
    const auto oxidizer = projected_reachability(25.14, 247, 5.0 / 12.0, x1_lower, x1_upper);
    const auto fuel = projected_reachability(19.915, 199.92, -1.0 / 3.0, x3_lower, x3_upper);
    write_projection(output / "reachable-x1-x2.svg", oxidizer, trajectory, 0, 1,
                     "Oxidizer projection: constrained reachable sets and optimal path", "x1",
                     "x2");
    write_projection(output / "reachable-x3-x4.svg", fuel, trajectory, 2, 3,
                     "Fuel projection: constrained reachable sets and optimal path", "x3", "x4");
    std::cout << std::setprecision(12) << "objective=" << objective << " terminal=";
    for (std::size_t coordinate = 0; coordinate < 4; ++coordinate)
        std::cout << (coordinate ? "," : "")
                  << result->primal->at(*history.layout.state_index(10, coordinate));
    std::cout << " oracle_objective=" << oracle_objective
              << " article_reported_objective=4.6608 article_minus_oracle="
              << (4.6608 - oracle_objective)
              << " oracle=terminal-affine-hull-lower-bound-attained-by-feasible-witness\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
