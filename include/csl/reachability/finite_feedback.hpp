#pragma once

#include <csl/core/diagnostics.hpp>
#include <cstddef>
#include <optional>
#include <variant>
#include <vector>

namespace csl::reachability::finite_feedback {

struct StateIndex { std::size_t value; bool operator==(const StateIndex&) const = default; };
struct ActionIndex { std::size_t value; bool operator==(const ActionIndex&) const = default; };

// One exact state is available before the action. The disturbance index is
// chosen afterward; its nonempty domain is identical for all state/action
// pairs at this stage. next_state[state][action][disturbance] is complete.
struct Stage {
    std::vector<bool> safe_states;
    std::size_t action_count;
    std::size_t disturbance_count;
    std::vector<std::vector<std::vector<StateIndex>>> next_state;
};

struct Game {
    std::size_t state_count;
    std::vector<Stage> stages;
    std::vector<bool> terminal_safe;
    std::vector<bool> terminal_target;
};

struct Policy {
    // winning[t][state] includes current safety and terminal target.
    std::vector<std::vector<bool>> winning;
    // All robustly feasible actions, in authored order. The first is a
    // deterministic causal selector; this makes no cost-optimality claim.
    std::vector<std::vector<std::vector<ActionIndex>>> admissible_actions;
    bool operator==(const Policy&) const = default;
};

using Result = std::variant<Policy,Diagnostic>;
std::optional<Diagnostic> validate(const Game& game);
Result solve(const Game& game);

} // namespace csl::reachability::finite_feedback
