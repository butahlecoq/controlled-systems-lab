#include <csl/adapters/convex/highs.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/provider.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <functional>
#include <map>
#include <limits>
#include <memory>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;

constexpr std::size_t episode_steps = 4;
constexpr std::size_t fixed_lookahead = 2;
constexpr double dt = 0.1;
constexpr double qp_tie_tolerance = 1e-7;
constexpr std::uint64_t deadline_ns = 50'000'000;
constexpr std::array<double, 2> actions{-1.0, 1.0};
constexpr std::array<double, 2> disturbances{-1.0, 1.0};
constexpr std::array<double, 4> discrete_a{
    0.99505392003313353, 0.099838375271514387,
    -0.099838375271514387, 0.99505392003313353};
constexpr std::array<double, 2> discrete_b{0.0049460799668663343, 0.099838375271514443};
constexpr std::array<double, 2> discrete_e{0.099838375271514443, -0.0049460799668663343};
using State = std::array<double, 3>;

class DeadlineExceeded : public std::runtime_error {
public:
    explicit DeadlineExceeded(const std::string& reason) : std::runtime_error(reason) {}
};

struct SelectedPlan {
    std::vector<double> controls;
    double squared_objective{};
    double primary_squared_objective{};
    std::uint64_t elapsed_ns{};
    std::uint64_t primary_solve_ns{};
    std::uint64_t tie_solve_ns{};
    std::string solver_status{"not_run"};
    std::string provider_id;
    std::string provider_version;
    Json solver_residuals{nullptr};
};

using ConvexProvider = PreparedProvider<ConvexPort>;

template<class T> T take(std::variant<T, Diagnostic> value) {
    if(const auto* error = std::get_if<Diagnostic>(&value))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(value));
}

sets::SetData vertices(std::string id, Matrix rows) {
    const auto dimension = rows.cols;
    return take(sets::make_v({{std::move(id)}, dimension, {}},
        {take(numeric::snapshot(std::move(rows))),
         take(numeric::snapshot(Matrix{0, dimension, {}}))}));
}

sets::SetData point(std::string id, const State& state) {
    return vertices(std::move(id), Matrix{1, state.size(),
        {state[0], state[1], state[2]}});
}

FiniteActionMinimaxRequest make_request(const State& initial, std::size_t horizon,
                                   bool robust, const std::array<double, 3>& direction,
                                   std::size_t component) {
    Matrix transition{3, 3, {1.0, 0.0, 0.0,
        0.0, discrete_a[0], discrete_a[1],
        0.0, discrete_a[2], discrete_a[3]}};
    Matrix control{3, 1, {0.0, discrete_b[0], discrete_b[1]}};
    Matrix external{3, 1, {0.0, discrete_e[0], discrete_e[1]}};
    Vector offset{0.1, 0.0, 0.0};
    LinearStage stage{std::move(transition), std::move(control), std::move(external), std::move(offset)};
    const SystemModel authored{{{3, 1, 1}, TimeDomain::discrete, std::move(stage)}, {}};
    std::vector<double> times;
    times.reserve(horizon + 1);
    for(std::size_t i = 0; i <= horizon; ++i)
        times.push_back(initial[0] + dt * static_cast<double>(i));
    auto system = take(model::snapshot(authored, std::move(times)));

    std::vector<Vector> action_points;
    for(const double action : actions) action_points.push_back({action});
    std::vector<sets::SetData> disturbance_sets;
    disturbance_sets.reserve(horizon);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(robust) {
            disturbance_sets.push_back(vertices("mpc04-disturbance-" +
                std::to_string(component) + "-" + std::to_string(stage),
                Matrix{2, 1, {disturbances[0], disturbances[1]}}));
        } else {
            disturbance_sets.push_back(vertices("mpc04-nominal-disturbance-" +
                std::to_string(component) + "-" + std::to_string(stage),
                Matrix{1, 1, {0.0}}));
        }
    }
    std::vector<sets::SetData> safe;
    safe.reserve(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        safe.push_back(take(sets::make_universal(
            {{"mpc04-unconstrained-" + std::to_string(stage)}, 3, {}})));
    const auto terminal = std::get<Objective>(snapshot(LinearTerminal{
        {direction[0], direction[1], direction[2]}, 0.0}));
    return {{"mpc04-max-coordinate-replanning"}, {"mpc04-finite-mpc"},
        std::move(system), point("mpc04-initial", initial),
        {1, std::move(action_points)}, std::move(disturbance_sets),
        std::move(safe), terminal};
}

