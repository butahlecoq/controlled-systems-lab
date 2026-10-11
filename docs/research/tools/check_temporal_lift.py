"""Exact authored examples for the temporal audit, not an optimizer or proof engine.

Only the Python standard library is used. All comparisons remain active under -O.
The report proves the continuous history statements; these finite literal checks
exercise offsets, initial memory, stage bounds and the stated counterexamples.
"""
from fractions import Fraction as Q


def mv(matrix, vector):
    return tuple(sum((a * b for a, b in zip(row, vector)), Q(0)) for row in matrix)


def add(*vectors):
    return tuple(sum(parts, Q(0)) for parts in zip(*vectors))


def observations():
    models = (
        (((1, 1), (0, 2)), (1, 3), (Q(1, 3), Q(-1, 7)),
         ((1, Q(-1, 2)), (0, Q(1, 2)))),
        (((2, 0), (1, 1)), (-2, 1), (Q(-1, 2), Q(2, 5)),
         ((Q(1, 2), 0), (Q(-1, 2), 1))),
    )
    x, z, y = (Q(2, 3), Q(-4, 5)), (Q(2, 3), Q(-4, 5), Q(-1, 4)), (Q(2, 3), Q(-4, 5), Q(-1, 4), Q(1))
    direct, lifted, inverse, homogeneous = [], [], [], []
    for (a, b, offset, a_inverse), u in zip(models, (Q(1, 5), Q(-1, 10))):
        v = u - z[-1]
        x = add(mv(a, x), tuple(q * u for q in b), offset)
        ahat = tuple(tuple(row) + (q,) for row, q in zip(a, b)) + ((0, 0, 1),)
        z = add(mv(ahat, z), tuple(q * v for q in b + (1,)), offset + (0,))
        previous_x = mv(a_inverse, add(z[:2], tuple(-q * z[-1] for q in b), tuple(-q for q in offset)))
        inverse.append(previous_x + (z[-1] - v,))
        atilde = tuple(tuple(row) + (q, c) for row, q, c in zip(a, b, offset)) + ((0, 0, 1, 0), (0, 0, 0, 1))
        y = add(mv(atilde, y), tuple(q * v for q in b + (1, 0)))
        direct.append(x)
        lifted.append(z)
        homogeneous.append(y)

    p0, u0_bounds, u1_bounds = Q(2), (Q(0), Q(1)), (Q(-1, 2), Q(0))
    first_domain = tuple(u - p0 for u in u0_bounds)
    u0, u1 = p0 + Q(-3, 2), p0 + Q(-3, 2) + Q(-3, 4)
    inside = lambda value, bounds: bounds[0] <= value <= bounds[1]
    rates = tuple(tuple(h * r for r in (Q(-1, 4), Q(1, 4))) for h in (Q(1, 2), Q(2)))
    true_terminal = (Q(1) + Q(1) - Q(1, 4), Q(1) + Q(1))
    naive_terminal = (Q(1) - Q(1), Q(1) + Q(1))
    controls = tuple((a, -a) for a in (Q(-1), Q(0), Q(1)))
    terminals = tuple((sum(plan), plan[-1]) for plan in controls)
    increments = tuple((plan[0], plan[1] - plan[0]) for plan in controls)
    singleton_retained = tuple(plan for plan, terminal in zip(controls, terminals) if terminal == (0, 0))
    witnesses = ((1, 0, -1), (-1, 0, 1), (1, -1, 0))
    trajectories = tuple(tuple(sum(plan[:t]) for t in (1, 2, 3)) for plan in witnesses)
    diagonal_residuals = tuple(path[0] - path[1] for path in trajectories)
    embedded_omitted = tuple((coordinate, 0, 0, 0) for coordinate in trajectories[-1])
    return {
        "temporal_affine_ltv_states": (tuple(direct), tuple(lifted)),
        "temporal_inverse_recovery": tuple(inverse),
        "temporal_first_step_and_stage_bounds": (first_domain, (u0, u1),
            (inside(u0, u0_bounds), inside(u1, u1_bounds)), inside(u1, u0_bounds), inside(p0, u0_bounds)),
        "temporal_rate_scaling": rates,
        "temporal_homogeneous_slice": tuple(homogeneous),
        "temporal_uncoupled_counterexample": (true_terminal, naive_terminal,
            true_terminal[0] ** 2, naive_terminal[0] ** 2, abs(Q(-1) - Q(1))),
        "temporal_terminal_memory_fibre": (terminals, increments, singleton_retained),
        "temporal_marginal_coverage": (trajectories, diagonal_residuals,
            tuple(path[-1] ** 2 for path in trajectories)),
        "temporal_four_state_embedding": (embedded_omitted,
            sum(q * q for q in embedded_omitted[-1]), (0, 0, 0, 0, terminals[-1][-1])),
    }


def check_temporal_lift():
    # Independent literal oracles from the report's rational derivations.
    expected = {
        "temporal_affine_ltv_states": (
            ((Q(2, 5), Q(-8, 7)), (Q(1, 2), Q(-31, 70))),
            ((Q(2, 5), Q(-8, 7), Q(1, 5)), (Q(1, 2), Q(-31, 70), Q(-1, 10)))),
        "temporal_inverse_recovery": ((Q(2, 3), Q(-4, 5), Q(-1, 4)), (Q(2, 5), Q(-8, 7), Q(1, 5))),
        "temporal_first_step_and_stage_bounds": ((-2, -1), (Q(1, 2), Q(-1, 4)), (True, True), False, False),
        "temporal_rate_scaling": ((Q(-1, 8), Q(1, 8)), (Q(-1, 2), Q(1, 2))),
        "temporal_homogeneous_slice": ((Q(2, 5), Q(-8, 7), Q(1, 5), 1), (Q(1, 2), Q(-31, 70), Q(-1, 10), 1)),
        "temporal_uncoupled_counterexample": ((Q(7, 4), 2), (0, 2), Q(49, 16), 0, 2),
        "temporal_terminal_memory_fibre": (((0, 1), (0, 0), (0, -1)), ((-1, 2), (0, 0), (1, -2)), ((0, 0),)),
        "temporal_marginal_coverage": (((1, 1, 0), (-1, -1, 0), (1, 0, 0)), (0, 0, 1), (0, 0, 0)),
        "temporal_four_state_embedding": (((1, 0, 0, 0), (0, 0, 0, 0), (0, 0, 0, 0)), 0, (0, 0, 0, 0, -1)),
    }
    actual = observations()
    if actual.keys() != expected.keys():
        raise ValueError("Temporal example coverage differs from the literal contract")
    for name, value in expected.items():
        if actual[name] != value:
            raise ValueError(f"{name}: expected {value!r}, computed {actual[name]!r}")
    return actual


if __name__ == "__main__":
    for name in check_temporal_lift():
        print(f"PASS {name}")
    print("9 exact literal checks passed; continuum claims require the report proofs.")
