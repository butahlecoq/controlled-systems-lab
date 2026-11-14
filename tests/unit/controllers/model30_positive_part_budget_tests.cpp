#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/adapters/convex/highs.hpp>
#include <csl/controllers/discrete_mpc.hpp>
#include <csl/registry/registry.hpp>
#include <doctest/doctest.h>

#include <algorithm>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <variant>

namespace {
using namespace csl;
using namespace csl::controllers;
using csl::model::catalogue::DiscreteModelData;
using csl::optimization::CompiledNominalQuadraticHistory;
using csl::registry::ConvexPort;
using csl::registry::Registration;

NominalMpcTask make_model30_task() {
    auto loaded = model::catalogue::make_discrete_model("catalogue-2026/model-30/1");
    if (!std::holds_alternative<DiscreteModelData>(loaded))
        throw std::runtime_error("Catalogue model 30 is unavailable");
    const auto &data = std::get<DiscreteModelData>(loaded);
    const auto nx = data.coefficients.A.rows;
    const auto nu = data.coefficients.B.cols;
    const auto nw = data.coefficients.E.cols;
    constexpr std::size_t horizon = 2;
    Matrix q{nx, nx, Vector(nx * nx, 0.0)};
    Matrix r{nu, nu, Vector(nu * nu, 0.0)};
    for (std::size_t coordinate = 0; coordinate < nx; ++coordinate)
        q.values[coordinate * nx + coordinate] = 2.0;
    for (std::size_t coordinate = 0; coordinate < nu; ++coordinate)
        r.values[coordinate * nu + coordinate] = 2.0;

    AuthoredTaskChoices choices;
    choices.problem_id = {"example.model30-positive-part"};
    choices.program_id = {"example.model30-positive-part.history-qp"};
    choices.profile_id = "source30-bounds-positive-part-v1";
    choices.objective_id = "authored-identity-quadratic-positive-control-target-v1";
    choices.horizon_id = "authored-fixed-two-transition-v1";
    choices.final_stage = horizon;
    for (std::size_t stage = 0; stage < horizon; ++stage)
        choices.running_costs.push_back(
            {q, Matrix{nx, nu, Vector(nx * nu, 0.0)}, r, Vector(nx, 0.0), Vector(nu, -10.0), 0.0});
    choices.terminal_cost = {q, Vector(nx, 0.0), 0.0};
    choices.forecast_external.assign(horizon, Vector(nw, 0.0));
    choices.forecast_id = "authored-zero-external-forecast-v1";
    choices.replay_external.assign(horizon, Vector(nw, 0.0));
    choices.replay_id = "authored-zero-external-replay-v1";
    auto admitted = make_source_task_profile(data.info.id, choices);
    if (!std::holds_alternative<NominalMpcTask>(admitted))
        throw std::runtime_error("Explicit model 30 task profile was not admitted");
    return std::get<NominalMpcTask>(std::move(admitted));
}

MpcEpisodeEvidence run(const NominalMpcTask &task, EpisodePolicy policy,
                       const Registration<ConvexPort> &registration, const ConvexProgram &program) {
    auto workspace = registration.factory(program);
    if (!workspace)
        throw std::runtime_error("HiGHS did not construct a model 30 workspace");
    const ExecutionContext context{
        std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {},
        {},
        {1e-8, 1e-8},
        "model30-positive-part-budget"};
    return execute_nominal_episode(task, policy, *workspace, context);
}
} // namespace

