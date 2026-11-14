#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/controllers/discrete_mpc.hpp>
#include <doctest/doctest.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
using namespace csl;
using namespace csl::controllers;
using csl::model::catalogue::DiscreteModelData;
using csl::optimization::CompiledNominalQuadraticHistory;
using csl::optimization::QuadraticHistoryStageCost;

std::variant<DiscreteModelData, Diagnostics> load_model(std::size_t number) {
    return csl::model::catalogue::make_discrete_model("catalogue-2026/model-" +
                                                      std::to_string(number) + "/1");
}

AuthoredTaskChoices choices_for(const DiscreteModelData &data, std::size_t horizon = 2) {
    const auto nx = data.coefficients.A.rows;
    const auto nu = data.coefficients.B.cols;
    const auto nw = data.coefficients.E.cols;
    Matrix q{nx, nx, Vector(nx * nx, 0.0)};
    Matrix r{nu, nu, Vector(nu * nu, 0.0)};
    for (std::size_t i = 0; i < nx; ++i)
        q.values[i * nx + i] = 2.0;
    for (std::size_t i = 0; i < nu; ++i)
        r.values[i * nu + i] = 2.0;
    std::vector<QuadraticHistoryStageCost> running;
    for (std::size_t stage = 0; stage < horizon; ++stage)
        running.push_back(
            {q, Matrix{nx, nu, Vector(nx * nu, 0.0)}, r, Vector(nx, 0.0), Vector(nu, 0.0), 0.0});
    return {{"authored-task-" + std::string(data.info.id)},
            {"authored-program-" + std::string(data.info.id)},
            "authored-profile",
            "raw-identity-quadratic-v1",
            "two-stage-test-v1",
            horizon,
            running,
            QuadraticTerminal{q, Vector(nx, 0.0), 0.0},
            std::vector<Vector>(horizon, Vector(nw, 0.0)),
            "zero-forecast-test",
            std::vector<Vector>(horizon, Vector(nw, 0.0)),
            "zero-replay-test"};
}

NominalMpcTask task_for(std::size_t number, AuthoredTaskChoices choices) {
    auto loaded = load_model(number);
    if (!std::holds_alternative<DiscreteModelData>(loaded))
        throw std::runtime_error("catalogue model not found");
    const auto &data = std::get<DiscreteModelData>(loaded);
    if (number == 4 || number == 9 || number == 10)
        choices.domain_choice = DomainChoice::explicit_continuous_relaxation;
    if (number == 24 || number == 25 || number == 27) {
        choices.domain_choice = DomainChoice::authored_continuous_domain;
        choices.authored_state_bounds =
            std::vector<Interval>(data.coefficients.A.rows, Interval{-100.0, 100.0});
        choices.authored_control_bounds =
            std::vector<Interval>(data.coefficients.B.cols, Interval{-100.0, 100.0});
    }
    if (number == 3 || number == 11 || number == 18 || number == 31)
        choices.arrival_availability = ArrivalAvailability::before_decision;
    auto admission = make_source_task_profile(data.info.id, choices);
    if (!std::holds_alternative<NominalMpcTask>(admission))
        throw std::runtime_error("model profile was not admitted");
    return std::get<NominalMpcTask>(std::move(admission));
}

std::size_t find_control_budget_row(const auto &qp, std::size_t state_count,
                                    std::span<const std::size_t> budget_controls, double upper) {
    for (std::size_t row = 0; row < qp.rows().size(); ++row) {
        if (!qp.rows()[row].upper || *qp.rows()[row].upper != upper || qp.rows()[row].lower)
            continue;
        bool matches = true;
        for (std::size_t column = 0; column < state_count; ++column)
            matches = matches && qp.constraints()(row, column) == 0.0;
        for (std::size_t column = 0; column + state_count < qp.constraints().cols(); ++column) {
            const bool selected = std::find(budget_controls.begin(), budget_controls.end(),
                                            column) != budget_controls.end();
            matches =
                matches && qp.constraints()(row, state_count + column) == (selected ? 1.0 : 0.0);
        }
        if (matches)
            return row;
    }
    throw std::runtime_error("Compiled QP did not retain the source control-budget row");
}
} // namespace

