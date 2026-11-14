"""Check saved row transformations and original-coordinate trajectories, without a solver."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check(root: Path) -> dict:
    def rows(path):
        with (root / path).open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    native = {(r["model"], r["kind"], int(r["row"]), int(r["column"])): float(r["value"])
              for r in rows("inputs/models.csv")}
    results = []
    for number in (23, 27, 28):
        model = f"catalogue-2026/model-{number}/1"
        attempt = f"records/attempts/model-{number}-row-scale"
        output = attempt + "-output"
        receipt = json.loads((root / attempt / "attempt.json").read_text())
        require(receipt["returncode"] == (0 if number == 23 else 1), "saved outcome changed")
        require(not receipt["process_group_remains_after_wait"], "captured process group survived")
        transforms = []
        for folder in sorted((root / output).glob("replan-*")):
            relative = folder.relative_to(root).as_posix()
            bounds = rows(relative + "/rows.csv")
            coefficients = rows(relative + "/csr.csv")
            for c in coefficients:
                exponent = int(bounds[int(c["row"])]["power2_exponent"])
                old, new = float(c["original"]), float(c["scaled"])
                require(Fraction(new) == Fraction(old) * 2**exponent, "coefficient is not exact positive row scaling")
                require(struct.pack("d", math.ldexp(new, -exponent)) == struct.pack("d", old), "coefficient roundtrip changed bits")
            for row in bounds:
                exponent = int(row["power2_exponent"])
                for side in ("lower", "upper"):
                    old, new = row["original_" + side], row["scaled_" + side]
                    require(new == old if old == "unbounded" else Fraction(float(new)) == Fraction(float(old)) * 2**exponent,
                            "row bound is not the same exact transform")
            original_objective = root / f"records/attempts/model-{number}-original-export-output/replan-0/objective.csv"
            require((folder / "objective.csv").read_bytes() == original_objective.read_bytes(), "original objective changed")
            transforms.append({"replan": folder.name, "coefficient_rows_checked": len(coefficients),
                               "power2_exponents": sorted({int(row["power2_exponent"]) for row in bounds})})
        result = {"model": model, "returncode": receipt["returncode"], "transforms": transforms,
                  "completed_plan": number == 23}
        if number == 23:
            values = {}
            for row in rows(output + "/trace.csv"):
                key = row["kind"], int(row["replan"]), int(row["stage"]), int(row["coordinate"])
                value = float(row["value"])
                require(key not in values or values[key] == value, "duplicate trace value differs")
                values[key] = value
            nx, nu, nw = 8, 2, 8
            initial = [native[model, "x0", i, 0] for i in range(nx)]
            weights = [1 / max(1, abs(v))**2 for v in initial]
            a = [[native[model, "A", i, j] for j in range(nx)] for i in range(nx)]
            b = [[native[model, "B", i, j] for j in range(nu)] for i in range(nx)]
            e = [[native[model, "G", i, j] for j in range(nw)] for i in range(nx)]
            w = [native.get((model, "nominal_w", j, 0), 0) for j in range(nw)]
            affine = [native[model, "a", i, 0] + math.fsum(e[i][j] * w[j] for j in range(nw)) for i in range(nx)]
            observed = initial
            maximum_dynamics = maximum_cost = 0.0
            for replan in range(3):
                x = [[values["predicted_state", replan, k, i] for i in range(nx)] for k in range(4)]
                u = [[values["predicted_control", replan, k, j] for j in range(nu)] for k in range(3)]
                require(x[0] == observed, "prediction does not bind the original observed state")
                require(all(-1 - 1e-8 <= value <= 1 + 1e-8 for control in u for value in control), "original actuator bounds violated")
                for k in range(3):
                    for i in range(nx):
                        expected = math.fsum([affine[i], *(a[i][j] * x[k][j] for j in range(nx)), *(b[i][j] * u[k][j] for j in range(nu))])
                        delta = abs(expected - x[k + 1][i])
                        require(delta <= 1e-8 * (1 + abs(expected)), "original full-state dynamics violated")
                        maximum_dynamics = max(maximum_dynamics, delta)
                cost = math.fsum([*(weights[i] * x[k][i]**2 for k in range(3) for i in range(nx)),
                                 *(.02 * value**2 for control in u for value in control),
                                 *(5 * weights[i] * x[3][i]**2 for i in range(nx))])
                for kind in ("independent_plan_cost", "compiled_plan_cost"):
                    delta = abs(values[kind, replan, 0, 0] - cost)
                    require(delta <= 1e-8 * (1 + abs(cost)), "original task objective differs")
                    maximum_cost = max(maximum_cost, delta)
                require([values["applied_control", replan, 0, j] for j in range(nu)] == u[0], "executed control differs from first predicted action")
                require([values["observed_state", replan, 0, i] for i in range(nx)] == observed, "executed observed state differs")
                observed = [values["observed_next_state", replan, 1, i] for i in range(nx)]
                require(all(abs(observed[i] - x[1][i]) <= 1e-8 * (1 + abs(x[1][i])) for i in range(nx)), "executed plant step differs")
            result["original_coordinate_check"] = {"full_state_transitions": 9, "state_dimension": 8,
                "maximum_dynamics_residual": maximum_dynamics, "maximum_objective_difference": maximum_cost,
                "initial_state_zero": all(v == 0 for v in initial), "state_constraints": "none in authored task",
                "control_constraints": "[-1,1] in recorded coordinates"}
        else:
            log = (root / output / "native-replan-0.txt").read_text()
            if number == 27:
                require("start.valid=false" in log and "qp_run=false" in log and "phase.feasibility.model_status=7" in log,
                        "model27 start rejection evidence missing")
            else:
                require("excessive primal values" in log and "phase.feasibility.api_status=-1" in log,
                        "model28 native numerical error evidence missing")
        results.append(result)
    toy = json.loads((root / "records/analytic-result.json").read_text())
    stdout = (root / "records/attempts/analytic-normalized/stdout.log").read_bytes()
    require(hashlib.sha256(stdout).hexdigest() == toy["native_stdout_sha256"], "toy does not bind native stdout")
    require(toy["observed_x"] == toy["analytic_x"] == [1.5, 1.5] and toy["observed_original_objective"] == 4.5,
            "native toy point differs from exact analytic optimum")
    require(toy["original_equality_coefficient"] == 2**-50 and toy["original_equality_rhs"] == 3 * 2**-50,
            "exact dyadic toy input changed")
    return {"models": results, "analytic_check": "passed", "execution": "saved-data check only, no solver"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(check(args.root), indent=2))