TEST_CASE("model 30 positive-part budgets survive native open-loop and observed-state MPC") {
    const auto task = make_model30_task();
    REQUIRE(task.control_bounds.size() == task.final_stage);
    REQUIRE(task.control_positive_part_budgets.size() == task.final_stage);
    for (std::size_t stage_index = 0; stage_index < task.control_bounds.size(); ++stage_index) {
        const auto &stage = task.control_bounds[stage_index];
        for (const auto &bound : stage) {
            CHECK(bound.lower == -0.2);
            CHECK(bound.upper == 0.2);
        }
        REQUIRE(task.control_positive_part_budgets[stage_index].size() == 1);
        const auto &budget = task.control_positive_part_budgets[stage_index].front();
        REQUIRE(budget.control_indices.size() == 30);
        CHECK(budget.upper_bound == 1.0);
        for (std::size_t coordinate = 0; coordinate < 30; ++coordinate)
            CHECK(budget.control_indices[coordinate] == coordinate);
    }

    auto compiled = compile_mpc_decision(task, {0}, task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(compiled));
    const auto &history = std::get<CompiledNominalQuadraticHistory>(compiled);
    REQUIRE(history.layout.state_variable_count == 90);
    REQUIRE(history.layout.control_variable_count == 60);
    REQUIRE(history.layout.auxiliary_variable_count == 60);
    REQUIRE(history.layout.total_variable_count == 210);
    CHECK(history.program.quadratic_program().constraints().rows() == 212);
    REQUIRE(history.layout.auxiliary_blocks.size() == 2);
    CHECK(history.layout.auxiliary_blocks[0].stage == 0);
    CHECK(history.layout.auxiliary_blocks[0].control_indices.size() == 30);
    CHECK(history.layout.auxiliary_blocks[1].stage == 1);
    CHECK(history.layout.auxiliary_blocks[1].first_variable == 180);

    // A signed sum row admits this point although the source positive-part
    // budget rejects it. Each coordinate still respects the source box.
    Vector counterexample(30, 0.0);
    std::fill_n(counterexample.begin(), 6, 0.1875);
    counterexample[6] = -0.125;
    const auto signed_sum = std::accumulate(counterexample.begin(), counterexample.end(), 0.0);
    const auto positive_sum =
        std::accumulate(counterexample.begin(), counterexample.end(), 0.0,
                        [](double sum, double value) { return sum + std::max(value, 0.0); });
    CHECK(signed_sum == doctest::Approx(1.0));
    CHECK(positive_sum == doctest::Approx(1.125));
    for (const auto value : counterexample)
        CHECK(value >= -0.2);

    const auto registration_result = adapters::convex::make_highs_registration();
    REQUIRE(std::holds_alternative<Registration<ConvexPort>>(registration_result));
    const auto &registration = std::get<Registration<ConvexPort>>(registration_result);
    const auto open_loop =
        run(task, EpisodePolicy::nominal_open_loop, registration, history.program);
    const auto feedback =
        run(task, EpisodePolicy::observed_state_mpc, registration, history.program);
    REQUIRE(feedback.decisions.size() == 2);
    REQUIRE(feedback.decisions[1].variable_layout.has_value());
    CHECK(feedback.decisions[1].variable_layout->horizon == 1);
    CHECK(feedback.decisions[1].variable_layout->state_variable_count == 60);
    CHECK(feedback.decisions[1].variable_layout->control_variable_count == 30);
    CHECK(feedback.decisions[1].variable_layout->auxiliary_variable_count == 30);
    CHECK_FALSE(open_loop.decisions[1].variable_layout.has_value());
    for (const auto *episode : {&open_loop, &feedback}) {
        REQUIRE(episode->stop == EpisodeStop::completed);
        REQUIRE(episode->applied_controls.size() == task.final_stage);
        REQUIRE(episode->decisions.size() == task.final_stage);
        CHECK(episode->realized_states.size() == task.final_stage + 1);
        for (const auto &control : episode->applied_controls) {
            const auto source_total =
                std::accumulate(control.begin(), control.end(), 0.0, [](double sum, double value) {
                    return sum + std::max(value, 0.0);
                });
            CHECK(source_total <= 1.0 + 1e-7);
            for (const auto value : control)
                CHECK(value >= -0.2 - 1e-7);
            for (const auto value : control)
                CHECK(value <= 0.2 + 1e-7);
        }
        REQUIRE(episode->decisions.front().variable_layout.has_value());
        CHECK(episode->decisions.front().variable_layout->total_variable_count == 210);
        REQUIRE(episode->realized_objective.has_value());
        for (std::size_t index = 0; index < episode->decisions.size(); ++index) {
            const auto &decision = episode->decisions[index];
            const bool should_solve = episode == &feedback || index == 0;
            CHECK(decision.solve.has_value() == should_solve);
            if (should_solve) {
                REQUIRE(decision.solve.has_value());
                CHECK(std::holds_alternative<ProgramResult>(*decision.solve));
                REQUIRE(decision.attempt.has_value());
                CHECK(decision.attempt->state == SolveAttemptState::returned_result);
                CHECK(decision.predicted_controls.size() ==
                      task.final_stage - decision.stage.value);
                for (const auto &predicted : decision.predicted_controls)
                    CHECK(predicted.size() == 30);
            }
        }
        double literal_episode_cost = 0.0;
        for (std::size_t stage = 0; stage < task.final_stage; ++stage) {
            const auto &state = episode->realized_states[stage];
            const auto &control = episode->applied_controls[stage];
            for (std::size_t i = 0; i < state.size(); ++i)
                literal_episode_cost += state[i] * state[i];
            for (const auto value : control)
                literal_episode_cost += value * value - 10.0 * value;
        }
        for (const auto value : episode->realized_states.back())
            literal_episode_cost += value * value;
        CHECK(*episode->realized_objective == doctest::Approx(literal_episode_cost));
    }
}
