#include <Highs.h>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <cmath>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using nlohmann::json;

template<class T> T take(std::variant<T, Diagnostic> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("invalid MPC-03 fixture");
    return std::get<T>(std::move(result));
}

sets::SetData singleton(std::string id, double value) {
    return take(sets::make_singleton({{std::move(id)}, 1, {"x"}},
        take(numeric::snapshot_vector(Vector{value}))));
}

sets::SetData interval(std::string id, double lower, double upper) {
    return take(sets::make_v({{std::move(id)}, 1, {"x"}},
        {take(numeric::snapshot(Matrix{2, 1, {lower, upper}})),
         take(numeric::snapshot(Matrix{0, 1, {}}))}));
}

sets::SetData stage_safe(std::string id, double lower) {
    return take(sets::make_h({{std::move(id)}, 1, {"x"}},
        {take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
         take(numeric::snapshot_vector(Vector{10, -lower})),
         take(numeric::snapshot(Matrix{0, 1, {}})),
         take(numeric::snapshot_vector(Vector{}))}));
}

FiniteActionMinimaxRequest finite_case() {
    const SystemModel authored{{{1, 1, 1}, TimeDomain::discrete,
        LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 1, {1}}, {0}}}, {}};
    return {{"mpc03-scalar"}, {"mpc03-open-loop"},
        take(model::snapshot(authored, Vector{0, 1, 2})), singleton("x0", 0),
        {1, {{0}, {1}, {1}}}, {interval("w0", -0.125, 0.125), interval("w1", -0.125, 0.125)},
        {stage_safe("safe0", -10), stage_safe("safe1", -10), stage_safe("safe2", 1.5)},
        std::get<Objective>(snapshot(LinearTerminal{{1}, 0}))};
}

struct SolvedModel {
    double objective;
    double lower_bound;
    double gap;
    std::vector<double> solution;
};

void add_row(HighsLp& lp, const std::map<HighsInt, double>& coefficients, double lower, double upper) {
    for (const auto& [column, value] : coefficients) {
        lp.a_matrix_.index_.push_back(column);
        lp.a_matrix_.value_.push_back(value);
    }
    lp.a_matrix_.start_.push_back(static_cast<HighsInt>(lp.a_matrix_.index_.size()));
    lp.row_lower_.push_back(lower);
    lp.row_upper_.push_back(upper);
}

HighsLp formulation(bool integer_actions) {
    constexpr HighsInt stages = 2;
    constexpr HighsInt actions = 3;
    constexpr HighsInt x1_start = stages * actions;
    constexpr HighsInt x2_start = x1_start + 2;
    constexpr HighsInt epigraph = x2_start + 4;
    HighsLp lp;
    lp.num_col_ = epigraph + 1;
    lp.num_row_ = 0;
    lp.sense_ = ObjSense::kMinimize;
    lp.col_cost_.assign(static_cast<std::size_t>(lp.num_col_), 0.0);
    lp.col_cost_[epigraph] = 1.0;
    lp.col_lower_.assign(static_cast<std::size_t>(lp.num_col_), -kHighsInf);
    lp.col_upper_.assign(static_cast<std::size_t>(lp.num_col_), kHighsInf);
    for (HighsInt i = 0; i < stages * actions; ++i) {
        lp.col_lower_[i] = 0.0;
        lp.col_upper_[i] = 1.0;
    }
    for (HighsInt i = 0; i < 2; ++i) {
        lp.col_lower_[x1_start + i] = -10.0;
        lp.col_upper_[x1_start + i] = 10.0;
    }
    for (HighsInt i = 0; i < 4; ++i) {
        lp.col_lower_[x2_start + i] = 1.5;
        lp.col_upper_[x2_start + i] = 10.0;
    }
    lp.col_lower_[epigraph] = 0.0;
    lp.a_matrix_.format_ = MatrixFormat::kRowwise;
    lp.a_matrix_.start_ = {0};
    lp.integrality_.assign(static_cast<std::size_t>(lp.num_col_), HighsVarType::kContinuous);
    if (integer_actions)
        for (HighsInt i = 0; i < stages * actions; ++i)
            lp.integrality_[i] = HighsVarType::kInteger;

    for (HighsInt stage = 0; stage < stages; ++stage) {
        std::map<HighsInt, double> row;
        for (HighsInt action = 0; action < actions; ++action) row[stage * actions + action] = 1.0;
        add_row(lp, row, 1.0, 1.0);
    }
    const std::array<double, 2> disturbances{-0.125, 0.125};
    for (HighsInt i = 0; i < 2; ++i) {
        add_row(lp, {{1, -1.0}, {2, -1.0}, {x1_start + i, 1.0}},
            disturbances[static_cast<std::size_t>(i)], disturbances[static_cast<std::size_t>(i)]);
        add_row(lp, {{x1_start + i, 1.0}}, -10.0, 10.0);
    }
    for (HighsInt first = 0; first < 2; ++first) {
        for (HighsInt second = 0; second < 2; ++second) {
            const HighsInt scenario = 2 * first + second;
            const double disturbance = disturbances[static_cast<std::size_t>(first)] +
                disturbances[static_cast<std::size_t>(second)];
            add_row(lp, {{1, -1.0}, {2, -1.0}, {4, -1.0}, {5, -1.0},
                {x2_start + scenario, 1.0}}, disturbance, disturbance);
            add_row(lp, {{x2_start + scenario, 1.0}}, 1.5, 10.0);
            add_row(lp, {{x2_start + scenario, -1.0}, {epigraph, 1.0}}, 0.0, kHighsInf);
        }
    }
    lp.num_row_ = static_cast<HighsInt>(lp.row_lower_.size());
    lp.a_matrix_.num_row_ = lp.num_row_;
    lp.a_matrix_.num_col_ = lp.num_col_;
    return lp;
}

