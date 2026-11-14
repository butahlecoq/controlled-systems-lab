#include "quadcopter_mpc_task.hpp"

#include <csl/adapters/convex/highs.hpp>
#include <csl/model/discrete_catalogue.hpp>
#include <csl/model/linear_system.hpp>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
template <class T, class... E> T take(std::variant<T, E...> value) {
    if (auto *result = std::get_if<T>(&value))
        return std::move(*result);
    throw std::runtime_error("Native quadcopter MPC operation failed");
}
}

int main(int argc, char **argv) try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::controllers;
    using namespace csl::registry;
    using namespace csl::examples::quadcopter_mpc;
    if (argc != 2)
        throw std::runtime_error("Usage: quadcopter_mpc NEW_OUTPUT_DIRECTORY");
    const std::filesystem::path output(argv[1]);
    if (!std::filesystem::create_directory(output))
        throw std::runtime_error("Output directory must be new");
    const auto model = take<model::catalogue::DiscreteModelData>(
        model::catalogue::make_discrete_model("catalogue-2026/model-21/1"));
    constexpr std::size_t nx = 12, nu = 4, horizon = 10, replans = 15;
    const auto &coefficients = model.coefficients;
    NominalProblem task{coefficients.A,
                        coefficients.B,
                        Matrix{nx, nx, Vector(nx * nx, 0)},
                        Matrix{nx, nx, Vector(nx * nx, 0)},
                        Matrix{nu, nu, Vector(nu * nu, 0)},
                        Vector(nx, 0),
                        Vector(nx, 0),
                        horizon};
    task.reference[2] = 1;
    for (const auto index : std::vector<std::size_t>{2, 3, 4, 5})
        task.Q.values[index * nx + index] = 10;
    for (const auto index : std::vector<std::size_t>{9, 10, 11})
        task.Q.values[index * nx + index] = 5;
    task.QN = task.Q;
    for (std::size_t i = 0; i < nu; ++i)
        task.R.values[i * nu + i] = .1;
    Vector grid(horizon + 1);
    for (std::size_t i = 0; i < grid.size(); ++i)
        grid[i] = static_cast<double>(i) * model.time_step.value;
    const auto system = take<model::LinearSystem>(model::snapshot(model.system_model(), grid));
    auto profile =
        make_source_task_profile(model.info.id, make_source21_choices(task, model.external.size()));
    if (!std::holds_alternative<NominalMpcTask>(profile))
        throw std::runtime_error("Source21 task profile rejected its explicit OSQP choices");
    const auto mpc_task = std::get<NominalMpcTask>(std::move(profile));
    Vector previous_primal;

    Registry<ConvexPort> registry;
    if (registry.add(
            std::get<Registration<ConvexPort>>(adapters::convex::make_highs_registration())))
        throw std::runtime_error("HiGHS registration failed");
    std::ofstream records(output / "plans.csv");
    if (!records)
        throw std::runtime_error("Could not create plans.csv");
    records << std::setprecision(std::numeric_limits<double>::max_digits10)
            << "replan,kind,stage,coordinate,value\n";
    std::string backend_version, backend_id;
    double total_realized_cost = 0;
    for (std::size_t iteration = 0; iteration < replans; ++iteration) {
        const auto observed_state = task.initial;
        auto compiled = compile_mpc_decision(mpc_task, {0}, observed_state);
        if (!std::holds_alternative<ConvexProgram>(compiled))
            throw std::runtime_error("MPC quadratic program rejected");
        auto program = std::get<ConvexProgram>(std::move(compiled));
        if (!previous_primal.empty()) {
            const auto state_count = (horizon + 1) * nx, control_offset = state_count;
            Vector warm_start(program.quadratic_program().variables().size(), 0);
            for (std::size_t k = 0; k < horizon; ++k) {
                const auto source_state = (k + 1) * nx;
                std::copy_n(previous_primal.begin() + static_cast<std::ptrdiff_t>(source_state), nx,
                            warm_start.begin() + static_cast<std::ptrdiff_t>(k * nx));
                const auto source_control = control_offset + std::min(k + 1, horizon - 1) * nu;
                std::copy_n(
                    previous_primal.begin() + static_cast<std::ptrdiff_t>(source_control), nu,
                    warm_start.begin() + static_cast<std::ptrdiff_t>(control_offset + k * nu));
            }
            std::copy(observed_state.begin(), observed_state.end(), warm_start.begin());
            const auto terminal_control = control_offset + (horizon - 1) * nu;
            const auto terminal_state = horizon * nx;
            auto warm_terminal = take<Vector>(
                system.step({0}, std::span(previous_primal).subspan(state_count - nx, nx),
                            std::span(previous_primal).subspan(terminal_control, nu),
                            Vector(model.external.size(), 0)));
            std::copy(warm_terminal.begin(), warm_terminal.end(),
                      warm_start.begin() + static_cast<std::ptrdiff_t>(terminal_state));
            bool feasible = true;
            for (std::size_t k = 0; k <= horizon; ++k)
                for (std::size_t i = 0; i < nx; ++i) {
                    const double value = warm_start[k * nx + i];
                    if ((mpc_task.state_bounds[k][i].lower &&
                         value < *mpc_task.state_bounds[k][i].lower - 1e-7) ||
                        (mpc_task.state_bounds[k][i].upper &&
                         value > *mpc_task.state_bounds[k][i].upper + 1e-7))
                        feasible = false;
                }
            for (std::size_t k = 0; k < horizon; ++k)
                for (std::size_t i = 0; i < nu; ++i) {
                    const double value = warm_start[control_offset + k * nu + i];
                    if ((mpc_task.control_bounds[k][i].lower &&
                         value < *mpc_task.control_bounds[k][i].lower - 1e-7) ||
                        (mpc_task.control_bounds[k][i].upper &&
                         value > *mpc_task.control_bounds[k][i].upper + 1e-7))
                        feasible = false;
                }
            if (feasible) {
                auto seeded = with_primal_start(program, warm_start);
                if (auto *seeded_program = std::get_if<ConvexProgram>(&seeded))
                    program = std::move(*seeded_program);
            }
        }
        Requirements requirements;
        requirements.output.representation = {"csl.program-result.v1"};
        auto selection =
            prepare_pipeline(select(registry, {{"csl.convex.highs"}, {}}, program, requirements));
        if (!std::holds_alternative<PreparedPipeline<ConvexPort>>(selection))
            throw std::runtime_error("HiGHS selection failed");
        auto &prepared = std::get<PreparedPipeline<ConvexPort>>(selection);
        auto provenance = prepared.provenance();
        backend_version = provenance.front().actual->version;
        backend_id = provenance.front().actual->id.value;
        auto [workspace] = prepared.create();
        auto outcome =
            workspace->run({std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
                            {},
                            {},
                            {1e-8, 1e-8},
                            "source21-replan"});
        const auto *result = std::get_if<ProgramResult>(&outcome);
        if (!result)
            throw std::runtime_error("Source21 solver returned non-result variant=" +
                                     std::to_string(outcome.index()));
        const auto result_checks = check_program_result(*result, program, Assurance::numerical);
        if (!result->primal || result->termination != Termination::completed ||
            result->outcome.value != MathematicalOutcome::optimal || !result_checks.empty()) {
            std::string detail =
                "Source21 solve rejected at replan " + std::to_string(iteration) +
                " termination=" + std::to_string(static_cast<int>(result->termination)) +
                " outcome=" + std::to_string(static_cast<int>(result->outcome.value)) +
                " diagnostics=" + std::to_string(result_checks.size());
            for (const auto &d : result_checks)
                detail += " " + d.field + ":" + d.explanation;
            detail += " raw=" + result->raw_diagnostics;
            throw std::runtime_error(detail);
        }
        const auto &z = *result->primal;
        previous_primal = z;
        const auto state_count = (horizon + 1) * nx, control_offset = state_count;
        if (!source_history_feasible(
                task, mpc_task.state_bounds.front(), mpc_task.control_bounds.front(),
                std::span(z).first(state_count), std::span(z).subspan(control_offset)))
            throw std::runtime_error(
                "Independent source21 dynamics/bounds check rejected the solver history");
        const double physical_cost = evaluate_source_cost(task, std::span(z).first(state_count),
                                                          std::span(z).subspan(control_offset));
        auto checked =
            evaluate_primal(program, z, {1e-8, 1e-8}, {{"source21-independent-plan-cost"}, "1"});
        if (!std::holds_alternative<ConvexPrimalEvaluation>(checked) ||
            std::abs(std::get<ConvexPrimalEvaluation>(checked).original_objective - physical_cost) >
                1e-5 * (1 + std::abs(physical_cost)))
            throw std::runtime_error("Independent source objective disagrees with compiled QP");
        for (std::size_t k = 0; k <= horizon; ++k)
            for (std::size_t i = 0; i < nx; ++i)
                records << iteration << ",predicted_state," << k << ',' << i << ',' << z[k * nx + i]
                        << '\n';
        for (std::size_t k = 0; k < horizon; ++k)
            for (std::size_t i = 0; i < nu; ++i)
                records << iteration << ",predicted_control," << k << ',' << i << ','
                        << z[control_offset + k * nu + i] << '\n';
        for (std::size_t i = 0; i < nx; ++i)
            records << iteration << ",observed_state,0," << i << ',' << observed_state[i] << '\n';
        for (std::size_t i = 0; i < nu; ++i)
            records << iteration << ",applied_control,0," << i << ',' << z[control_offset + i]
                    << '\n';
        records << iteration << ",independent_plan_cost,0,0," << physical_cost << '\n'
                << iteration << ",program_plan_cost,0,0,"
                << std::get<ConvexPrimalEvaluation>(checked).original_objective << '\n';
        total_realized_cost +=
            evaluate_running_stage(task, observed_state, std::span(z).subspan(control_offset, nu));
        // Feedback execution advances the zero-disturbance model using only u0.
        Vector next =
            take<Vector>(system.step({0}, observed_state, std::span(z).subspan(control_offset, nu),
                                     mpc_task.replay_external[0]));
        for (std::size_t i = 0; i < nx; ++i)
            records << iteration << ",observed_next_state,1," << i << ',' << next[i] << '\n';
        records << iteration << ",realized_running_cost,0,0,"
                << evaluate_running_stage(task, observed_state,
                                          std::span(z).subspan(control_offset, nu))
                << '\n';
        task.initial = std::move(next);
    }
    records.close();
    std::ofstream manifest(output / "run.txt");
    manifest
        << "model=catalogue-2026/model-21/1\nsource=https://osqp.org/docs/examples/mpc.html\nhorizon=10\nfeedback_replans=15\n"
        << "solver=" << backend_id << " version=" << backend_version
        << "\nfixed_external_input=zero\n"
        << "nominal_grid=" << model.time_step.value << ' ' << model.time_step.unit
        << " per stage (native owner catalogue); coordinates=indexed, physical_units=unspecified\n"
        << "outcome=numerical_optimal; no certified bounds or global feedback-policy claim\n"
        << "realized_zero_disturbance_running_cost=" << total_realized_cost
        << " (15 applied stages; no terminal term)\n";
    if (!records || !manifest)
        throw std::runtime_error("Writing output records failed");
    std::cout << "Source21 native MPC: 15 checked feedback replans; backend=" << backend_id
              << " version=" << backend_version
              << " zero-disturbance realized running cost=" << total_realized_cost << '\n';
} catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 1;
}