TEST_CASE("source profile factory records an explicit admission for every catalogue model") {
    const auto models = csl::model::catalogue::discrete_models();
    REQUIRE(models.size() == 35);
    std::size_t runnable = 0;
    for (std::size_t i = 1; i <= models.size(); ++i) {
        const auto expected_model_id = "catalogue-2026/model-" + std::to_string(i) + "/1";
        CHECK(models[i - 1].id == expected_model_id);
        auto loaded = load_model(i);
        REQUIRE(std::holds_alternative<DiscreteModelData>(loaded));
        auto data = std::get<DiscreteModelData>(std::move(loaded));
        auto choices = choices_for(data, 1);
        if (i == 4 || i == 9 || i == 10)
            choices.domain_choice = DomainChoice::explicit_continuous_relaxation;
        if (i == 24 || i == 25 || i == 27) {
            choices.domain_choice = DomainChoice::authored_continuous_domain;
            choices.authored_state_bounds =
                std::vector<Interval>(data.coefficients.A.rows, Interval{-100.0, 100.0});
            choices.authored_control_bounds =
                std::vector<Interval>(data.coefficients.B.cols, Interval{-100.0, 100.0});
        }
        if (i == 3 || i == 11 || i == 18 || i == 31)
            choices.arrival_availability = ArrivalAvailability::before_decision;
        auto admission = make_source_task_profile(data.info.id, choices);
        REQUIRE(std::holds_alternative<NominalMpcTask>(admission));
        CHECK(std::get<NominalMpcTask>(admission).provenance.model_id == data.info.id);
        if (i == 30) {
            const auto &task = std::get<NominalMpcTask>(admission);
            REQUIRE(task.control_positive_part_budgets.size() == task.final_stage);
            REQUIRE(task.control_positive_part_budgets[0].size() == 1);
            CHECK(task.control_positive_part_budgets[0][0].upper_bound == 1.0);
            CHECK(task.control_positive_part_budgets[0][0].control_indices.size() == 30);
        }
        ++runnable;
    }
    CHECK(runnable == 35);
}

TEST_CASE("profile choices do not silently relax integer or source-availability semantics") {
    auto integer_model = std::get<DiscreteModelData>(load_model(9));
    auto integer_choices = choices_for(integer_model, 1);
    auto integer_admission = make_source_task_profile(integer_model.info.id, integer_choices);
    REQUIRE(std::holds_alternative<DeferredTask>(integer_admission));
    CHECK(std::get<DeferredTask>(integer_admission).reason.find("integer") != std::string::npos);

    auto arrival_model = std::get<DiscreteModelData>(load_model(31));
    auto arrival_choices = choices_for(arrival_model, 1);
    auto arrival_admission = make_source_task_profile(arrival_model.info.id, arrival_choices);
    REQUIRE(std::holds_alternative<DeferredTask>(arrival_admission));
    CHECK(std::get<DeferredTask>(arrival_admission).reason.find("before-decision") !=
          std::string::npos);
}

TEST_CASE("source21 bounds are owned by the source profile consumed by its caller") {
    const auto data = std::get<DiscreteModelData>(load_model(21));
    const auto task = task_for(21, choices_for(data, 2));
    REQUIRE(task.state_bounds.size() == 3);
    REQUIRE(task.control_bounds.size() == 2);
    for (const auto &stage : task.state_bounds) {
        CHECK(stage[0].lower == doctest::Approx(-std::acos(-1.0) / 6.0));
        CHECK(stage[0].upper == doctest::Approx(std::acos(-1.0) / 6.0));
        CHECK(stage[1].lower == doctest::Approx(-std::acos(-1.0) / 6.0));
        CHECK(stage[1].upper == doctest::Approx(std::acos(-1.0) / 6.0));
        CHECK(stage[5].lower == doctest::Approx(-1.0));
        CHECK_FALSE(stage[5].upper.has_value());
    }
    for (const auto &stage : task.control_bounds)
        for (const auto &bound : stage) {
            CHECK(bound.lower == doctest::Approx(-0.9916));
            CHECK(bound.upper == doctest::Approx(2.4084));
        }
}

