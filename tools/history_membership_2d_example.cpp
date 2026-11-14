#include <csl/adapters/nlp/casadi_history_optimizer.hpp>
#include <csl/optimization/history_optimizer.hpp>
#include <csl/sets/data.hpp>

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <utility>

#ifndef CSL_HISTORY_MEMBERSHIP_SOURCE_COMMIT
#error "CMake must bind this example to a source commit"
#endif
#ifndef CSL_HISTORY_MEMBERSHIP_COMPILER
#error "CMake must record the compiler identity for this example"
#endif
#ifndef CSL_HISTORY_MEMBERSHIP_CASADI_VERSION
#error "CMake must record the CasADi version for this example"
#endif

using namespace csl;
namespace {
template <class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("failed to construct the 2D membership example");
    return std::get<T>(std::move(value));
}

optimization::HistoryOptimizationRequest make_request() {
    constexpr std::size_t n = 8;
    Matrix inequalities{4, n, {0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, -1, 0,
                               0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0,  -1}};
    Matrix equalities{6, n, {1,  0, 0,  0, 0, 0, 0,  0, 0, 1,  0, 0,  0, 0, 0, 0,
                             -1, 0, 1,  0, 0, 0, -1, 0, 0, -1, 0, 1,  0, 0, 0, 0,
                             0,  0, -1, 0, 1, 0, 0,  0, 0, 0,  0, -1, 0, 1, 0, -1}};
    auto set = take(sets::make_h(
        {{"membership-integrator-history"}, n, {}},
        {take(numeric::snapshot(inequalities)), take(numeric::snapshot_vector(Vector{1, 0, 1, 0})),
         take(numeric::snapshot(equalities)), take(numeric::snapshot_vector(Vector(6, 0)))}));
    synthesis::JointHistoryRelation histories{{{2, 1, 0}, 2}, std::move(set)};

    optimization::HistoryZonotopeMembership selected{{0.4, 0.0}, {2, 1, {0.2, 0.0}}};
    optimization::HistoryMembershipOrigin origin{
        {"source-stage-1-zonotope"},
        {"selected-stage-1-zonotope"},
        optimization::HistorySetFamily::zonotope,
        SetRelation::equivalent,
        "integrator-state-(x,y)",
        {2, 3},
        optimization::HistorySourceGeometry{{"source-stage-1-zonotope"},
                                            optimization::HistorySetFamily::zonotope,
                                            optimization::HistoryMembershipShape{selected}}};
    optimization::HistoryDomain domain{
        std::move(histories),
        {{{1}, std::move(origin), optimization::HistoryMembershipShape{selected}}},
        "integrator-state-(x,y)"};

    TerminalObjective terminal =
        ResidualNormTerminal{Matrix{2, 2, {1, 0, 0, 1}}, Vector{1, 1}, Vector{1, 1}};
    optimization::RunningControlCost running{
        "half-l1-control",
        2,
        {{0, {optimization::EuclideanControlPenalty{{1, 1, {1}}, {0}, 0.5}}},
         {1, {optimization::EuclideanControlPenalty{{1, 1, {1}}, {0}, 0.5}}}}};
    auto compiled = optimization::compile_history_cost(domain.original, terminal, running, 0);
    if (!std::holds_alternative<optimization::HistoryCostProgram>(compiled))
        throw std::runtime_error("source objective did not compile");
    return {{ProblemId{"two-state-integrator-zonotope"},
             ProgramId{"full-source-cost-stage-zonotope-membership"}},
            std::move(domain),
            std::get<optimization::HistoryCostProgram>(std::move(compiled)),
            optimization::SuppliedStart{{0, 0, 0.4, 0, 0.4, 0.5, 0.4, 0.5},
                                        {optimization::HistoryZonotopeWitness{{0.0}}}}};
}

