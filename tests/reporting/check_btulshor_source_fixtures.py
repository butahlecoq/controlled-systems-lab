"""Compare the actual C++ CLI with saved original-procedure observations.

This is a functional regression check, not a benchmark. It deliberately preserves
source behavior, including the two known near-tolerance hull omissions.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


REPOSITORY = Path(__file__).resolve().parents[2]
EVIDENCE = REPOSITORY / "docs/research/evidence"
SOURCE_SHA256 = "06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442"
TOLERANCE = 1e-12


def numerically_equal(expected, actual):
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(expected) == len(actual)
                and all(numerically_equal(a, b) for a, b in zip(expected, actual)))
    return (type(actual) in (float, int) and math.isfinite(actual)
            and math.isclose(expected, actual, rel_tol=TOLERANCE, abs_tol=TOLERANCE))


def valid_index(value, count):
    return type(value) is int and 0 <= value < count


def check_retained_ids(case, output):
    indices = output.get("retained_indices")
    points = output["points"]
    if (not isinstance(indices, list) or len(indices) != len(points)
            or any(not valid_index(i, len(case["points"])) for i in indices)
            or len(set(indices)) != len(indices)):
        return ["retained original-index shape invalid"]
    if any(case["points"][i] != point for i, point in zip(indices, points)):
        return ["retained ID does not reconstruct raw input coordinate"]
    return []


def check_source_pairs(case, output):
    pairs = output.get("source_vertices")
    points = output["points"]
    if not isinstance(pairs, list) or len(pairs) != len(points):
        return ["source pair count differs"]
    errors = []
    for pair, point in zip(pairs, points):
        if (not isinstance(pair, list) or len(pair) != 2
                or not valid_index(pair[0], len(case["initial_points"]))
                or not valid_index(pair[1], len(case["control_points"]))):
            errors.append("source pair outside input or malformed")
            continue
        initial, control = pair
        rebuilt = []
        for a_row, b_row in zip(case["a"], case["b"]):
            left = 0.0
            for a, x in zip(a_row, case["initial_points"][initial]):
                left = left + a * x
            right = 0.0
            for b, u in zip(b_row, case["control_points"][control]):
                right = right + b * u
            rebuilt.append(left + right)
        if not numerically_equal(rebuilt, point):
            errors.append("source pair does not reconstruct image-plus-input point")
    return errors


def compare(record, output, modif_calls, pivot_count):
    case = record["case"]
    original = record["source_outcome"]["raw"]
    errors = []
    if not isinstance(output, dict):
        return ["C++ output is not an object"]
    for field, expected in (("schema", "csl.btulshor-raw-case/1"),
                            ("case_id", case["id"]), ("operation", case["operation"]),
                            ("status", "completed")):
        if output.get(field) != expected:
            errors.append(f"{field} differs: expected {expected!r}, got {output.get(field)!r}")
    if errors:
        return errors
    if type(output.get("pivot_count")) is not int or output["pivot_count"] != pivot_count:
        errors.append(f"pivot count differs: original={pivot_count}, C++={output.get('pivot_count')}")
    if case["operation"] == "modif":
        if type(output.get("original_status")) is not int or output["original_status"] != original["original_status"]:
            errors.append("original p differs")
        basis = output.get("basis")
        if (not isinstance(basis, list) or any(type(i) is not int for i in basis)
                or basis != original["basis"]):
            errors.append("basis differs")
        if not numerically_equal(original["x"], output.get("x")):
            errors.append("raw x differs")
        # The direct MODIF CLI makes exactly one call; its result has no call counter.
        if modif_calls != 1:
            errors.append("direct MODIF fixture does not describe one entry")
        return errors
    if not numerically_equal(original["points"], output.get("points")):
        errors.append("raw point values/order differ")
    count_name = "retained_count" if case["operation"] == "kpabep" else "point_count"
    expected_count = original["retained_count"]
    if type(output.get(count_name)) is not int or output[count_name] != expected_count:
        errors.append(f"{count_name} differs")
    if type(output.get("modif_calls")) is not int or output["modif_calls"] != modif_calls:
        errors.append(f"MODIF calls differ: original={modif_calls}, C++={output.get('modif_calls')}")
    if not errors:
        errors.extend(check_retained_ids(case, output) if case["operation"] == "kpabep"
                      else check_source_pairs(case, output))
    return errors


def load_fixtures():
    documents = [json.loads((EVIDENCE / name).read_text()) for name in (
        "btulshor-source-oracle-fixtures.json", "btulshor-near-tolerance-observations.json",
        "btulshor-source-operation-counts.json")]
    if any(document["source_sha256"] != SOURCE_SHA256 for document in documents):
        raise ValueError("fixture source identity differs")
    records = documents[0]["records"] + documents[1]["records"]
    ids = [record["case"]["id"] for record in records]
    counts = {record["case_id"]: record for record in documents[2]["records"]}
    if (len(records) != 45 or len(set(ids)) != 45 or set(ids) != set(counts)
            or len(documents[2]["records"]) != 45):
        raise ValueError("expected 45 unique cases and matching companion counts")
    if any(type(row.get(field)) is not int or row[field] < 0
           for row in counts.values() for field in ("modif_calls", "pivot_count")):
        raise ValueError("companion operation counts must be nonnegative integers")
    if any(record["source_outcome"]["execution"] != "completed" for record in records):
        raise ValueError("source fixture did not complete")
    return records, counts


def run(driver):
    fixtures, counts = load_fixtures()
    records = []
    with tempfile.TemporaryDirectory(prefix="btulshor-source-fixtures-") as directory:
        for index, record in enumerate(fixtures):
            case = record["case"]
            path = Path(directory) / f"case-{index}.json"
            # Only the input crosses the executable boundary, never the oracle outcome.
            path.write_text(json.dumps(case) + "\n")
            output = None
            try:
                process = subprocess.run([str(driver), "--case", str(path)], text=True,
                                         capture_output=True, timeout=8, check=False)
                if process.returncode:
                    errors = [f"process exit {process.returncode}: {process.stderr}"]
                else:
                    output = json.loads(process.stdout)
                    errors = compare(record, output, counts[case["id"]]["modif_calls"],
                                     counts[case["id"]]["pivot_count"])
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                errors = [str(error)]
            records.append({"case_id": case["id"], "operation": case["operation"],
                            "passed": not errors, "errors": errors, "cpp_result": output})
    failed = sum(not record["passed"] for record in records)
    return {
        "scope": "Actual C++ --case input-only JSON against saved original-source outcomes; no timing claim.",
        "driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
        "source_sha256": SOURCE_SHA256,
        "numeric_tolerance": {"absolute": TOLERANCE, "relative": TOLERANCE},
        "exact_fields": ["original status", "basis", "point ordering", "MODIF entry counts", "completed MODIF pivot counts",
                         "valid original-index/source-pair shape"],
        "cases": len(records), "passed": len(records) - failed, "failed": failed, "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="optional JSON functional-check receipt")
    args = parser.parse_args()
    result = run(args.driver.resolve())
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Actual C++ source differential: {result['passed']}/{result['cases']} passed")
    for record in result["records"]:
        if not record["passed"]:
            print(record["case_id"] + ": " + "; ".join(record["errors"]))
    return int(result["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