TEST_CASE("model 26 source headway is a coupled transition and terminal state constraint") {
    auto task = task_for(26, choices_for(std::get<DiscreteModelData>(load_model(26)), 2));
    REQUIRE(task.stage_constraints.size() == 2);
    REQUIRE(task.stage_constraints.front().bounds.size() == 9);
    REQUIRE(task.terminal_state_constraints.size() == 1);
    CHECK(task.terminal_state_constraints.front().bounds.size() == 9);
    CHECK(task.terminal_state_constraints.front().state_map.values[0] == 1.0);
    CHECK(task.terminal_state_constraints.front().state_map.values[3] == -1.0);
    CHECK(task.terminal_state_constraints.front().state_map.values[4] == -1.2);

    auto compiled = compile_mpc_decision(task, {0}, task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(compiled));
    const auto &program = std::get<CompiledNominalQuadraticHistory>(compiled).program;
    const auto &qp = program.quadratic_program();
    CHECK(qp.constraints().rows() ==
          137); // initial/dynamics, control bounds, stage + terminal rows
    CHECK(qp.rows()[110].lower == 2.0);
    CHECK(qp.constraints()(110, 0) == 1.0);
    CHECK(qp.constraints()(110, 3) == -1.0);
    CHECK(qp.constraints()(110, 4) == -1.2);
    CHECK(qp.rows()[128].lower == 2.0);
    CHECK(qp.constraints()(128, 60) == 1.0); // terminal x[T], no terminal control column
    CHECK(qp.constraints()(128, 63) == -1.0);
    CHECK(qp.constraints()(128, 64) == -1.2);
}

TEST_CASE("interleaved model 34 and 35 resource budgets use their source control channels") {
    const auto verify = [](std::size_t model_number, double budget_upper,
                           std::vector<std::size_t> resource_controls, double resource_amount,
                           double other_channel_amount) {
        const auto data = std::get<DiscreteModelData>(load_model(model_number));
        auto task = task_for(model_number, choices_for(data, 1));
        REQUIRE(task.stage_constraints.size() == 1);
        REQUIRE(task.stage_constraints.front().bounds.size() == 1);
        const auto &row = task.stage_constraints.front();
        REQUIRE(row.control_map.rows == 1);
        REQUIRE(row.control_map.cols == data.coefficients.B.cols);
        CHECK(row.bounds.front().upper == budget_upper);

        auto compiled = compile_mpc_decision(task, {0}, task.initial.point);
        REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(compiled));
        const auto &qp =
            std::get<CompiledNominalQuadraticHistory>(compiled).program.quadratic_program();
        const auto state_count = 2 * data.coefficients.A.rows;
        const auto budget_row =
            find_control_budget_row(qp, state_count, resource_controls, budget_upper);
        Vector resource_only(data.coefficients.B.cols, 0.0);
        Vector other_channel(data.coefficients.B.cols, 0.0);
        for (const auto index : resource_controls)
            resource_only[index] = resource_amount;
        for (std::size_t index = 0; index < other_channel.size(); ++index)
            if (std::find(resource_controls.begin(), resource_controls.end(), index) ==
                resource_controls.end())
                other_channel[index] = other_channel_amount;

        const auto compiled_lhs = [&](std::span<const double> controls) {
            double value = 0.0;
            for (std::size_t index = 0; index < controls.size(); ++index)
                value += qp.constraints()(budget_row, state_count + index) * controls[index];
            return value;
        };
        const auto source_lhs = [&](std::span<const double> controls) {
            double value = 0.0;
            for (const auto index : resource_controls)
                value += controls[index];
            return value;
        };
        for (const auto *candidate : {&resource_only, &other_channel})
            for (std::size_t index = 0; index < candidate->size(); ++index) {
                const auto &bound = task.control_bounds[0][index];
                const bool satisfies_lower = !bound.lower || candidate->at(index) >= *bound.lower;
                const bool satisfies_upper = !bound.upper || candidate->at(index) <= *bound.upper;
                CHECK(satisfies_lower);
                CHECK(satisfies_upper);
            }

        CHECK(compiled_lhs(resource_only) == source_lhs(resource_only));
        CHECK(compiled_lhs(resource_only) > budget_upper);
        CHECK(source_lhs(resource_only) > budget_upper);
        CHECK(compiled_lhs(other_channel) == source_lhs(other_channel));
        CHECK(compiled_lhs(other_channel) <= budget_upper);
        CHECK(source_lhs(other_channel) <= budget_upper);
    };

    std::vector<std::size_t> model34_gpu_controls;
    for (std::size_t index = 0; index < 16; index += 2)
        model34_gpu_controls.push_back(index);
    verify(34, 50.0, model34_gpu_controls, 10.0, 10.0);

    std::vector<std::size_t> model35_radio_controls;
    for (std::size_t index = 0; index < 24; index += 2)
        model35_radio_controls.push_back(index);
    verify(35, 8.0, model35_radio_controls, 1.0, 1.0);
}

