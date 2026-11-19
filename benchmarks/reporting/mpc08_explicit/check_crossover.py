"""Replay both closed-loop deployments against exact cell laws before reporting timings."""

import argparse
import json
from fractions import Fraction
from math import ceil, hypot, isfinite
from pathlib import Path
from statistics import median

from crossover_reference import checked_reference, polygon_rows
from crossover_workload import make_workload


def require(value, message):
    if not value:
        raise ValueError(message)


def near(a, b, tolerance):
    return isfinite(a) and abs(a - b) <= tolerance


def distribution(values):
    return {"min": min(values), "median": median(values), "max": max(values)}


def policy(reference):
    result = {}
    for stage in reference["horizons"]:
        cells = []
        for cell in stage["cells"]:
            rows = [(float(a), float(b), float(c)) for a, b, c in polygon_rows(cell["vertices"])]
            controls = [tuple(map(float, u)) for u in cell["controls"]]
            cells.append((rows, controls))
        result[stage["remaining"]] = cells
    return result


def expected(cells, x):
    for rows, controls in cells:
        if all(a * x[0] + b * x[1] <= c + 1e-9 * hypot(a, b) for a, b, c in rows):
            return [a * x[0] + b * x[1] + c for a, b, c in controls]
    return None


def check_episode(ep, start, cells, spec):
    x = start
    cost = 0
    history = expected(cells[3], x)
    require(not ep["error"], ep["error"])
    if history is None:
        require(
            ep["status"] == "infeasible" and ep["cost"] is None and len(ep["steps"]) == 1,
            "infeasible state",
        )
        s = ep["steps"][0]
        require(s["action"] is None and s["observed"] == x, "rejection observation")
        return
    require(ep["status"] == "completed" and len(ep["steps"]) == 3, "feasible episode")
    for n, step in zip((3, 2, 1), ep["steps"], strict=True):
        require(
            all(near(a, b, 1e-12) for a, b in zip(step["observed"], x, strict=True)),
            "observed state",
        )
        u = step["action"]
        law = expected(cells[n], x)
        require(
            law is not None and near(u, law[0], spec["action_tolerance"]), "observed-state action"
        )
        require(abs(u) <= 1 + spec["feasibility_tolerance"], "acceleration bound")
        x = [x[0] + x[1], x[1] + u]
        require(
            abs(x[0]) <= 3 + spec["feasibility_tolerance"]
            and abs(x[1]) <= 2 + spec["feasibility_tolerance"],
            "state box",
        )
        cost += 0.25 * u * u
    require(
        max(abs(x[0] + x[1]), abs(x[0] + 2 * x[1])) <= 1 + spec["feasibility_tolerance"],
        "terminal set",
    )
    cost += x[0] ** 2 + x[1] ** 2
    require(near(ep["cost"], cost, 1e-12), "replayed cost")
    p, v = start
    oracle_cost = 0
    for u in history:
        p, v = p + v, v + u
        oracle_cost += 0.25 * u * u
    require(near(ep["cost"], oracle_cost + p * p + v * v, spec["cost_tolerance"]), "optimal cost")


def same_vertices(cell, pts):
    vertices = cell["vertices"]
    return all(
        any(hypot(x - float(p), y - float(v)) < 1e-8 for p, v in vertices) for x, y in pts
    ) and all(any(hypot(float(p) - x, float(v) - y) < 1e-8 for x, y in pts) for p, v in vertices)


