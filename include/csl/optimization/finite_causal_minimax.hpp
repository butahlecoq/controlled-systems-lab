#pragma once

#include <csl/core/diagnostics.hpp>

#include <cstddef>
#include <optional>
#include <variant>
#include <vector>

namespace csl::optimization::finite_causal_minimax {

struct StateId {
    std::size_t value;
    bool operator==(const StateId&) const = default;
};

struct ActionId {
    std::size_t value;
    bool operator==(const ActionId&) const = default;
};

struct Stage {
    std::size_t state_count;
    std::size_t action_count;
    std::size_t disturbance_count;
    std::vector<bool> safe_states;
    // next_state[state][action][disturbance] identifies a state in the next
    // stage, or in the terminal layer for the final stage.
    std::vector<std::vector<std::vector<StateId>>> next_state;
};

struct Terminal {
    std::size_t state_count;
    std::vector<bool> safe_states;
    std::vector<double> cost;
};

// The state catalogues are stage-local. Builders must assign one StateId to
// all histories that produce the same exact observed state at the same stage.
// The cost is terminal-only; disturbances are finite and stage-rectangular.
struct Game {
    std::vector<Stage> stages;
    Terminal terminal;
    StateId initial_state;
};

struct Options {
    double absolute_value_tolerance;
    double relative_value_tolerance;
};

struct StateValue {
    bool feasible;
    double value; // meaningful only when feasible
    std::vector<ActionId> optimal_actions;
    bool operator==(const StateValue&) const = default;
};

struct Result {
    // Includes the terminal layer at index stages.size().
    std::vector<std::vector<StateValue>> values_by_stage;
    StateId initial_state;
    const StateValue& initial() const {
        return values_by_stage.front().at(initial_state.value);
    }
};

using Outcome = std::variant<Result, Diagnostic>;

std::optional<Diagnostic> validate(const Game& game, const Options& options);
Outcome solve(const Game& game, const Options& options);

} // namespace csl::optimization::finite_causal_minimax
