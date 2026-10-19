#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/feasible_directions/smooth_convex.hpp>

#include <chrono>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::optimization::feasible_directions;

void near(double actual, double expected) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > 1e-8)
        throw std::runtime_error("Independent box-quadratic literal differs");
}

struct Observation {
    double x, y, objective, projected_residual;
    std::size_t iterations, objective_evaluations;
};

Observation run_once() {
    auto created = make_linear_program({{{"opt10-report"}, {"box-quadratic"}},
        {0, 0}, 0, {0, 2, {0}, {}, {}}, {{0, 1}, {-1, 1}}, {}});
    if (!std::holds_alternative<LinearProgram>(created))
        throw std::runtime_error("Public feasible-set construction failed");
    const auto& feasible = std::get<LinearProgram>(created);
    auto registered = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registered))
        throw std::runtime_error("Production HiGHS LP registration failed");
    auto backend = std::get<registry::Registration<registry::LPPort>>(std::move(registered));
    auto workspace = backend.factory(feasible);
    if (!workspace) throw std::runtime_error("Production LP workspace missing");
    SmoothObjective objective{"half-squared-distance", 2, ObjectiveClaim::declared_convex,
        [](std::span<const double> x) {
            return 0.5 * ((x[0] - 2) * (x[0] - 2) + (x[1] + 2) * (x[1] + 2));
        },
        [](std::span<const double> x) { return Vector{x[0] - 2, x[1] + 2}; }};
    ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {}, {}, {1e-10, 1e-10}, "opt10-report"};
    auto outcome = minimize(feasible, objective, Vector{0, 0}, *workspace, context);
    if (!std::holds_alternative<SmoothStationary>(outcome))
        throw std::runtime_error("Public adapter did not return numerical stationarity");
    const auto& result = std::get<SmoothStationary>(outcome);
    if (result.point.size() != 2 || result.gradient.size() != 2 ||
        result.evidence != SmoothEvidence::declared_convex_numerical_stationarity ||
        result.reason != StationarityReason::zero_projected_direction ||
        result.iterations != 1 || result.objective_evaluations < 2)
        throw std::runtime_error("Public result evidence or shape differs");
    near(result.point[0], 1);
    near(result.point[1], -1);
    near(result.objective, 1);
    near(result.gradient[0], -1);
    near(result.gradient[1], 1);
    near(result.projected_gradient_residual, 0);
    return {result.point[0], result.point[1], result.objective,
        result.projected_gradient_residual, result.iterations, result.objective_evaluations};
}

void row(std::string_view phase, std::size_t repetition, std::size_t calls) {
    const auto start = std::chrono::steady_clock::now();
    Observation result{};
    for (std::size_t i = 0; i < calls; ++i) result = run_once();
    const auto end = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    if (elapsed <= 0) throw std::runtime_error("Measurement clock did not advance");
    std::cout << phase << ",box-quadratic," << repetition << ',' << calls
              << ",success,true," << elapsed << ',' << result.x << ',' << result.y
              << ',' << result.objective << ',' << result.projected_residual << ','
              << result.iterations << ',' << result.objective_evaluations << '\n';
}
} // namespace

int main(int argc, char** argv) try {
    if (argc != 2) throw std::runtime_error("Expected smoke or measure mode");
    const std::string_view mode{argv[1]};
    std::cout << "phase,case,repetition,calls,status,verified,elapsed_ns,x,y,objective,"
                 "projected_residual,iterations,objective_evaluations\n";
    if (mode == "smoke") row("smoke", 0, 1);
    else if (mode == "measure") {
        row("warmup", 0, 100);
        for (std::size_t repetition = 0; repetition < 7; ++repetition)
            row("trial", repetition, 100);
    } else throw std::runtime_error("Expected smoke or measure mode");
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