TEST_CASE(
    "remaining-horizon compiler shifts forecast rows and preserves cross-Hessian convention") {
    auto data = std::get<DiscreteModelData>(load_model(31));
    auto choices = choices_for(data, 2);
    choices.forecast_external[0][0] = 2.0;
    auto task = task_for(31, choices);
    REQUIRE(task.stage_constraints.size() == 2);
    const auto &availability = task.stage_constraints.front();
    CHECK(availability.control_map.values[0] == 1.0);
    CHECK(availability.state_map.values[0] == -1.0);
    CHECK(availability.external_map.values[0] == -1.0);
    auto compiled = compile_mpc_decision(task, {0}, task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(compiled));
    const auto &full_qp =
        std::get<CompiledNominalQuadraticHistory>(compiled).program.quadratic_program();
    CHECK(full_qp.rows()[132].upper == 2.0); // state/control bounds precede availability rows

    const auto suffix = compile_mpc_decision(task, {1}, task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(suffix));
    CHECK(std::get<CompiledNominalQuadraticHistory>(suffix)
              .program.quadratic_program()
              .constraints()
              .rows() == 96);

    auto two_state = std::get<DiscreteModelData>(load_model(7));
    auto cross_choices = choices_for(two_state, 1);
    cross_choices.running_costs[0].state_control_hessian.values[0] = 0.25;
    auto cross_task = task_for(7, std::move(cross_choices));
    auto cross_program = compile_mpc_decision(cross_task, {0}, cross_task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(cross_program));
    const auto &hessian = std::get<CompiledNominalQuadraticHistory>(cross_program)
                              .program.quadratic_program()
                              .hessian();
    const std::size_t state_count = 4;
    CHECK(hessian(0, state_count) == doctest::Approx(0.25));
    CHECK(hessian(state_count, 0) == doctest::Approx(0.25));
}

TEST_CASE("authored terminal constraints cannot encode a control at the terminal stage") {
    auto data = std::get<DiscreteModelData>(load_model(7));
    auto choices = choices_for(data, 1);
    choices.terminal_state_constraints.push_back({Matrix{1, 2, {1.0, 0.0}}, {{0.0, 2.0}}});
    auto task = task_for(7, std::move(choices));
    auto compiled = compile_mpc_decision(task, {0}, task.initial.point);
    REQUIRE(std::holds_alternative<CompiledNominalQuadraticHistory>(compiled));
    const auto &qp =
        std::get<CompiledNominalQuadraticHistory>(compiled).program.quadratic_program();
    CHECK(qp.constraints().rows() == 11);  // initial, dynamics, state/control bounds, one terminal
    CHECK(qp.constraints()(10, 2) == 1.0); // terminal x1 first state
}

TEST_CASE("profile admission rejects malformed authored schedules and bounds") {
    const auto data = std::get<DiscreteModelData>(load_model(7));
    auto wrong_forecast = choices_for(data, 2);
    wrong_forecast.forecast_external[1].push_back(1.0);
    auto forecast_admission = make_source_task_profile(data.info.id, wrong_forecast);
    REQUIRE(std::holds_alternative<Diagnostics>(forecast_admission));
    CHECK(std::get<Diagnostics>(forecast_admission).front().field ==
          "task.choices.forecast_external");

    auto nonfinite_replay = choices_for(data, 2);
    nonfinite_replay.replay_external[0][0] = std::numeric_limits<double>::infinity();
    auto replay_admission = make_source_task_profile(data.info.id, nonfinite_replay);
    REQUIRE(std::holds_alternative<Diagnostics>(replay_admission));
    CHECK(std::get<Diagnostics>(replay_admission).front().field == "task.choices.replay_external");

    auto empty_intersection = choices_for(data, 2);
    empty_intersection.authored_control_bounds =
        std::vector<Interval>(data.coefficients.B.cols, Interval{11.0, 30.0});
    auto bound_admission = make_source_task_profile(data.info.id, empty_intersection);
    REQUIRE(std::holds_alternative<Diagnostics>(bound_admission));
    CHECK(std::get<Diagnostics>(bound_admission).front().field == "task.bounds.intersection");

    auto malformed_terminal = choices_for(data, 2);
    malformed_terminal.terminal_state_constraints.push_back(
        {Matrix{1, data.coefficients.A.rows + 1, Vector(data.coefficients.A.rows + 1, 1.0)},
         {{0.0, 1.0}}});
    auto terminal_admission = make_source_task_profile(data.info.id, malformed_terminal);
    REQUIRE(std::holds_alternative<Diagnostics>(terminal_admission));
    CHECK(std::get<Diagnostics>(terminal_admission).front().field ==
          "task.choices.terminal_state_constraints");
}