SelectedPlan choose_plan(const State& state, std::size_t horizon, bool robust) {
    constexpr double tie_tolerance = 1e-12;
    constexpr std::array<std::array<double, 3>, 4> directions{{
        {0.0, 1.0, 0.0}, {0.0, -1.0, 0.0},
        {0.0, 0.0, 1.0}, {0.0, 0.0, -1.0}}};
    const auto start = Clock::now();
    std::vector<std::vector<double>> plan_controls;
    std::vector<double> combined;
    std::size_t plan_count = 0;
    for(std::size_t component = 0; component < directions.size(); ++component) {
        auto input = make_request(state, horizon, robust, directions[component], component);
        const auto limits = FiniteActionMinimaxLimits{
            std::size_t{1} << horizon, 256, tie_tolerance};
        auto outcome = finite_action_minimax(input, limits);
        const auto* optimum = std::get_if<FiniteMinimaxOptimal>(&outcome);
        if(!optimum) throw std::runtime_error("finite_action_minimax did not return a plan optimum");
        if(component == 0) {
            plan_count = optimum->plans.size();
            plan_controls.reserve(plan_count);
            combined.assign(plan_count, -std::numeric_limits<double>::infinity());
            for(const auto& record : optimum->plans) {
                const auto* feasible = std::get_if<FinitePlanFeasible>(&record);
                if(!feasible) throw std::runtime_error("unconstrained plan was rejected");
                std::vector<double> controls;
                for(const auto index : feasible->action_indices) {
                    if(index >= actions.size()) throw std::runtime_error("action index is outside catalogue");
                    controls.push_back(actions[index]);
                }
                plan_controls.push_back(std::move(controls));
            }
        } else if(optimum->plans.size() != plan_count) {
            throw std::runtime_error("signed-coordinate solves returned different plan counts");
        }
        for(std::size_t i = 0; i < optimum->plans.size(); ++i) {
            const auto* feasible = std::get_if<FinitePlanFeasible>(&optimum->plans[i]);
            if(!feasible) throw std::runtime_error("unconstrained plan was rejected");
            combined[i] = std::max(combined[i], feasible->worst_value);
        }
    }
    if(plan_controls.empty()) throw std::runtime_error("empty finite action catalogue");
    std::size_t best = 0;
    for(std::size_t i = 1; i < combined.size(); ++i) {
        if(combined[i] < combined[best] - tie_tolerance) best = i;
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - start).count();
    const double nonnegative = std::max(0.0, combined[best]);
    const auto squared = nonnegative * nonnegative;
    return {std::move(plan_controls[best]), squared, squared,
            static_cast<std::uint64_t>(elapsed), static_cast<std::uint64_t>(elapsed), 0,
            "optimal", "csl.finite_action_minimax", ""};
}

struct TerminalAffine {
    std::array<double, 2> offset{};
    std::vector<std::array<double, 2>> controls;
};

enum class QpDisturbanceMode { nominal_zero, finite_binary };

struct QpPlanRequest {
    State observed_state;
    std::size_t remaining_horizon;
    QpDisturbanceMode disturbance_mode;
    std::uint64_t serial;
};

std::vector<std::vector<double>> planning_histories(std::size_t horizon, QpDisturbanceMode mode) {
    if(mode == QpDisturbanceMode::nominal_zero) return {std::vector<double>(horizon, 0.0)};
    std::vector<std::vector<double>> histories{{}};
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        std::vector<std::vector<double>> next;
        next.reserve(histories.size() * disturbances.size());
        for(const auto& prefix : histories) for(const double disturbance : disturbances) {
            auto history = prefix;
            history.push_back(disturbance);
            next.push_back(std::move(history));
        }
        histories = std::move(next);
    }
    return histories;
}

TerminalAffine terminal_affine(const State& initial, const std::vector<double>& history) {
    TerminalAffine terminal{{initial[1], initial[2]}, {}};
    terminal.controls.reserve(history.size());
    for(std::size_t stage = 0; stage < history.size(); ++stage) {
        const auto offset = terminal.offset;
        terminal.offset = {
            discrete_a[0] * offset[0] + discrete_a[1] * offset[1] + discrete_e[0] * history[stage],
            discrete_a[2] * offset[0] + discrete_a[3] * offset[1] + discrete_e[1] * history[stage]};
        for(auto& column : terminal.controls) {
            const auto previous = column;
            column = {discrete_a[0] * previous[0] + discrete_a[1] * previous[1],
                      discrete_a[2] * previous[0] + discrete_a[3] * previous[1]};
        }
        terminal.controls.push_back(discrete_b);
    }
    return terminal;
}

