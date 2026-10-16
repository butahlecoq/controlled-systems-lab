"""Trace A10's saved criterion against hash-identified A08/A09 expressions.

Reads private originals only when explicitly supplied. It does not execute
MATLAB or identify the generator of L13's published Table 2 rows.
"""
import argparse
from io import BytesIO
import hashlib
import json
import math
from pathlib import Path


RESEARCH = Path(__file__).resolve().parents[1]
VARIANT = "a10-saved-mat-criterion-trace-v1"
SOURCE_IDS = ("A08", "A09", "A10")


def registered_sources(archive_root):
    register = json.loads((RESEARCH / "archive-selected-sources.json").read_text(encoding="utf-8"))
    records = {entry["id"]: entry for entry in register["selected_sources"]}
    data = {}
    for source_id in SOURCE_IDS:
        record = records[source_id]
        path = archive_root / record["path"]
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ValueError(f"cannot read registered {source_id} private original") from error
        if len(content) != record["bytes"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"{source_id} SHA-256 or byte-count mismatch; supply the registered original")
        data[source_id] = content
    return data, {source_id: records[source_id]["sha256"] for source_id in SOURCE_IDS}


def criterion_values(state):
    """Eq. (16), A08's nonlinear report, and A09's distinct terminal norm."""
    oxidizer_flow, oxidizer_stock, fuel_flow, fuel_stock = state
    base = (oxidizer_flow - 60) ** 2 + oxidizer_stock ** 2 + fuel_stock ** 2
    synchronization = (fuel_stock * 2.5 - oxidizer_stock) ** 2
    fuel_deviation = fuel_flow - 24
    return {
        "l13_eq16": math.sqrt(base + fuel_deviation ** 2),
        "a08_report": math.sqrt(base + fuel_deviation + synchronization),
        "a09_candidate": math.sqrt(base + fuel_deviation ** 2 + synchronization),
    }


def trace(archive_root):
    originals, hashes = registered_sources(archive_root)
    try:
        import numpy as np
        from scipy.io import loadmat
    except ImportError as error:
        raise ValueError("NumPy and SciPy are required to read the registered A10 MAT file") from error
    saved = loadmat(BytesIO(originals["A10"]),
                    variable_names=("J", "m", "position", "UU", "UUU",
                                    "mo", "Mo", "mg", "Mg"))

    def array(name, shape):
        value = saved.get(name)
        if value is None or value.shape != shape or not np.isfinite(value).all():
            raise ValueError(f"A10 saved {name} has unexpected shape or nonfinite values")
        return value

    saved_j = float(array("J", (1, 1))[0, 0])
    open_loop = [float(value) for value in array("m", (4, 5))[:, -1]]
    adaptive = [float(value) for value in array("position", (4, 5))[:, -1]]
    trajectory_end = [float(array(name, (1, 90001))[0, -1])
                      for name in ("mo", "Mo", "mg", "Mg")]
    if trajectory_end != adaptive:
        raise ValueError("A10 adaptive saved position does not match trajectory endpoints")
    open_controls = [float(value) for value in array("UUU", (1, 4))[0]]
    adaptive_controls = [float(value) for value in array("UU", (1, 4))[0]]
    open_values = criterion_values(open_loop)
    adaptive_values = criterion_values(adaptive)
    if not math.isclose(saved_j, open_values["a08_report"], rel_tol=0, abs_tol=1e-12):
        raise ValueError("A10 saved J does not match A08's nonlinear open-loop reporting expression")
    if math.isclose(saved_j, open_values["a09_candidate"], rel_tol=0, abs_tol=1e-6):
        raise ValueError("A10 saved J does not distinguish A08 from A09's squared expression")

    def rounds_to(state, printed, places):
        return all(round(value, digits) == target for value, target, digits
                   in zip(state, printed, places))

    publication_match = (
        rounds_to(open_loop, (60.26, 22.6, 23.86, 5.0), (2, 1, 2, 0)) or
        rounds_to(adaptive, (60.0, 20.3, 24.0, 4.5), (0, 1, 0, 1)))
    return {
        "variant": VARIANT,
        "source_sha256": hashes,
        "saved_j": saved_j,
        "open_loop_terminal": open_loop,
        "adaptive_terminal": adaptive,
        "adaptive_trajectory_end": trajectory_end,
        "saved_open_loop_controls": open_controls,
        "saved_adaptive_controls": adaptive_controls,
        "open_loop_l13_eq16": open_values["l13_eq16"],
        "open_loop_a08_report": open_values["a08_report"],
        "open_loop_a09_candidate": open_values["a09_candidate"],
        "adaptive_l13_eq16": adaptive_values["l13_eq16"],
        "adaptive_a08_report": adaptive_values["a08_report"],
        "adaptive_a09_candidate": adaptive_values["a09_candidate"],
        "publication_row_match": publication_match,
        "scope": "A10 saved-workspace criterion trace; not L13 Table 2 reproduction",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = trace(arguments.archive_root)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True))
