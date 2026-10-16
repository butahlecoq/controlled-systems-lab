"""Exact-dyadic audit of the frozen Issue 3 B08 numerical fixture.

Every parsed binary64 coefficient is interpreted as its exact rational value.
This checks an ideal affine recurrence for those values, not rounding within
the C++ recurrence or equivalence to the paper's printed decimal inputs.
"""

import argparse
from dataclasses import dataclass
from fractions import Fraction
import hashlib
from itertools import product
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SAVED_RAW = ROOT / "reports/algorithm-results/issue3-finite-catalogue-b4632ce76510aa4f/evidence/accepted-001/accepted.stdout"
PRODUCT_DRIVER = ROOT / "benchmarks/reporting/issue3/finite_catalogue_driver.cpp"
PRINTED_CHECKER = ROOT / "docs/research/tools/check_b08_displayed_exact.py"
PRINTED_RECORD = ROOT / "docs/research/evidence/b08-displayed-exact.json"
EXPECTED_RAW_SHA256 = "b4632ce76510aa4f2bb136baa193bc78da66506336a90d048cd8495c2d7926de"
EXPECTED_FIXTURE_SHA256 = "9494dec664f6fed74f39886ec3ab94c576dba6cdb5349f1f19329c6c31acc85a"
EXPECTED_SOURCE_COMMIT = "994f3ee4310b4087d289e2eb02adbdb9dfd97827"
EXPECTED_INPUT_SHA256 = "47ec040f5631dd1b24012318223efb73fa2bb7aa2db76c03c56cb88f2a85e733"
EXPECTED_SAVED_RESULT_SHA256 = "f04dc6d930bc9b09fb32e65565fa0e8d582c41bb8537265fe4b94389cac20004"
EXPECTED_PRINTED_CHECKER_SHA256 = "5a84edcf9a9761d5a7b8036417546d71160fe8d74eb800e651aad3edfe081866"
EXPECTED_PRINTED_RECORD_SHA256 = "dc8fbb816f359d132284fa92c8289b87a4cd7804270aa35fab926cdeb90e3e0a"


@dataclass(frozen=True)
class PlanScore:
    squared: Fraction
    vertices: int


def dyadic(value):
    if isinstance(value, str):
        return Fraction.from_float(float.fromhex(value))
    return Fraction.from_float(float(value))


def step(state, action, disturbance, model):
    return tuple(
        sum(dyadic(a) * x for a, x in zip(row_a, state))
        + sum(dyadic(b) * u for b, u in zip(row_b, action))
        + sum(dyadic(d) * w for d, w in zip(row_d, disturbance))
        for row_a, row_b, row_d in zip(model["A"], model["B"], model["D"])
    )


def exact_plan_scores(fixture):
    """Return all ordered plans' exact squared worst norms for this V fixture."""
    if fixture["safe"] != "universal" or fixture["objective"]["type"] != "residual_norm_terminal":
        raise ValueError("only universal-safe residual-norm fixtures are supported")
    model = fixture["model"]
    horizon = model["horizon"]
    actions = [tuple(map(dyadic, row)) for row in fixture["actions"]]
    vertices = [[tuple(map(dyadic, row)) for row in stage]
                for stage in fixture["disturbance_vertices_binary64_hex"]]
    if len(vertices) != horizon or any(not stage for stage in vertices):
        raise ValueError("one nonempty compact V stage is required per transition")
    zero_state = (Fraction(0),) * len(model["initial"])
    zero_action = (Fraction(0),) * len(model["B"][0])
    zero_disturbance = (Fraction(0),) * len(model["D"][0])
    offsets = []
    for history in product(*vertices):
        offset = zero_state
        for disturbance in history:
            offset = step(offset, zero_action, disturbance, model)
        offsets.append(offset)
    target = tuple(map(dyadic, fixture["objective"]["target"]))
    transform = tuple(tuple(map(dyadic, row)) for row in fixture["objective"]["C"])
    scores = []
    for plan in product(actions, repeat=horizon):
        center = tuple(map(dyadic, model["initial"]))
        for action in plan:
            center = step(center, action, zero_disturbance, model)
        worst = max(
            sum((sum(c * x for c, x in zip(row, (a + b for a, b in zip(center, offset)))) - t) ** 2
                for row, t in zip(transform, target))
            for offset in offsets
        )
        scores.append(PlanScore(worst, len(offsets)))
    return scores