ConvexProvider make_qp_provider() {
    auto registration_result = adapters::convex::make_highs_registration();
    auto* registration = std::get_if<Registration<ConvexPort>>(&registration_result);
    if(!registration) {
        const auto& diagnostics = std::get<Diagnostics>(registration_result);
        std::ostringstream message;
        for(const auto& item : diagnostics) message << item.field << ": " << item.explanation << "; ";
        throw std::runtime_error("HiGHS convex registration failed: " + message.str());
    }
    Registry<ConvexPort> registry;
    const Method method{registration->identity.id, registration->identity.version};
    if(registry.add(std::move(*registration))) throw std::runtime_error("HiGHS convex registry rejected registration");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto result = prepare_provider(select_provider(registry, method, requirements));
    if(const auto* rejected = std::get_if<Rejection>(&result)) {
        std::ostringstream message;
        for(const auto& item : rejected->diagnostics) message << item.field << ": " << item.explanation << "; ";
        throw std::runtime_error("HiGHS convex provider preparation failed: " + message.str());
    }
    return std::get<ConvexProvider>(std::move(result));
}

ConvexProgram make_qp_program(const std::string& id,
                              const std::vector<TerminalAffine>& scenarios,
                              std::size_t horizon,
                              double rho_upper,
                              bool tie_break) {
    const auto variables = horizon + 1;
    std::vector<std::size_t> row_offsets{0}, column_indices;
    Vector coefficients;
    std::vector<Interval> rows;
    rows.reserve(scenarios.size() * 4);
    for(const auto& scenario : scenarios) {
        for(std::size_t coordinate = 0; coordinate < 2; ++coordinate) {
            for(const double sign : {1.0, -1.0}) {
                for(std::size_t control = 0; control < horizon; ++control) {
                    const double value = sign * scenario.controls[control][coordinate];
                    if(value != 0.0) {
                        column_indices.push_back(control);
                        coefficients.push_back(value);
                    }
                }
                column_indices.push_back(horizon);
                coefficients.push_back(-1.0);
                row_offsets.push_back(coefficients.size());
                rows.push_back({std::nullopt, -sign * scenario.offset[coordinate]});
            }
        }
    }

    std::vector<Interval> variable_bounds(horizon, {-1.0, 1.0});
    variable_bounds.push_back({0.0, tie_break ? std::optional<double>{rho_upper} : std::nullopt});
    Vector q(variables, 0.0);
    Vector Q(variables * variables, 0.0);
    if(tie_break) {
        for(std::size_t control = 0; control < horizon; ++control) Q[control * variables + control] = 2.0;
    } else {
        Q[horizon * variables + horizon] = 2.0;
    }
    auto result = optimization::make_convex_program({
        {ProblemId{"mpc04-max-coordinate-replanning"}, ProgramId{id}},
        QuadraticTerminal{Matrix{variables, variables, std::move(Q)}, std::move(q), 0.0},
        SparseMatrix{rows.size(), variables, std::move(row_offsets),
                     std::move(column_indices), std::move(coefficients)},
        std::move(variable_bounds), std::move(rows), {}});
    if(const auto* program = std::get_if<ConvexProgram>(&result)) return *program;
    std::ostringstream message;
    if(const auto* diagnostics = std::get_if<Diagnostics>(&result)) {
        for(const auto& item : *diagnostics) message << item.field << ": " << item.explanation << "; ";
    } else {
        message << std::get<OperationStopped>(result).diagnostics;
    }
    throw std::runtime_error("MPC-04 QP construction failed: " + message.str());
}

ProgramResult solve_qp_program(const ConvexProvider& provider, const ConvexProgram& program,
                               Clock::time_point deadline) {
    auto pipeline_result = provider.prepare(program);
    if(const auto* rejected = std::get_if<Rejection>(&pipeline_result)) {
        std::ostringstream message;
        for(const auto& item : rejected->diagnostics) message << item.field << ": " << item.explanation << "; ";
        throw std::runtime_error("MPC-04 QP request rejected: " + message.str());
    }
    auto pipeline = std::get<PreparedPipeline<ConvexPort>>(std::move(pipeline_result));
    auto [workspace] = pipeline.create();
    ExecutionContext context;
    context.numerical = {1e-8, 1e-8};
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    context.deadline = deadline;
    auto outcome = workspace->run(context);
    if(const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        std::ostringstream message;
        for(const auto& item : unsupported->diagnostics) message << item.field << ": " << item.explanation << "; ";
        throw std::runtime_error("MPC-04 QP solve unsupported: " + message.str());
    }
    auto result = std::get<ProgramResult>(std::move(outcome));
    if(result.termination == Termination::deadline_expired || result.termination == Termination::resource_limit)
        throw DeadlineExceeded("HiGHS convex adapter stopped at the MPC-04 decision deadline/resource limit");
    const auto diagnostics = optimization::check_program_result(result, program, Assurance::numerical);
    if(!diagnostics.empty()) {
        std::ostringstream message;
        for(const auto& item : diagnostics) message << item.field << ": " << item.explanation << "; ";
        throw std::runtime_error("MPC-04 QP result validation failed: " + message.str());
    }
    return result;
}

