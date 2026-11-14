#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>

#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <variant>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;

NominalQuadraticHistoryTask make_task(bool track_interior_state) {
    const Matrix a{2, 2, {0, 0, 0, 0}}, b{2, 1, {1, 1}}, e{2, 0, {}};
    const Matrix zero_x{2, 2, {0, 0, 0, 0}}, zero_xu{2, 1, {0, 0}};
    const Matrix regularize_u{1, 1, {0.4}};
    QuadraticHistoryStageCost stage0{zero_x, zero_xu, regularize_u, {0, 0}, {0}, 0};
    QuadraticHistoryStageCost stage1{zero_x, zero_xu, regularize_u, {0, 0}, {0}, 0};
    if (track_interior_state) {
        stage1.state_hessian = {2, 2, {2, 0, 0, 2}};
        stage1.state_linear = {-2, 0};
        stage1.offset = 1;
    }
    return {{{"two-dimensional-history"},
             {track_interior_state ? "with-interior-state-cost" : "control-only"}},
            {{a, b, e, {0, 0}}, {a, b, e, {0, 0}}},
            KnownInitial{{0, 0}},
            {},
            {{{-1, 1}}, {{-1, 1}}},
            std::nullopt,
            {stage0, stage1},
            {zero_x, {0, 0}, 0}};
}

std::pair<HistoryVariableLayout, Vector> solve(const NominalQuadraticHistoryTask &task) {
    auto compiled = compile_nominal_quadratic_history(task);
    if (!std::holds_alternative<CompiledNominalQuadraticHistory>(compiled))
        throw std::runtime_error("Nominal history compilation failed");
    const auto &history = std::get<CompiledNominalQuadraticHistory>(compiled);
    const auto &program = history.program;
    Registry<ConvexPort> registry;
    if (registry.add(
            std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration())))
        throw std::runtime_error("HiGHS registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto selected =
        prepare_pipeline(select(registry, {{"csl.convex.highs"}, {}}, program, requirements));
    if (!std::holds_alternative<PreparedPipeline<ConvexPort>>(selected))
        throw std::runtime_error("HiGHS selection failed");
    auto [workspace] = std::get<PreparedPipeline<ConvexPort>>(selected).create();
    auto outcome =
        workspace->run({std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
                        {},
                        {},
                        {1e-8, 1e-8},
                        "nominal-history-2d"});
    const auto *result = std::get_if<ProgramResult>(&outcome);
    if (!result || !result->primal || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("HiGHS did not return a checked optimum");
    if (!history.layout.accepts_primal_size(result->primal->size()))
        throw std::runtime_error("HiGHS returned a primal that does not match its history layout");
    return {history.layout, *result->primal};
}
}

int main() try {
    const auto [baseline_layout, baseline] = solve(make_task(false));
    const auto [tracking_layout, tracking] = solve(make_task(true));
    const auto baseline_control = baseline[baseline_layout.control_index(0, 0).value()];
    const auto tracking_control = tracking[tracking_layout.control_index(0, 0).value()];
    if (std::abs(baseline_control) > 1e-7 || std::abs(tracking_control - 5.0 / 11.0) > 1e-7)
        throw std::runtime_error("Interior-state cost did not change the checked first control");
    const auto baseline_x1 = baseline_layout.state_index(1, 0).value();
    const auto tracking_x1 = tracking_layout.state_index(1, 0).value();
    const auto tracking_x1_second = tracking_layout.state_index(1, 1).value();
    std::cout << std::fixed << std::setprecision(6)
              << "Interior-state penalty changes first control from " << baseline_control << " to "
              << tracking_control << "; baseline_x1=(" << baseline[baseline_x1] << ','
              << baseline[baseline_layout.state_index(1, 1).value()] << "); tracking_x1=("
              << tracking[tracking_x1] << ',' << tracking[tracking_x1_second] << ")\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
