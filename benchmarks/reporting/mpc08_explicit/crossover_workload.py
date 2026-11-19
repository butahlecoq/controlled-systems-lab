"""Deterministic states and exact expected histories for the MPC deployment study."""

import argparse
import json
import random
from fractions import Fraction as Q
from itertools import combinations
from pathlib import Path

from crossover_reference import checked_reference, polygon_rows
from explicit_double_integrator import holds, intersect


def mean_point(points):
    return tuple(sum(row[i] for row in points) / len(points) for i in range(2))


def make_workload(reference):
    queries = []
    deployment = []
    for record in reference["horizons"]:
        n = record["remaining"]
        cells = [(list(c["vertices"]), c["controls"]) for c in record["cells"]]
        samples = [(f"cell-{i}", mean_point(p)) for i, (p, _) in enumerate(cells)]
        for i, ((p, _), (q, _)) in enumerate(combinations(cells, 2)):
            shared = sorted(set(intersect(p, polygon_rows(q))))
            if len(shared) < 2:
                continue
            mid = mean_point([shared[0], shared[-1]])
            samples.append((f"edge-{i}", mid))
            for side, poly in enumerate([p, q]):
                toward = mean_point(poly)
                near = tuple(m + (c - m) / 1024 for m, c in zip(mid, toward, strict=True))
                samples.append((f"edge-{i}-side-{side}", near))
        samples += [("outside-state-box", (Q(4), Q(0))), ("inside-box-infeasible", (Q(3), Q(2)))]
        for label, x in samples:
            laws = [u for poly, u in cells if all(holds(h, x) for h in polygon_rows(poly))]
            expected = [a * x[0] + b * x[1] + c for a, b, c in laws[0]] if laws else None
            if label in ("outside-state-box", "inside-box-infeasible") and expected is not None:
                raise ValueError("infeasible sample has an exact feasible history")
            queries.append(
                {
                    "id": f"N{n}-{label}",
                    "remaining": n,
                    "state": list(map(float, x)),
                    "exact_state": list(map(str, x)),
                    "expected": list(map(str, expected)) if expected is not None else None,
                }
            )
            if n == 3:
                deployment.append(list(map(float, x)))
    # Begin every size with the same nonzero feasible state. Larger batches
    # cycle through the boundary, interior and infeasible queries.
    order = list(range(len(deployment)))
    random.Random(1084).shuffle(order)
    return {
        "schema": "csl.mpc-crossover-workload/1",
        "queries": queries,
        "deployment_states": [[-2.0, 0.5], *[deployment[i] for i in order]],
        "counts": [1, 4, 16, 64, 256],
        "action_tolerance": 2e-6,
        "feasibility_tolerance": 2e-6,
        "cost_tolerance": 2e-6,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    spec = make_workload(checked_reference())
    args.output.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