Json residual_evidence(const ProgramResult& result) {
    auto measure = [](const ResidualMeasure& value) {
        return Json{{"violation", value.violation}, {"scale", value.scale}};
    };
    Json primal = nullptr;
    if(result.residuals.primal) {
        const auto& values = *result.residuals.primal;
        primal = { {"rows", measure(values.rows)}, {"variables", measure(values.variables)},
            {"verifier_id", values.context.verifier.id.value},
            {"verifier_version", values.context.verifier.version},
            {"absolute_tolerance", values.context.absolute_tolerance},
            {"relative_tolerance", values.context.relative_tolerance} };
    }
    Json dual = nullptr;
    if(result.residuals.dual) {
        const auto& values = *result.residuals.dual;
        dual = { {"stationarity", values.stationarity ? measure(*values.stationarity) : Json(nullptr)},
            {"signs", values.signs ? measure(*values.signs) : Json(nullptr)},
            {"complementarity", values.complementarity ? measure(*values.complementarity) : Json(nullptr)},
            {"verifier_id", values.context.verifier.id.value},
            {"verifier_version", values.context.verifier.version},
            {"absolute_tolerance", values.context.absolute_tolerance},
            {"relative_tolerance", values.context.relative_tolerance} };
    }
    return {{"primal", std::move(primal)}, {"dual", std::move(dual)}};
}

SelectedPlan choose_qp_plan(const QpPlanRequest& request, const ConvexProvider& provider) {
    const auto& state = request.observed_state;
    const auto horizon = request.remaining_horizon;
    if(horizon == 0 || horizon > episode_steps) throw std::runtime_error("MPC-04 QP horizon is outside the pilot range");
    const auto started = Clock::now();
    const auto deadline = started + std::chrono::nanoseconds(deadline_ns);
    std::vector<TerminalAffine> scenarios;
    for(const auto& history : planning_histories(horizon, request.disturbance_mode))
        scenarios.push_back(terminal_affine(state, history));
    const auto suffix = std::string(request.disturbance_mode == QpDisturbanceMode::finite_binary ? "robust" : "nominal") +
        "-h" + std::to_string(horizon) + "-" + std::to_string(request.serial);
    const auto primary_program = make_qp_program("mpc04-qpm-primary-" + suffix,
        scenarios, horizon, std::numeric_limits<double>::infinity(), false);
    const auto primary_started = Clock::now();
    const auto primary = solve_qp_program(provider, primary_program, deadline);
    const auto primary_elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - primary_started).count();
    if(primary.termination != Termination::completed || primary.outcome.value != MathematicalOutcome::optimal ||
       !primary.primal || primary.primal->size() != horizon + 1)
        throw std::runtime_error("MPC-04 primary QP did not return a completed optimal primal");
    const double primary_rho = primary.primal->back();
    if(!std::isfinite(primary_rho) || primary_rho < -1e-8)
        throw std::runtime_error("MPC-04 primary QP returned an invalid epigraph value");
    const double primary_squared = std::max(0.0, primary_rho) * std::max(0.0, primary_rho);

    const auto tie_program = make_qp_program("mpc04-qpm-tie-" + suffix,
        scenarios, horizon, std::max(0.0, primary_rho) + qp_tie_tolerance, true);
    const auto tie_started = Clock::now();
    const auto tied = solve_qp_program(provider, tie_program, deadline);
    const auto tie_elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - tie_started).count();
    if(tied.termination != Termination::completed || tied.outcome.value != MathematicalOutcome::optimal ||
       !tied.primal || tied.primal->size() != horizon + 1)
        throw std::runtime_error("MPC-04 tie-break QP did not return a completed optimal primal");

    std::vector<double> controls(tied.primal->begin(), tied.primal->begin() + static_cast<std::ptrdiff_t>(horizon));
    const double tied_rho = tied.primal->back();
    if(!std::isfinite(tied_rho) || tied_rho < -1e-8)
        throw std::runtime_error("MPC-04 tie-break QP returned an invalid epigraph value");
    double worst_terminal = 0.0;
    for(const auto& scenario : scenarios) {
        std::array<double, 2> terminal = scenario.offset;
        for(std::size_t control = 0; control < horizon; ++control) {
            terminal[0] += scenario.controls[control][0] * controls[control];
            terminal[1] += scenario.controls[control][1] * controls[control];
        }
        worst_terminal = std::max(worst_terminal, std::max(std::abs(terminal[0]), std::abs(terminal[1])));
    }
    for(const double control : controls)
        if(!std::isfinite(control) || control < -1.0 - 1e-7 || control > 1.0 + 1e-7)
            throw std::runtime_error("MPC-04 tie-break QP returned a control outside [-1,1]");
    if(worst_terminal > primary_rho + qp_tie_tolerance + 1e-7)
        throw std::runtime_error("MPC-04 selected plan exceeds the primary terminal optimum tolerance");
    if(worst_terminal > tied_rho + 1e-7)
        throw std::runtime_error("MPC-04 selected plan violates the tie-break epigraph constraints");

    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - started).count();
    const auto* actual = provider.provenance().actual ? &*provider.provenance().actual : nullptr;
    SelectedPlan selected{std::move(controls), worst_terminal * worst_terminal, primary_squared,
            static_cast<std::uint64_t>(elapsed), static_cast<std::uint64_t>(primary_elapsed),
            static_cast<std::uint64_t>(tie_elapsed), "optimal", actual ? actual->id.value : "unknown",
            actual ? actual->version : "unknown"};
    selected.solver_residuals = {{"primary", residual_evidence(primary)},
                                 {"tie_break", residual_evidence(tied)}};
    return selected;
}

