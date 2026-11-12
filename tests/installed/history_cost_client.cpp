#include <csl/optimization/history_cost.hpp>
#include <csl/sets/data.hpp>

#include <iostream>
#include <variant>

int main() {
    using namespace csl;
    auto feasible = sets::make_universal({{"installed-history"}, 3, {}});
    if(const auto* error = std::get_if<Diagnostic>(&feasible)) {
        std::cerr << error->explanation << '\n';
        return 1;
    }
    synthesis::JointHistoryRelation history{{Dimensions{1, 1, 0}, 1},
        std::get<sets::SetData>(std::move(feasible))};
    const TerminalObjective terminal = LinearTerminal{{1.0}, 0.0};
    const optimization::RunningControlCost running{"installed-source", 1, {{0,
        {optimization::QuadraticControlPenalty{{0.0}, {1.0}, {1.0}, 1.0, 1}}}}};
    auto compiled = optimization::compile_history_cost(history, terminal, running, 0);
    const auto* program = std::get_if<optimization::HistoryCostProgram>(&compiled);
    if(!program || program->quadratic.dimension != 3) return 1;
    auto evaluated = optimization::evaluate_history_cost(*program,
        std::vector<Vector>{{0.0}, {0.5}}, std::vector<Vector>{{0.5}});
    const auto* score = std::get_if<optimization::HistoryCostEvaluation>(&evaluated);
    if(!score || score->terminal != 0.5 || score->running != 0.25 || score->total != 0.75) return 1;
    std::cout << "Installed history-cost client: compiled canonical history objective passed\n";
}
