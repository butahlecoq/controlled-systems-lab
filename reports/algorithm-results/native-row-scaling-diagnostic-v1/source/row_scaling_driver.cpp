#include <csl/adapters/convex/highs.hpp>
#include <csl/model/discrete_catalogue.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <span>
#include <stdexcept>
#include <string>


#include "row_scaling.hpp"

namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    throw std::runtime_error("Native tracking operation returned diagnostics");
}

double dot_cost(const csl::Vector& state, const csl::Vector& control,
                const csl::Vector& weights) {
    double result = 0.02 * std::inner_product(control.begin(), control.end(), control.begin(), 0.0);
    for (std::size_t i = 0; i < state.size(); ++i) result += weights[i] * state[i] * state[i];
    return result;
}

csl::optimization::NominalQuadraticHistoryTask make_task(
    const csl::model::catalogue::DiscreteModelData& model, const csl::Vector& initial,
    std::size_t horizon, const csl::Vector& state_weights, const csl::Vector& affine) {
    using namespace csl;
    const auto nx = initial.size(), nu = model.controls.size();
    std::vector<LinearStage> dynamics(horizon);
    for (auto& stage : dynamics)
        stage = {model.coefficients.A, model.coefficients.B, Matrix{nx, 0, {}}, affine};

    Matrix q{nx, nx, Vector(nx * nx, 0.0)};
    Matrix r{nu, nu, Vector(nu * nu, 0.0)};
    for (std::size_t i = 0; i < nx; ++i) q.values[i * nx + i] = 2.0 * state_weights[i];
    for (std::size_t i = 0; i < nu; ++i) r.values[i * nu + i] = 0.04;
    Matrix zero_xu{nx, nu, Vector(nx * nu, 0.0)};
    std::vector<optimization::QuadraticHistoryStageCost> running;
    running.reserve(horizon);
    for (std::size_t k = 0; k < horizon; ++k)
        running.push_back({q, zero_xu, r, Vector(nx, 0.0), Vector(nu, 0.0), 0.0});
    Matrix terminal_q = q;
    for (auto& value : terminal_q.values) value *= 5.0;
    std::vector<std::vector<Interval>> state_bounds(horizon + 1,
        std::vector<Interval>(nx));
    std::vector<std::vector<Interval>> control_bounds(horizon,
        std::vector<Interval>(nu, Interval{-1.0, 1.0}));
    return {{{"1012-authored-nominal-tracking"},
              {std::string(model.info.id) + "-3step-zero-target-v1"}},
        std::move(dynamics), KnownInitial{initial}, std::move(state_bounds),
        std::move(control_bounds), std::nullopt, std::move(running),
        {std::move(terminal_q), Vector(nx, 0.0), 0.0}};
}