Json check_qp_analytic_fixture(const ConvexProvider& provider, std::uint64_t& serial) {
    const State initial{0.0, 0.1, 0.0};
    const double y_offset = discrete_a[0] * initial[1] + discrete_a[1] * initial[2];
    const double z_offset = discrete_a[2] * initial[1] + discrete_a[3] * initial[2];
    const double crossing = -(y_offset + z_offset) / (discrete_b[0] + discrete_b[1]);
    const double y_terminal = y_offset + discrete_b[0] * crossing;
    const double z_terminal = z_offset + discrete_b[1] * crossing;
    if(crossing < -1.0 || crossing > 1.0 || y_terminal < 0.0 || z_terminal > 0.0 ||
       std::abs(y_terminal + z_terminal) > 1e-12)
        throw std::runtime_error("MPC-04 one-step analytic fixture does not have its expected interior optimum");
    const double expected = std::max(std::abs(y_terminal), std::abs(z_terminal));
    const auto actual = choose_qp_plan(
        {initial, 1, QpDisturbanceMode::nominal_zero, serial++}, provider);
    if(actual.controls.size() != 1 || std::abs(actual.primary_squared_objective - expected * expected) > 2e-6 ||
       actual.squared_objective > expected * expected + 2.0 * expected * qp_tie_tolerance + 1e-6)
        throw std::runtime_error("MPC-04 one-step QP does not match the analytic terminal-only optimum");
    return {{"initial_state", initial}, {"expected_control", crossing},
            {"expected_terminal_squared_objective", expected * expected},
            {"selected_control", actual.controls.front()},
            {"primary_squared_objective", actual.primary_squared_objective},
            {"selected_squared_objective", actual.squared_objective},
            {"solver_residuals", actual.solver_residuals},
            {"tie_tolerance", qp_tie_tolerance}, {"status", actual.solver_status}};
}

State advance(State state, double action, double disturbance) {
    // The pinned source holds both player actions over 100 explicit Euler steps.
    constexpr double h = dt / 100.0;
    for(int i = 0; i < 100; ++i) {
        const double y = state[1];
        const double z = state[2];
        state[1] = y + h * (z + disturbance);
        state[2] = z + h * (-y + action);
    }
    state[0] += dt;
    return state;
}

double source_objective(const State& state) {
    return std::max(std::abs(state[1]), std::abs(state[2]));
}

template<class StateType, class DisturbanceType, class Choose, class Advance>
StateType run_closed_loop(StateType state,
                          const std::vector<DisturbanceType>& disturbance_history,
                          Choose choose, Advance advance) {
    for(std::size_t step = 0; step < disturbance_history.size(); ++step) {
        const auto decision = choose(step, state);
        state = advance(step, state, decision, disturbance_history[step]);
    }
    return state;
}

struct IntegerFixture {
    using StateType = std::vector<int>;
    StateType initial_state;
    std::vector<std::vector<int>> actions;
    std::vector<std::vector<int>> disturbances;
    std::function<StateType(std::size_t, const StateType&, int, int)> transition;
    std::function<int(const StateType&)> score;
};

