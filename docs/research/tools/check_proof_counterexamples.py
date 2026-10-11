"""Exact literal checks for the authored proof audits; no archive or solver needed.

Continuous-domain maxima are proved analytically in the reports. These checks
exercise their literal witnesses and costs, not a sampled certification.
"""
from fractions import Fraction


def observations():
    """Compute the literal witnesses exposed by the public reports."""
    candidates = (Fraction(0), Fraction(2))
    retained = candidates[:1]
    full = (min(candidates), max(candidates))
    reduced = (min(retained), max(retained))
    constraint = (Fraction(0), Fraction(0))

    def clip(interval):
        return (max(interval[0], constraint[0]), min(interval[1], constraint[1]))

    triangle = ((-2, -2), (2, 2), (2, -2))
    outside = (-1, 1)
    direction = (-1, 1)

    def support(points):
        return max(sum(a * b for a, b in zip(point, direction)) for point in points)

    def linear(u):
        return (u, Fraction(0))

    def nonlinear(u):
        return (u, u * u)

    def squared_cost(u0, u1, w0):
        # A=((1,0),(1,1)), B=(1,0), E=(1,-1), w1=0.
        x1 = (u0 + w0, -w0)
        x2 = (x1[0] + u1, x1[0] + x1[1])
        return sum(coordinate * coordinate for coordinate in x2)

    vertices = (Fraction(-1), Fraction(1))
    probes = (Fraction(-1), Fraction(0), Fraction(1))
    plans = ((0, -1), (0, 1), (1, -1), (1, 1))
    fixed = tuple(max(squared_cost(*plan, w) for w in vertices) for plan in plans)
    replan = tuple(min(squared_cost(1, u, w) for u in (-1, 1)) for w in probes)
    causal = tuple(squared_cost(0, -1 if w >= 0 else 1, w) for w in probes)
    endpoints = (nonlinear(Fraction(-1)), nonlinear(Fraction(1)))
    midpoint = tuple((a + b) / 2 for a, b in zip(*endpoints))
    return {
        "unclipped_hulls": (full, reduced),
        "clipped_sets": (clip(full), clip(reduced)),
        "facet_support_gap": (support(triangle), support((outside,))),
        "nonlinear_endpoints": (linear(Fraction(1)), nonlinear(Fraction(1)), midpoint),
        "fixed_plan_squared_costs": fixed,
        "replanning_squared_costs": replan,
        "replanning_tie_squared_costs": tuple(squared_cost(1, u, Fraction(-1)) for u in (-1, 1)),
        "causal_squared_costs": causal,
        "feedback_vertex_and_interior_maxima": (max(causal[0], causal[2]), causal[1]),
    }


def check_counterexamples():
    expected = {
        "unclipped_hulls": ((0, 2), (0, 0)),
        "clipped_sets": ((0, 0), (0, 0)),
        "facet_support_gap": (0, 2),
        "nonlinear_endpoints": ((1, 0), (1, 1), (0, 1)),
        "fixed_plan_squared_costs": (4, 4, 2, 10),
        "replanning_squared_costs": (2, 1, 2),
        "replanning_tie_squared_costs": (2, 2),
        "causal_squared_costs": (0, 1, 0),
        "feedback_vertex_and_interior_maxima": (0, 1),
    }
    actual = observations()
    if set(actual) != set(expected):
        raise ValueError("Counterexample coverage differs from the literal contract")
    for name, value in expected.items():
        if actual[name] != value:
            raise ValueError(f"{name}: expected {value!r}, computed {actual[name]!r}")
    return actual


if __name__ == "__main__":
    for name in check_counterexamples():
        print(f"PASS {name}")
    print("9 exact literal checks passed; continuum claims require the report proofs.")