void write_values(std::ostream& out, const std::string& id, const std::string& kind,
                  std::size_t replan, std::size_t stage, const csl::Vector& values) {
    for (std::size_t i = 0; i < values.size(); ++i)
        out << id << ',' << kind << ',' << replan << ',' << stage << ',' << i << ',' << values[i] << '\n';
}
}

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::model::catalogue;
    using namespace csl::optimization;
    using namespace csl::registry;
    if (argc != 4) throw std::runtime_error("Usage: row_scaling MODE MODEL_ID NEW_OUTPUT_DIRECTORY");
    const std::string mode(argv[1]);
    const bool apply_scaling = mode == "row-scale";
    if (!apply_scaling && mode != "export") throw std::runtime_error("Unknown diagnostic mode");
    const std::string id(argv[2]);
    const std::filesystem::path output(argv[3]);
    if (!std::filesystem::create_directory(output))
        throw std::runtime_error("Output directory must be new");
    const auto model = take<DiscreteModelData>(make_discrete_model(id));
    constexpr std::size_t horizon = 3, replans = 3;
    const auto nx = model.initial_state.size(), nu = model.controls.size();
    const Vector selected_external = model.nominal_external.value_or(Vector(model.external.size(), 0.0));
    Vector affine = model.coefficients.offset;
    for (std::size_t i = 0; i < nx; ++i)
        for (std::size_t j = 0; j < selected_external.size(); ++j)
            affine[i] += model.coefficients.E.values[i * model.coefficients.E.cols + j] * selected_external[j];
    Vector weights(nx);
    for (std::size_t i = 0; i < nx; ++i) {
        const double scale = std::max(1.0, std::abs(model.initial_state[i]));
        weights[i] = 1.0 / (scale * scale);
    }
    Vector grid{0.0, model.time_step.value};
    const auto system = take<model::LinearSystem>(model::snapshot(model.system_model(), grid));

    Registry<ConvexPort> providers;
    if (providers.add(std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration())))
        throw std::runtime_error("HiGHS provider registration failed");
    std::ofstream trace(output / "trace.csv");
    std::ofstream run(output / "run.txt");
    if (!trace || !run) throw std::runtime_error("Could not create first-pass records");
    trace << std::setprecision(std::numeric_limits<double>::max_digits10)
          << "model,kind,replan,stage,coordinate,value\n";
    run << "model=" << id << "\ntitle=" << model.info.title << "\nsource_title=" << model.info.source.title
        << "\nsource_sha256=" << model.info.source.sha256 << "\nsource_locator=" << model.info.source.locator
        << "\nsource_qualification=" << model.info.source.qualification << "\n"
        << "task=authored nominal quadratic tracking to zero; 3-stage horizon; 3 closed-loop replans\n"
        << "task_identity=1012-authored-nominal-tracking/" << id << "-3step-zero-target-v1\n"
        << "state_weight_i=1/max(1,abs(initial_i))^2; terminal_weight=5*state_weight; R=0.02*I\n"
        << "recorded_coordinate_actuator_bounds=[-1,1]; state_bounds=none; units=source catalogue coordinates\n"
        << "external_selection=" << (model.nominal_external ? "supplied_nominal_external" : "authored_fixed_zero")
        << "; source_E_channel_retained=" << model.external.size() << " coordinates\n"
        << "time_step=" << model.time_step.value << ' ' << model.time_step.unit << "\n"
        << "assurance=numerical; this is not empirical calibration, certified optimality, robust control, or nonlinear stability evidence\n";

    Vector observed = model.initial_state;
    double accumulated_stage_cost = 0.0;
    std::string backend_id, backend_version;
    for (std::size_t replan = 0; replan < replans; ++replan) {
        const auto task = make_task(model, observed, horizon, weights, affine);
        auto compiled = compile_nominal_quadratic_history(task);
        if (!std::holds_alternative<ConvexProgram>(compiled))
            throw std::runtime_error("Nominal history QP compilation rejected the authored task");
        const auto original_program = std::get<ConvexProgram>(std::move(compiled));
        auto program = row_diagnostic::export_and_scale(original_program, output / ("replan-" + std::to_string(replan)), nx, nu, horizon, apply_scaling);
        if (!apply_scaling) { std::cout << "Original compiled QP exported before backend selection\n"; return 0; }
        Requirements requirements;
        requirements.output.representation = {"csl.program-result.v1"};
        auto selected = prepare_pipeline(select(providers, {{"csl.convex.highs"}, {}}, program, requirements));
        if (!std::holds_alternative<PreparedPipeline<ConvexPort>>(selected)) {
            const auto* rejected = std::get_if<Rejection>(&selected);
            std::string message = "HiGHS task selection failed";
            if (rejected)
                for (const auto& diagnostic : rejected->diagnostics)
                    message += "; " + diagnostic.field + ": " + diagnostic.explanation;
            throw std::runtime_error(message);
        }
        auto& prepared = std::get<PreparedPipeline<ConvexPort>>(selected);
        const auto provenance = prepared.provenance();
        backend_id = provenance.front().actual->id.value;
        backend_version = provenance.front().actual->version;
        auto [workspace] = prepared.create();
        const auto outcome = workspace->run({
            std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}), {}, {}, {1e-8, 1e-8},
            "1012-authored-tracking-replan"});
        std::ofstream native_log(output / ("native-replan-" + std::to_string(replan) + ".txt"));
        if (const auto* rejected_outcome = std::get_if<Unsupported>(&outcome))
            for (const auto& d : rejected_outcome->diagnostics) native_log << d.field << ": " << d.explanation << '\n';
        const auto* result = std::get_if<ProgramResult>(&outcome);
        if (result) native_log << "termination=" << static_cast<int>(result->termination) << " outcome=" << static_cast<int>(result->outcome.value) << "\n" << result->raw_diagnostics;
        native_log.flush();
        if (!result || !result->primal || result->termination != Termination::completed ||
            result->outcome.value != MathematicalOutcome::optimal ||
            !check_program_result(*result, program, Assurance::numerical).empty())
            throw std::runtime_error("Numerical optimizer did not return a checked completed optimum");
        const auto& z = *result->primal;
        const auto original_check = evaluate_primal(original_program, z, {1e-8, 1e-8}, {{"diagnostic-original-primal"}, "1"});
        if (!std::holds_alternative<ConvexPrimalEvaluation>(original_check)) throw std::runtime_error("Original primal evaluator refused");
        const auto& residuals = std::get<ConvexPrimalEvaluation>(original_check).residuals;
        if (residuals.rows.violation > 1e-8 + 1e-8 * residuals.rows.scale || residuals.variables.violation > 1e-8 + 1e-8 * residuals.variables.scale)
            throw std::runtime_error("Scaled solver primal violates original program rows/bounds");
        const auto state_count = (horizon + 1) * nx;
        const auto control_offset = state_count;
        Vector plan(horizon * nu);
        std::copy_n(z.begin() + static_cast<std::ptrdiff_t>(control_offset), plan.size(), plan.begin());
        const auto& first_control = std::span(z).subspan(control_offset, nu);
        for (std::size_t i = 0; i < nx; ++i)
            if (std::abs(z[i] - observed[i]) > 1e-7 * (1 + std::abs(observed[i])))
                throw std::runtime_error("QP initial-state binding check failed");
        for (std::size_t k = 0; k < horizon; ++k) {
            for (std::size_t i = 0; i < nx; ++i) {
                double expected = affine[i];
                for (std::size_t j = 0; j < nx; ++j)
                    expected += model.coefficients.A.values[i * nx + j] * z[k * nx + j];
                for (std::size_t j = 0; j < nu; ++j)
                    expected += model.coefficients.B.values[i * nu + j] * z[control_offset + k * nu + j];
                const double actual = z[(k + 1) * nx + i];
                if (!std::isfinite(actual) || std::abs(actual - expected) > 1e-6 * (1 + std::abs(expected)))
                    throw std::runtime_error("Independent compiled-history dynamics check failed");
            }
            for (std::size_t i = 0; i < nu; ++i) {
                const double u = z[control_offset + k * nu + i];
                if (!std::isfinite(u) || u < -1.000001 || u > 1.000001)
                    throw std::runtime_error("Independent actuator-box check failed");
            }
        }
        double independent_cost = 0.0;
        for (std::size_t k = 0; k < horizon; ++k) {
            const auto x = std::span(z).subspan(k * nx, nx);
            const auto u = std::span(z).subspan(control_offset + k * nu, nu);
            independent_cost += dot_cost(Vector(x.begin(), x.end()), Vector(u.begin(), u.end()), weights);
        }
        const auto terminal = std::span(z).subspan(horizon * nx, nx);
        for (std::size_t i = 0; i < nx; ++i) independent_cost += 5.0 * weights[i] * terminal[i] * terminal[i];
        const auto evaluated = evaluate_primal(original_program, z, {1e-8, 1e-8}, {{"1012-independent-task-cost"}, "1"});
        if (!std::holds_alternative<ConvexPrimalEvaluation>(evaluated) ||
            std::abs(std::get<ConvexPrimalEvaluation>(evaluated).original_objective - independent_cost) >
                1e-6 * (1 + std::abs(independent_cost)))
            throw std::runtime_error("Independent task-cost evaluator disagrees with compiled QP");

        write_values(trace, id, "predicted_state", replan, 0, Vector(z.begin(), z.begin() + static_cast<std::ptrdiff_t>(nx)));
        for (std::size_t k = 0; k <= horizon; ++k)
            write_values(trace, id, "predicted_state", replan, k,
                Vector(z.begin() + static_cast<std::ptrdiff_t>(k * nx),
                       z.begin() + static_cast<std::ptrdiff_t>((k + 1) * nx)));
        for (std::size_t k = 0; k < horizon; ++k)
            write_values(trace, id, "predicted_control", replan, k,
                Vector(z.begin() + static_cast<std::ptrdiff_t>(control_offset + k * nu),
                       z.begin() + static_cast<std::ptrdiff_t>(control_offset + (k + 1) * nu)));
        write_values(trace, id, "observed_state", replan, 0, observed);
        write_values(trace, id, "applied_control", replan, 0, Vector(first_control.begin(), first_control.end()));
        const double current_cost = dot_cost(observed, Vector(first_control.begin(), first_control.end()), weights);
        accumulated_stage_cost += current_cost;
        auto next = take<Vector>(system.step({0}, observed, Vector(first_control.begin(), first_control.end()), selected_external));
        write_values(trace, id, "observed_next_state", replan, 1, next);
        trace << id << ",independent_plan_cost," << replan << ",0,0," << independent_cost << '\n'
              << id << ",compiled_plan_cost," << replan << ",0,0,"
              << std::get<ConvexPrimalEvaluation>(evaluated).original_objective << '\n'
              << id << ",realized_running_cost," << replan << ",0,0," << current_cost << '\n';
        trace.flush();
        if (!trace) throw std::runtime_error("Could not flush completed replan record");
        observed = std::move(next);
    }
    run << "solver=" << backend_id << " version=" << backend_version << "\ncompleted_replans=" << replans
        << "\nzero-disturbance/selected-nominal realized running cost=" << accumulated_stage_cost << '\n'
        << "final_observed_state=";
    for (std::size_t i = 0; i < observed.size(); ++i) run << (i ? "," : "") << observed[i];
    run << '\n';
    if (!run) throw std::runtime_error("Could not finalize run receipt");
    std::cout << "Native authored tracking: model=" << id << " replans=" << replans
              << " states=" << nx << " controls=" << nu << " backend=" << backend_id
              << " version=" << backend_version << '\n';
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