std::vector<std::vector<int>> suffixes(const std::vector<std::vector<int>>& sets,
                                       std::size_t stage) {
    std::vector<std::vector<int>> output{{}};
    for(std::size_t i = stage; i < sets.size(); ++i) {
        std::vector<std::vector<int>> next;
        for(const auto& prefix : output) for(const int value : sets[i]) {
            auto row = prefix; row.push_back(value); next.push_back(std::move(row));
        }
        output = std::move(next);
    }
    return output;
}

int fixed_plan_value(const IntegerFixture& game, std::size_t stage,
                     const IntegerFixture::StateType& initial,
                     const std::vector<int>& plan) {
    int worst = std::numeric_limits<int>::min();
    for(const auto& disturbance_suffix : suffixes(game.disturbances, stage)) {
        auto state = initial;
        for(std::size_t offset = 0; offset < plan.size(); ++offset)
            state = game.transition(stage + offset, state, plan[offset], disturbance_suffix[offset]);
        worst = std::max(worst, game.score(state));
    }
    return worst;
}

std::pair<int, std::vector<int>> choose_fixture_plan(const IntegerFixture& game,
        std::size_t stage, const IntegerFixture::StateType& state) {
    const auto plans = suffixes(game.actions, stage);
    std::pair<int, std::vector<int>> best{std::numeric_limits<int>::max(), {}};
    for(const auto& plan : plans) {
        const auto value = fixed_plan_value(game, stage, state, plan);
        if(value < best.first || (value == best.first && plan < best.second))
            best = {value, plan};
    }
    return best;
}

int causal_fixture_value(const IntegerFixture& game, std::size_t stage,
                         const IntegerFixture::StateType& state) {
    if(stage == game.actions.size()) return game.score(state);
    int best = std::numeric_limits<int>::max();
    for(const int action : game.actions[stage]) {
        int worst = std::numeric_limits<int>::min();
        for(const int disturbance : game.disturbances[stage]) {
            const auto next = game.transition(stage, state, action, disturbance);
            worst = std::max(worst, causal_fixture_value(game, stage + 1, next));
        }
        best = std::min(best, worst);
    }
    return best;
}

std::string history_key(const std::vector<int>& history) {
    std::string key = "(";
    for(std::size_t i = 0; i < history.size(); ++i) {
        if(i != 0) key += ", ";
        key += std::to_string(history[i]);
    }
    return key + ")";
}

Json check_finite_policy_fixtures() {
    IntegerFixture strict{
        {{0, 0}}, {{0, 1}, {-1, 1}}, {{-1, 0, 1}, {0}},
        [](std::size_t, const std::vector<int>& s, int u, int w) {
            return std::vector<int>{s[0] + u + w, s[0] + s[1] - w};
        },
        [](const std::vector<int>& s) { return s[0] * s[0] + s[1] * s[1]; }};
    IntegerFixture scalar{
        {{0}}, {{0}, {-1, 1}}, {{-1, 1}, {0}},
        [](std::size_t, const std::vector<int>& s, int u, int w) {
            return std::vector<int>{s[0] + u + w};
        },
        [](const std::vector<int>& s) { return std::abs(s[0]); }};

    auto execute = [](const IntegerFixture& game) {
        std::map<std::vector<int>, int> outcomes;
        for(const auto& history : suffixes(game.disturbances, 0)) {
            const auto terminal = run_closed_loop(game.initial_state, history,
                [&](std::size_t stage, const IntegerFixture::StateType& state) {
                    return choose_fixture_plan(game, stage, state).second.front();
                },
                [&](std::size_t stage, const IntegerFixture::StateType& state,
                    int action, int disturbance) {
                    return game.transition(stage, state, action, disturbance);
                });
            outcomes.emplace(history, game.score(terminal));
        }
        return outcomes;
    };
    const auto strict_outcomes = execute(strict);
    const auto scalar_outcomes = execute(scalar);
    const auto strict_fixed = choose_fixture_plan(strict, 0, strict.initial_state).first;
    const auto scalar_fixed = choose_fixture_plan(scalar, 0, scalar.initial_state).first;
    const auto strict_causal = causal_fixture_value(strict, 0, strict.initial_state);
    const auto strict_worst = std::max_element(strict_outcomes.begin(), strict_outcomes.end(),
        [](const auto& a, const auto& b) { return a.second < b.second; })->second;
    const auto scalar_worst = std::max_element(scalar_outcomes.begin(), scalar_outcomes.end(),
        [](const auto& a, const auto& b) { return a.second < b.second; })->second;
    if(strict_fixed != 2 || strict_worst != 2 || strict_causal != 1 ||
       strict_outcomes.at({-1, 0}) != 2 || strict_outcomes.at({0, 0}) != 1 ||
       strict_outcomes.at({1, 0}) != 2 || scalar_fixed != 2 || scalar_worst != 0)
        throw std::runtime_error("closed-loop finite policy-gap fixtures changed");
    Json strict_histories = Json::object(), scalar_histories = Json::object();
    for(const auto& [history, value] : strict_outcomes)
        strict_histories[history_key(history)] = value;
    for(const auto& [history, value] : scalar_outcomes)
        scalar_histories[history_key(history)] = value;
    return {{"strict_two_step", {{"fixed_plan_squared", strict_fixed},
              {"executed_replanning_worst_squared", strict_worst},
              {"causal_squared", strict_causal}, {"history_squared", strict_histories}}},
            {"scalar_two_step", {{"fixed_plan", scalar_fixed},
              {"executed_replanning_worst", scalar_worst},
              {"history_costs", scalar_histories}}}};
}