void write_outputs(const std::filesystem::path &directory,
                   const optimization::HistoryOptimizationResult &result) {
    std::filesystem::create_directories(directory);
    const auto witness =
        std::get<optimization::HistoryZonotopeWitness>(result.membership_witnesses.at(0));
    std::ofstream csv(directory / "history.csv");
    csv << std::setprecision(17) << "series,stage,x,y,u0,u1,source_J,zonotope_coefficient\n"
        << "optimized,0," << result.history[0] << ',' << result.history[1] << ','
        << result.history[6] << ',' << result.history[7] << ',' << result.source_cost.total
        << ",\noptimized,1," << result.history[2] << ',' << result.history[3] << ','
        << result.history[6] << ',' << result.history[7] << ',' << result.source_cost.total << ','
        << witness.coefficients.at(0) << "\noptimized,2," << result.history[4] << ','
        << result.history[5] << ',' << result.history[6] << ',' << result.history[7] << ','
        << result.source_cost.total << ",\nselected-zonotope,1,0.2,0,0,0,0,-1\n"
        << "selected-zonotope,1,0.6,0,0,0,0,1\n";
    if (!csv)
        throw std::runtime_error("failed to write history.csv");

    const auto px = [](double x) { return 120.0 + 560.0 * x; };
    const auto py = [](double y) { return 600.0 - 500.0 * y; };
    std::ofstream svg(directory / "history.svg");
    svg << std::setprecision(8)
        << "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"700\" viewBox=\"0 0 800 700\">"
        << "<rect width=\"800\" height=\"700\" fill=\"white\"/>"
        << "<text x=\"400\" y=\"32\" text-anchor=\"middle\" font-size=\"19\">2D history optimization with a stage-1 zonotope membership</text>"
        << "<path d=\"M120 600 H680 M120 600 V100\" stroke=\"#444\" fill=\"none\"/>"
        << "<text x=\"400\" y=\"650\" text-anchor=\"middle\">state coordinate x</text>"
        << "<text x=\"38\" y=\"350\" transform=\"rotate(-90 38 350)\" text-anchor=\"middle\">state coordinate y</text>"
        << "<path d=\"M" << px(0.2) << ' ' << py(0) << " L" << px(0.6) << ' ' << py(0)
        << "\" stroke=\"#D55E00\" stroke-width=\"12\" stroke-linecap=\"round\"/>"
        << "<polyline points=\"" << px(result.history[0]) << ',' << py(result.history[1]) << ' '
        << px(result.history[2]) << ',' << py(result.history[3]) << ' ' << px(result.history[4])
        << ',' << py(result.history[5])
        << "\" fill=\"none\" stroke=\"#0072B2\" stroke-width=\"5\"/>"
        << "<circle cx=\"" << px(result.history[2]) << "\" cy=\"" << py(result.history[3])
        << "\" r=\"8\" fill=\"#D55E00\"/><circle cx=\"" << px(result.history[4]) << "\" cy=\""
        << py(result.history[5]) << "\" r=\"8\" fill=\"#009E73\"/>"
        << "<text x=\"145\" y=\"92\" fill=\"#D55E00\">selected stage-1 zonotope: (0.4,0)+0.2[-1,1](1,0)</text>"
        << "<text x=\"145\" y=\"120\" fill=\"#0072B2\">optimized state history (blue), x₀→x₁→x₂</text>"
        << "<text x=\"145\" y=\"148\" fill=\"#009E73\">terminal state x₂ = (" << result.history[4]
        << ',' << result.history[5] << ")</text></svg>";
    if (!svg)
        throw std::runtime_error("failed to write history.svg");

    std::ofstream html(directory / "index.html");
    html
        << "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>2D typed history membership</title>"
        << "<main><h1>2D typed stage-membership example</h1><p>Two-state integrator: "
        << "x₀=(0,0), x₁=x₀+(u₀,0), x₂=x₁+(0,u₁), and 0≤u₀,u₁≤1. At stage 1, "
        << "the state must also belong to the rank-one zonotope Z=(0.4,0)+0.2[-1,1](1,0).</p>"
        << "<img src=\"history.svg\" alt=\"Selected stage-one zonotope and actual optimized state history\">"
        << "<p>Objective: J=||x₂−(1,1)||₂+0.5(|u₀|+|u₁|). The solver returns "
        << "u₀=" << result.history[6] << ", u₁=" << result.history[7]
        << ", J=" << result.source_cost.total
        << ". The independently checked latent zonotope coefficient is "
        << witness.coefficients.at(0) << "; maximum full-H violation is "
        << result.maximum_history_violation
        << ".</p><a href=\"history.csv\">History CSV</a></main></html>";
    if (!html)
        throw std::runtime_error("failed to write index.html");
}
} // namespace

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cerr << "usage: history_membership_2d_example OUTPUT_DIR\n";
        return 2;
    }
    try {
        auto request = make_request();
        auto entry = adapters::nlp::make_casadi_history_optimizer_registration();
        registry::Registry<registry::HistoryOptimizerPort> providers;
        const registry::Method method{entry.identity.id, entry.identity.version};
        if (providers.add(std::move(entry)))
            throw std::runtime_error("could not register the CasADi history optimizer");
        registry::Requirements requirements;
        requirements.output.representation = {"csl.whole-history-source-cost.v1"};
        auto prepared =
            registry::prepare_provider(registry::select_provider(providers, method, requirements));
        if (!std::holds_alternative<registry::PreparedProvider<registry::HistoryOptimizerPort>>(
                prepared))
            throw std::runtime_error("CasADi history optimizer unavailable");
        auto pipeline =
            std::get<registry::PreparedProvider<registry::HistoryOptimizerPort>>(prepared).prepare(
                request);
        if (!std::holds_alternative<registry::PreparedPipeline<registry::HistoryOptimizerPort>>(
                pipeline))
            throw std::runtime_error("whole-history membership request rejected");
        auto workspaces =
            std::get<registry::PreparedPipeline<registry::HistoryOptimizerPort>>(pipeline).create();
        auto outcome = std::get<0>(workspaces)->run(ExecutionContext{});
        if (!std::holds_alternative<optimization::HistoryOptimizationResult>(outcome))
            throw std::runtime_error("whole-history membership solve failed");
        const auto &result = std::get<optimization::HistoryOptimizationResult>(outcome);
        write_outputs(argv[1], result);
        const auto &start = std::get<optimization::VerifiedSuppliedStart>(result.initialization);
        const auto &witness =
            std::get<optimization::HistoryZonotopeWitness>(result.membership_witnesses.at(0));
        std::cout << std::setprecision(17)
                  << "source_commit=" << CSL_HISTORY_MEMBERSHIP_SOURCE_COMMIT
                  << "; compiler=" << CSL_HISTORY_MEMBERSHIP_COMPILER
                  << "; casadi_version=" << CSL_HISTORY_MEMBERSHIP_CASADI_VERSION
                  << "; provider=" << method.id.value << '@' << *method.version
                  << "; source_J=" << result.source_cost.total << "; u0=" << result.history[6]
                  << "; u1=" << result.history[7] << "; x1=" << result.history[2] << ','
                  << result.history[3] << "; x2=" << result.history[4] << ',' << result.history[5]
                  << "; membership_lambda=" << witness.coefficients.at(0)
                  << "; supplied_start_readback="
                  << (start.supplied_history == start.primal_readback)
                  << "; max_H_violation=" << result.maximum_history_violation
                  << "; diagnostics=" << result.diagnostics << '\n';
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