SolvedModel solve(bool integer_actions) {
    Highs solver;
    solver.setOptionValue("output_flag", false);
    solver.setOptionValue("threads", 1);
    solver.setOptionValue("mip_rel_gap", 0.0);
    solver.setOptionValue("time_limit", 300.0);
    auto lp = formulation(integer_actions);
    if (solver.passModel(lp) == HighsStatus::kError || solver.run() == HighsStatus::kError ||
        solver.getModelStatus() != HighsModelStatus::kOptimal)
        throw std::runtime_error("HiGHS did not complete the MPC-03 model to optimality");
    const auto& info = solver.getInfo();
    const auto& solution = solver.getSolution();
    if (solution.col_value.size() != static_cast<std::size_t>(lp.num_col_) ||
        !std::isfinite(info.objective_function_value))
        throw std::runtime_error("HiGHS returned no finite MPC-03 incumbent");
    const double lower_bound = integer_actions ? info.mip_dual_bound : info.objective_function_value;
    const double gap = integer_actions ? info.mip_gap : 0.0;
    if (!std::isfinite(lower_bound) || !std::isfinite(gap))
        throw std::runtime_error("HiGHS returned no finite MPC-03 bound or gap");
    return {info.objective_function_value, lower_bound, gap, solution.col_value};
}

json run() {
    const auto exact = finite_action_minimax(finite_case(), {9, 16, 0.0});
    if (!std::holds_alternative<FiniteMinimaxOptimal>(exact)) {
        std::string message = "finite-action reference outcome variant " + std::to_string(exact.index());
        if (const auto* unsupported = std::get_if<Unsupported>(&exact))
            for (const auto& diagnostic : unsupported->diagnostics)
                message += "; " + diagnostic.field + ": " + diagnostic.explanation;
        throw std::runtime_error(message);
    }
    const auto& reference = std::get<FiniteMinimaxOptimal>(exact);
    const auto integer = solve(true);
    const auto relaxed = solve(false);
    if (reference.value != 2.25 || reference.minimizing_plan_indices != std::vector<std::size_t>{4, 5, 7, 8} ||
        integer.objective != reference.value || integer.lower_bound != reference.value ||
        relaxed.objective != 2.0 || relaxed.objective > reference.value)
        throw std::runtime_error("MPC-03 finite/MIP/relaxation agreement or bound direction failed");
    const json finite_report{{"value", reference.value},
        {"minimizing_plan_indices", reference.minimizing_plan_indices},
        {"plan_count", reference.plans.size()}, {"assurance", "numerical_exhaustive"}};
    const json integer_report{{"status", "optimal"}, {"objective", integer.objective},
        {"best_bound", integer.lower_bound}, {"gap", integer.gap},
        {"shared_action_indices", json::array({integer.solution[0], integer.solution[1], integer.solution[2],
            integer.solution[3], integer.solution[4], integer.solution[5]})}};
    const json relaxed_report{{"status", "optimal"}, {"lower_bound", relaxed.objective},
        {"objective", relaxed.objective}, {"controls", json::array({relaxed.solution[1] + relaxed.solution[2],
            relaxed.solution[4] + relaxed.solution[5]})}};
    return {{"schema", "csl.mpc03-open-loop-pilot/1"}, {"case_id", "scalar-slew-free-two-stage"},
        {"controls", json::array({0.0, 1.0, 1.0})}, {"disturbances_each_stage", json::array({-0.125, 0.125})},
        {"safe_stages", json::array({"-10 <= x0 <= 10", "-10 <= x1 <= 10", "1.5 <= x2 <= 10"})},
        {"terminal_cost", "minimize worst-case x2"}, {"history_count", 4},
        {"finite_reference", finite_report}, {"extensive_form_milp", integer_report},
        {"convex_action_relaxation", relaxed_report},
        {"finite_upper_bound", reference.value}, {"relaxation_lower_bound", relaxed.objective},
        {"solver", "HiGHS 1.11.0, one thread"}};
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2 || std::string(argv[1]) != "--smoke")
            throw std::runtime_error("usage: csl_mpc03_robust_minimax_report --smoke");
        std::cout << run().dump(2) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