Json episode(std::string policy, std::string horizon_name,
             const std::array<double, episode_steps>& history,
             const ConvexProvider& qp_provider, std::uint64_t& qp_serial,
             std::uint64_t decision_deadline_ns = deadline_ns,
             bool inject_solver_failure = false) {
    State initial{0.0, 0.2, 0.0};
    Json states = Json::array({initial});
    Json decisions = Json::array();
    std::size_t fallbacks = 0;
    std::vector<double> disturbance_history(history.begin(), history.end());
    const auto state = run_closed_loop(initial, disturbance_history,
        [&](std::size_t step, const State& observed) {
            const auto horizon = horizon_name == "shrinking_to_episode_terminal"
                ? episode_steps - step : fixed_lookahead;
            SelectedPlan plan;
            const auto decision_started = Clock::now();
            std::string status = "solved";
            std::string solver_detail;
            try {
                if(inject_solver_failure)
                    throw std::runtime_error("injected native solver failure");
                if(policy == "nominal_zero_disturbance" || policy == "finite_minimax") {
                    plan = choose_plan(observed, horizon, policy == "finite_minimax");
                } else {
                    const auto mode = policy == "linear_qp_finite_history_robust_linf"
                        ? QpDisturbanceMode::finite_binary : QpDisturbanceMode::nominal_zero;
                    plan = choose_qp_plan({observed, horizon, mode, qp_serial++}, qp_provider);
                }
            } catch(const DeadlineExceeded& error) {
                plan.controls = {0.0};
                plan.squared_objective = std::numeric_limits<double>::quiet_NaN();
                plan.primary_squared_objective = std::numeric_limits<double>::quiet_NaN();
                plan.elapsed_ns = static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - decision_started).count());
                plan.solver_status = "deadline_expired";
                status = "deadline_fallback";
                solver_detail = error.what();
                ++fallbacks;
            } catch(const std::exception& error) {
                plan.controls = {0.0};
                plan.squared_objective = std::numeric_limits<double>::quiet_NaN();
                plan.primary_squared_objective = std::numeric_limits<double>::quiet_NaN();
                plan.elapsed_ns = static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - decision_started).count());
                plan.solver_status = "failed";
                status = "solver_failure_fallback";
                solver_detail = error.what();
                ++fallbacks;
            }
            double action = plan.controls.empty() ? 0.0 : plan.controls.front();
            if(decision_deadline_ns == 0 || plan.elapsed_ns > decision_deadline_ns) {
                action = 0.0;
                status = "deadline_fallback";
                plan.solver_status = "deadline_exceeded";
                solver_detail = "native solve returned after the per-decision deadline; cancellation is unavailable";
                ++fallbacks;
            }
            Json remaining = plan.controls;
            if(status != "solved") remaining = Json::array();
            decisions.push_back({{"step", step}, {"observed_state", observed},
                {"action", action}, {"status", status}, {"requested_horizon", horizon},
                {"effective_horizon", horizon},
                {"planned_squared_objective", std::isfinite(plan.squared_objective)
                    ? Json(plan.squared_objective) : Json(nullptr)},
                {"primary_squared_objective", std::isfinite(plan.primary_squared_objective)
                    ? Json(plan.primary_squared_objective) : Json(nullptr)},
                {"solve_ns", plan.elapsed_ns}, {"remaining_plan", std::move(remaining)},
                {"primary_solve_ns", plan.primary_solve_ns}, {"tie_solve_ns", plan.tie_solve_ns},
                {"solver_residuals", plan.solver_residuals},
                {"solver_status", plan.solver_status}, {"provider_id", plan.provider_id},
                {"provider_version", plan.provider_version},
                {"solver_detail", solver_detail}, {"fallback", status != "solved"}});
            return action;
        },
        [](std::size_t, const State& observed, double action, double disturbance) {
            return advance(observed, action, disturbance);
        });
    // State snapshots are reconstructed from the initial state and each recorded action.
    states = Json::array({initial});
    auto replay_state = initial;
    for(std::size_t i = 0; i < episode_steps; ++i) {
        replay_state = advance(replay_state,
            decisions.at(i).at("action").get<double>(), history[i]);
        states.push_back(replay_state);
    }
    return {{"policy", std::move(policy)}, {"horizon", std::move(horizon_name)},
        {"disturbances", history}, {"states", std::move(states)},
        {"decisions", std::move(decisions)}, {"terminal_state", state},
        {"terminal_original_objective", source_objective(state)},
        {"fallback_count", fallbacks}, {"violations", 0}, {"completed", true}};
}