def norm_bracket(squared):
    """Adjacent binary64 values enclosing the exact square root."""
    lower = math.sqrt(float(squared))
    while Fraction.from_float(lower) ** 2 > squared:
        lower = math.nextafter(lower, -math.inf)
    while Fraction.from_float(math.nextafter(lower, math.inf)) ** 2 <= squared:
        lower = math.nextafter(lower, math.inf)
    upper = lower if Fraction.from_float(lower) ** 2 == squared else math.nextafter(lower, math.inf)
    return lower, upper


def rational(value):
    return f"{value.numerator}/{value.denominator}"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(saved_row, product_row=None):
    if saved_row["fixture"] != "b08_rounded" or saved_row["source_commit"] != EXPECTED_SOURCE_COMMIT:
        raise ValueError("wrong saved fixture or numerical source")
    if saved_row["fixture_sha256"] != EXPECTED_FIXTURE_SHA256:
        raise ValueError("saved fixture source hash differs")
    canonical = saved_row["input_canonical"]
    input_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if input_hash != saved_row["input_sha256"] or input_hash != EXPECTED_INPUT_SHA256:
        raise ValueError("saved input hash differs")
    if digest(SAVED_RAW) != EXPECTED_RAW_SHA256:
        raise ValueError("saved raw capture hash differs")
    if digest(PRINTED_CHECKER) != EXPECTED_PRINTED_CHECKER_SHA256 or digest(PRINTED_RECORD) != EXPECTED_PRINTED_RECORD_SHA256:
        raise ValueError("printed-rational reference hash differs")
    fixture = json.loads(canonical)
    scores = exact_plan_scores(fixture)
    if len(scores) != 625 or sum(score.vertices for score in scores) != 160000:
        raise ValueError("B08 plan or terminal row count differs")
    minimum = min(score.squared for score in scores)
    lower, upper = norm_bracket(minimum)
    observed = saved_row["result"]
    observed_hash = hashlib.sha256(json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if observed_hash != EXPECTED_SAVED_RESULT_SHA256:
        raise ValueError("saved result hash differs")
    if observed["status"] != "numerical_optimal" or observed["plan_count"] != len(scores) or observed["evaluated_vertices"] != 160000:
        raise ValueError("product aggregate status or count differs")
    tolerance = Fraction(1, 10**9)
    product_value = dyadic(observed["value"])
    if product_value < dyadic(lower) - tolerance or product_value > dyadic(upper) + tolerance:
        raise ValueError("product value differs from exact-dyadic bracket")
    near = []
    near_tolerance = dyadic(saved_row["limits"]["near_optimal_tolerance"])
    for i, score in enumerate(scores):
        plan_lower, plan_upper = norm_bracket(score.squared)
        if dyadic(plan_upper) - dyadic(lower) <= near_tolerance:
            near.append(i)
        elif dyadic(plan_lower) - dyadic(upper) <= near_tolerance:
            raise ValueError(f"plan {i} is ambiguous at the near-tie threshold")
    if observed["minimizing_plan_indices"] != near:
        raise ValueError("product near-plan indices differ")
    if product_row is not None:
        current_driver_hash = hashlib.sha256(PRODUCT_DRIVER.read_bytes()).hexdigest()
        if (product_row["schema"] != "csl.issue3-b08-per-plan-audit/1" or
                product_row["source_commit"] != EXPECTED_SOURCE_COMMIT or
                product_row["fixture_sha256"] != current_driver_hash):
            raise ValueError("product source or fixture hash differs")
        if product_row["value"] != observed["value"] or product_row["minimizing_plan_indices"] != observed["minimizing_plan_indices"]:
            raise ValueError("product aggregate differs from saved result")
        maximum_plan_error = check_product_plans(product_row, input_hash, scores, len(fixture["actions"]))
    else:
        maximum_plan_error = None
    score_bytes = "\n".join(f"{s.squared.numerator}/{s.squared.denominator}" for s in scores).encode()
    printed = json.loads(PRINTED_RECORD.read_text(encoding="utf-8"))
    if printed["minimum_squared_exact"] != "112730080707/25000000":
        raise ValueError("printed-rational reference changed")
    product_error = max(abs(product_value - dyadic(lower)), abs(product_value - dyadic(upper)))
    return {
        "scope": "exact rational arithmetic on frozen public binary64 B08 inputs",
        "source_commit": EXPECTED_SOURCE_COMMIT,
        "saved_raw_sha256": EXPECTED_RAW_SHA256,
        "fixture_sha256": EXPECTED_FIXTURE_SHA256,
        "product_driver_sha256": hashlib.sha256(PRODUCT_DRIVER.read_bytes()).hexdigest() if product_row is not None else None,
        "input_sha256": input_hash,
        "saved_result_sha256": observed_hash,
        "printed_checker_sha256": EXPECTED_PRINTED_CHECKER_SHA256,
        "printed_record_sha256": EXPECTED_PRINTED_RECORD_SHA256,
        "printed_rational_minimum_squared": printed["minimum_squared_exact"],
        "per_plan_squared_sha256": hashlib.sha256(score_bytes).hexdigest(),
        "plans": len(scores),
        "terminal_rows": sum(s.vertices for s in scores),
        "minimum_squared_exact": f"{minimum.numerator}/{minimum.denominator}",
        "exact_minimizer_indices": [i for i, score in enumerate(scores) if score.squared == minimum],
        "exact_norm_lower": lower,
        "exact_norm_upper": upper,
        "exact_norm_lower_dyadic": rational(dyadic(lower)),
        "exact_norm_upper_dyadic": rational(dyadic(upper)),
        "saved_product_error_upper_exact": rational(product_error),
        "maximum_per_plan_error_upper_exact": rational(maximum_plan_error) if maximum_plan_error is not None else None,
        "product_status": observed["status"],
        "product_value": observed["value"],
        "product_near_indices": observed["minimizing_plan_indices"],
        "product_plan_rows_checked": len(scores) if product_row is not None else 0,
        "product_plan_result_sha256": hashlib.sha256(json.dumps(product_row, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if product_row is not None else None,
    }


def check_product_plans(product_row, input_hash, scores, catalogue_size):
    if product_row["input_sha256"] != input_hash or product_row["status"] != "numerical_optimal":
        raise ValueError("product plan input or status differs")
    plans = product_row["plans"]
    if len(plans) != len(scores):
        raise ValueError("product plan count differs")
    maximum_error = Fraction(0)
    for index, (plan, score) in enumerate(zip(plans, scores)):
        if plan["status"] != "feasible" or plan["evaluated_vertices"] != score.vertices:
            raise ValueError(f"product plan {index} status/count differs")
        number = index
        expected_indices = [0] * (len(plans[0]["action_indices"]))
        for stage in range(len(expected_indices) - 1, -1, -1):
            expected_indices[stage] = number % catalogue_size
            number //= catalogue_size
        if plan["action_indices"] != expected_indices:
            raise ValueError(f"product plan {index} action indices differ")
        lower, upper = norm_bracket(score.squared)
        value = dyadic(plan["worst_value"])
        if value < dyadic(lower) - Fraction(1, 10**9) or value > dyadic(upper) + Fraction(1, 10**9):
            raise ValueError(f"product plan {index} objective differs")
        maximum_error = max(maximum_error, abs(value - dyadic(lower)), abs(value - dyadic(upper)))
    return maximum_error


def saved_b08_row():
    return next(json.loads(line) for line in SAVED_RAW.read_text(encoding="utf-8").splitlines()
                if '"fixture":"b08_rounded"' in line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-plans", type=Path, help="JSON row emitted by the optional public audit driver")
    args = parser.parse_args()
    product_record = json.loads(args.product_plans.read_text(encoding="utf-8")) if args.product_plans else None
    print(json.dumps(audit(saved_b08_row(), product_record), indent=2, sort_keys=True))
