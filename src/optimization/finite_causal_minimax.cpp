#include <csl/optimization/finite_causal_minimax.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <utility>

namespace csl::optimization::finite_causal_minimax {
namespace {

Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

bool tied(double left, double right, const Options& options) {
    const double scale = std::max(std::abs(left), std::abs(right));
    return std::abs(left - right) <= options.absolute_value_tolerance +
        options.relative_value_tolerance * scale;
}

} // namespace

std::optional<Diagnostic> validate(const Game& game, const Options& options) {
    if(!std::isfinite(options.absolute_value_tolerance) ||
       options.absolute_value_tolerance < 0.0 ||
       !std::isfinite(options.relative_value_tolerance) ||
       options.relative_value_tolerance < 0.0)
        return invalid("finite_causal.tolerance", "Value tolerances must be finite and nonnegative.");
    if(game.stages.empty())
        return invalid("finite_causal.stages", "At least one decision stage is required.");
    if(game.terminal.state_count == 0 ||
       game.terminal.safe_states.size() != game.terminal.state_count ||
       game.terminal.cost.size() != game.terminal.state_count)
        return invalid("finite_causal.terminal", "Terminal safety and cost rows must cover a nonempty state layer.");
    for(const double cost : game.terminal.cost)
        if(!std::isfinite(cost))
            return invalid("finite_causal.terminal.cost", "Terminal costs must be finite.");

    for(std::size_t t = 0; t < game.stages.size(); ++t) {
        const auto& stage = game.stages[t];
        const std::size_t next_state_count = t + 1 < game.stages.size()
            ? game.stages[t + 1].state_count : game.terminal.state_count;
        if(stage.state_count == 0 || stage.safe_states.size() != stage.state_count ||
           stage.next_state.size() != stage.state_count)
            return invalid("finite_causal.stage.states", "Every stage must have a nonempty state layer and matching safety/transition rows.");
        if(stage.action_count == 0)
            return invalid("finite_causal.stage.actions", "Every decision stage must have at least one action.");
        if(stage.disturbance_count == 0)
            return invalid("finite_causal.stage.disturbances", "Every stage disturbance catalogue must be nonempty.");
        for(const auto& actions : stage.next_state) {
            if(actions.size() != stage.action_count)
                return invalid("finite_causal.stage.actions", "Every state needs a transition row for each ordered action.");
            for(const auto& successors : actions) {
                if(successors.size() != stage.disturbance_count)
                    return invalid("finite_causal.stage.disturbances", "Every action needs one successor for each disturbance.");
                for(const StateId successor : successors)
                    if(successor.value >= next_state_count)
                        return invalid("finite_causal.stage.successor", "A successor state ID is out of range for the next stage.");
            }
        }
    }
    if(game.initial_state.value >= game.stages.front().state_count)
        return invalid("finite_causal.initial_state", "The initial state ID is out of range.");
    return {};
}

Outcome solve(const Game& game, const Options& options) {
    if(const auto error = validate(game, options)) return *error;

    Result result;
    result.initial_state = game.initial_state;
    result.values_by_stage.resize(game.stages.size() + 1);
    auto& terminal_values = result.values_by_stage.back();
    terminal_values.resize(game.terminal.state_count);
    for(std::size_t state = 0; state < game.terminal.state_count; ++state) {
        const bool feasible = game.terminal.safe_states[state];
        terminal_values[state] = {feasible, feasible ? game.terminal.cost[state] : 0.0, {}};
    }

    for(std::size_t t = game.stages.size(); t > 0; --t) {
        const auto stage_index = t - 1;
        const auto& stage = game.stages[stage_index];
        const auto& next_values = result.values_by_stage[stage_index + 1];
        auto& current_values = result.values_by_stage[stage_index];
        current_values.resize(stage.state_count);
        for(std::size_t state = 0; state < stage.state_count; ++state) {
            if(!stage.safe_states[state]) {
                current_values[state] = {false, 0.0, {}};
                continue;
            }

            bool has_feasible_action = false;
            double best_value = std::numeric_limits<double>::infinity();
            std::vector<std::pair<ActionId, double>> feasible_action_values;
            std::vector<ActionId> best_actions;
            for(std::size_t action = 0; action < stage.action_count; ++action) {
                bool all_disturbances_feasible = true;
                double worst_value = -std::numeric_limits<double>::infinity();
                for(const StateId successor : stage.next_state[state][action]) {
                    const auto& successor_value = next_values[successor.value];
                    if(!successor_value.feasible) {
                        all_disturbances_feasible = false;
                        break;
                    }
                    worst_value = std::max(worst_value, successor_value.value);
                }
                if(!all_disturbances_feasible) continue;
                has_feasible_action = true;
                best_value = std::min(best_value, worst_value);
                feasible_action_values.emplace_back(ActionId{action}, worst_value);
            }
            for(const auto& [action, value] : feasible_action_values)
                if(tied(value, best_value, options)) best_actions.push_back(action);
            current_values[state] = {has_feasible_action, has_feasible_action ? best_value : 0.0,
                                     std::move(best_actions)};
        }
    }

    return result;
}

} // namespace csl::optimization::finite_causal_minimax