Json summarize_native_fallback(const Json& row, const std::string& expected_status) {
    Json actions = Json::array();
    Json statuses = Json::array();
    for(const auto& decision : row.at("decisions")) {
        if(decision.at("status") != expected_status || !decision.at("fallback").get<bool>() ||
           decision.at("action").get<double>() != 0.0)
            throw std::runtime_error("native MPC-04 fallback fixture changed");
        actions.push_back(decision.at("action"));
        statuses.push_back(decision.at("status"));
    }
    if(actions.size() != episode_steps || row.at("fallback_count") != episode_steps ||
       !row.at("completed").get<bool>())
        throw std::runtime_error("native MPC-04 fallback episode did not complete as expected");
    return {{"completed", row.at("completed")}, {"fallback_count", row.at("fallback_count")},
            {"steps", actions.size()}, {"statuses", std::move(statuses)},
            {"actions", std::move(actions)}};
}

Json check_native_fallback_semantics(const ConvexProvider& provider, std::uint64_t& serial) {
    const std::array<double, episode_steps> history{};
    const auto deadline_row = episode("linear_qp_nominal_linf", "shrinking_to_episode_terminal",
        history, provider, serial, 0, false);
    const auto failure_row = episode("linear_qp_nominal_linf", "shrinking_to_episode_terminal",
        history, provider, serial, deadline_ns, true);
    return {{"deadline", summarize_native_fallback(deadline_row, "deadline_fallback")},
            {"solver_failure", summarize_native_fallback(failure_row, "solver_failure_fallback")}};
}

Json run(bool reverse_policy_order) {
    Json episodes = Json::array();
    const auto provider_setup_started = Clock::now();
    const auto qp_provider = make_qp_provider();
    const auto provider_setup_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - provider_setup_started).count());
    std::uint64_t qp_serial = 0;
    const auto qp_fixture = check_qp_analytic_fixture(qp_provider, qp_serial);
    const auto fallback_fixtures = check_native_fallback_semantics(qp_provider, qp_serial);
    std::vector<std::string> policies{"nominal_zero_disturbance", "finite_minimax",
        "linear_qp_nominal_linf", "linear_qp_finite_history_robust_linf"};
    if(reverse_policy_order) std::reverse(policies.begin(), policies.end());
    for(const std::string& policy : policies) {
        for(const std::string horizon : {"shrinking_to_episode_terminal",
                                         "moving_fixed_2_stage_lookahead"}) {
            for(const double v0 : disturbances) for(const double v1 : disturbances)
                for(const double v2 : disturbances) for(const double v3 : disturbances)
                    episodes.push_back(episode(policy, horizon, {v0, v1, v2, v3}, qp_provider, qp_serial));
        }
    }
    return {{"episodes", std::move(episodes)},
            {"controller_order", policies},
            {"fixtures", check_finite_policy_fixtures()},
            {"qp_analytic_fixture", qp_fixture},
            {"native_fallback_fixtures", fallback_fixtures},
            {"qp_metadata", {{"provider_id", qp_provider.provenance().actual->id.value},
                {"provider_version", qp_provider.provenance().actual->version},
                {"provider_setup_ns", provider_setup_ns},
                {"objective", "terminal squared max-coordinate via scalar epigraph"},
                {"action_domain", "continuous [-1,1] per stage"},
                {"tie_tolerance", qp_tie_tolerance},
                {"tie_selector", "second QP minimizes sum(u_i^2) subject to primary epigraph <= optimum + 1e-7"},
                {"warm_start", "none; each primary and tie solve uses a fresh workspace"},
                {"robust_plan_semantics", "one common open-loop control vector constrained against every complete finite disturbance history; execute first action and replan after full-state observation"}}}};
}
}

int main(int argc, char** argv) {
    try {
        if(argc > 2 || (argc == 2 && std::string(argv[1]) != "--reverse-policies"))
            throw std::runtime_error("usage: csl_mpc04_max_coordinate_replanning [--reverse-policies]");
        std::cout << run(argc == 2).dump() << '\n';
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