def check(workload_path, results_path):
    reference = checked_reference()
    spec = json.loads(workload_path.read_text())
    require(spec == make_workload(reference), "workload differs from exact construction")
    cells = policy(reference)
    records = [json.loads(s) for s in results_path.read_text().splitlines()]
    validation = records[0]
    require(validation["type"] == "validation", "missing validation")
    for q, row in zip(spec["queries"], validation["data"]["queries"], strict=True):
        require(q["id"] == row["id"] and "error" not in row, f"failed query {q['id']}: {row}")
        if q["expected"] is None:
            require(row["explicit"] is None and row["online"] is None, "feasibility classification")
        else:
            truth = [float(Fraction(v)) for v in q["expected"]]
            require(
                near(row["explicit"], truth[0], spec["action_tolerance"]), "explicit first action"
            )
            require(
                all(
                    near(a, b, spec["action_tolerance"])
                    for a, b in zip(row["online"], truth, strict=True)
                ),
                "QP history",
            )
    # Every emitted native polygon must have the same support as one exact cell.
    # Equality on its vertices then checks the affine first action on the entire cell.
    for exact, native in zip(reference["horizons"], validation["data"]["regions"], strict=True):
        remaining = list(exact["cells"])
        require(native["remaining"] == exact["remaining"], "horizon")
        for poly in native["cells"]:
            pts = poly["vertices"]

            compatible = [c for c in remaining if same_vertices(c, pts)]
            require(len(compatible) == 1, "unmatched native region")
            cell = compatible[0]
            remaining.remove(cell)
            a, b, c = poly["first_action"]
            A, B, C = map(float, cell["controls"][0])
            require(
                all(near(a * x + b * y + c, A * x + B * y + C, 1e-8) for x, y in pts),
                "native affine map",
            )
        require(not remaining, "missing native region")
    keys = set()
    grouped = {}
    for rec in records[1:]:
        count, rep, pos, method = (
            rec[k] for k in ("count", "repetition", "position", "controller")
        )
        k = count, rep, pos
        require(
            rec["type"] == "deployment"
            and k not in keys
            and count in spec["counts"]
            and -1 <= rep < 5
            and pos in (0, 1),
            "unexpected deployment",
        )
        keys.add(k)
        require(
            (method == "explicit") == ((rep % 2 == 0) == (pos == 0))
            and method in ("explicit", "online"),
            "alternation",
        )
        data = rec["data"]
        require(
            data["total_ns"] == data["setup_ns"] + data["service_ns"]
            and min(data["setup_ns"], data["service_ns"]) > 0,
            "timing",
        )
        require(len(data["episodes"]) == count, "work count")
        if method == "online":
            require(data["observed_scheduler_width"] == [1, 1, 1], "thread widths")
        for i, episode in enumerate(data["episodes"]):
            check_episode(
                episode, spec["deployment_states"][i % len(spec["deployment_states"])], cells, spec
            )
        grouped[count, rep, method] = data
    require(len(keys) == len(spec["counts"]) * 12, "missing paired repetition")
    summaries = []
    for count in spec["counts"]:
        item = {"count": count}
        for method in ("explicit", "online"):
            batches = [grouped[count, rep, method] for rep in range(5)]
            latencies = sorted(
                step["latency_ns"] for b in batches for ep in b["episodes"] for step in ep["steps"]
            )
            item[method] = {
                k: distribution([b[k] for b in batches])
                for k in ("setup_ns", "total_ns", "service_ns")
            }
            item[method]["p99_decision_ns"] = latencies[ceil(0.99 * len(latencies)) - 1]
        item["explicit_faster_pairs"] = sum(
            grouped[count, i, "explicit"]["total_ns"] < grouped[count, i, "online"]["total_ns"]
            for i in range(5)
        )
        summaries.append(item)
    return {
        "queries": len(spec["queries"]),
        "retained_pairs": len(spec["counts"]) * 5,
        "sizes": summaries,
        "first_observed_crossover": next(
            (s["count"] for s in summaries if s["explicit_faster_pairs"] == 5), None
        ),
        "policy_owned_bytes": grouped[spec["counts"][0], 0, "explicit"]["policy_owned_bytes"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workload", type=Path)
    parser.add_argument("raw", type=Path)
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    args.summary.write_text(
        json.dumps(check(args.workload, args.raw), indent=2) + "\n", encoding="utf-8"
    )
