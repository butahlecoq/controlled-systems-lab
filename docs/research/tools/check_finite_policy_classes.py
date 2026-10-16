"""Exact finite counterexample reference for issue #5, not a product solver.

Every disturbance catalogue is explicitly finite. The L13 example's continuous
disturbance interval and its policy-wide bounds are proved in the audit, not here.
Costs are exact squared norms, which preserve the ordering of Euclidean norms.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import product


@dataclass(frozen=True)
class Game:
    initial_state: tuple
    actions: tuple
    disturbances: tuple
    transition: object
    safe: object
    terminal_cost: object


@dataclass
class Comparison:
    fixed_plan_values: dict
    fixed_value: Fraction
    replanning_first_actions: dict
    replanning_history_costs: dict
    replanning_worst: Fraction
    causal_first_actions: dict
    causal_history_costs: dict
    causal_value: Fraction


def _validate(game):
    if not game.actions or len(game.actions) != len(game.disturbances):
        raise ValueError("A finite horizon needs matching action/disturbance stages")
    if any(not disturbances for disturbances in game.disturbances):
        raise ValueError("A disturbance catalogue cannot be empty")


def _plan_cost(game, stage, state, plan):
    """Return None if any disturbance history violates safety."""
    if not game.safe(stage, state):
        return None
    worst = None
    for disturbances in product(*game.disturbances[stage:]):
        reached = state
        for t, action, disturbance in zip(range(stage, len(game.actions)), plan, disturbances):
            reached = game.transition(t, reached, action, disturbance)
            if not game.safe(t + 1, reached):
                return None
        cost = Fraction(game.terminal_cost(reached))
        worst = cost if worst is None else max(worst, cost)
    return worst


def remaining_fixed(game, stage, state):
    """Minimize a fixed remaining plan before all future disturbances."""
    _validate(game)
    if not 0 <= stage < len(game.actions):
        raise ValueError("Stage must precede the terminal stage")
    values = ((plan, _plan_cost(game, stage, state, plan))
              for plan in product(*game.actions[stage:]))
    feasible = [(plan, value) for plan, value in values if value is not None]
    if not feasible:
        return None, ()
    best = min(value for _, value in feasible)
    return best, tuple(plan for plan, value in feasible if value == best)


def compare(game):
    """Compare exact finite fixed plans, first-action replanning and causal play.

    The deterministic execution selector takes the first optimal action in the
    authored catalogue; all tied first actions remain visible in the result.
    """
    _validate(game)
    horizon = len(game.actions)
    fixed_plan_values = {plan: _plan_cost(game, 0, game.initial_state, plan)
                         for plan in product(*game.actions)}
    fixed_value, root_plans = remaining_fixed(game, 0, game.initial_state)
    if not root_plans:
        raise ValueError("No robustly feasible initial fixed plan")

    replanning_first_actions = {}
    replanning_history_costs = {}

    def walk_replanning(stage, state, history):
        if stage == horizon:
            replanning_history_costs[history] = Fraction(game.terminal_cost(state))
            return
        value, plans = remaining_fixed(game, stage, state)
        if value is None:
            raise ValueError("Replanning lost robust feasibility")
        first_actions = tuple(dict.fromkeys(plan[0] for plan in plans))
        replanning_first_actions[(stage, state)] = first_actions
        action = first_actions[0]
        for disturbance in game.disturbances[stage]:
            successor = game.transition(stage, state, action, disturbance)
            walk_replanning(stage + 1, successor, history + (disturbance,))

    walk_replanning(0, game.initial_state, ())

    causal_first_actions = {}
    causal_values = {}

    def causal_value(stage, state):
        if not game.safe(stage, state):
            return None
        if stage == horizon:
            return Fraction(game.terminal_cost(state))
        key = (stage, state)
        if key in causal_values:
            return causal_values[key]
        action_values = []
        for action in game.actions[stage]:
            successor_values = [causal_value(stage + 1,
                                              game.transition(stage, state, action, disturbance))
                                for disturbance in game.disturbances[stage]]
            if all(value is not None for value in successor_values):
                action_values.append((action, max(successor_values)))
        if not action_values:
            causal_values[key] = None
            return None
        best = min(value for _, value in action_values)
        causal_first_actions[key] = tuple(action for action, value in action_values if value == best)
        causal_values[key] = best
        return best

    root_causal_value = causal_value(0, game.initial_state)
    if root_causal_value is None:
        raise ValueError("No robustly feasible initial causal action")

    causal_history_costs = {}

    def walk_causal(stage, state, history):
        if stage == horizon:
            causal_history_costs[history] = Fraction(game.terminal_cost(state))
            return
        action = causal_first_actions[(stage, state)][0]
        for disturbance in game.disturbances[stage]:
            successor = game.transition(stage, state, action, disturbance)
            walk_causal(stage + 1, successor, history + (disturbance,))

    walk_causal(0, game.initial_state, ())
    return Comparison(fixed_plan_values, fixed_value, replanning_first_actions,
                      replanning_history_costs, max(replanning_history_costs.values()),
                      causal_first_actions, causal_history_costs, root_causal_value)


def l13_policy_gap_game():
    """Authored T=2 counterexample from the reviewed issue #5 proof audit."""
    def transition(stage, state, action, disturbance):
        x, y = state
        return (x + action + disturbance, x + y - disturbance)

    return Game((0, 0), ((0, 1), (-1, 1)), ((-1, 0, 1), (0,)),
                transition,
                lambda stage, state: all(-4 <= coordinate <= 4 for coordinate in state),
                lambda state: sum(coordinate * coordinate for coordinate in state))


def main():
    result = compare(l13_policy_gap_game())
    print("fixed_plan_squared=" + repr(result.fixed_plan_values))
    print("initial_fixed_squared=" + str(result.fixed_value))
    print("executed_replanning_squared=" + str(result.replanning_worst))
    print("global_causal_squared=" + str(result.causal_value))
    print("replanning_history_squared=" + repr(result.replanning_history_costs))
    print("causal_history_squared=" + repr(result.causal_history_costs))


if __name__ == "__main__":
    main()
