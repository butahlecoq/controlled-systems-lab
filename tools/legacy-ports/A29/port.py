"""Python 3 transcription of active A29 QLPHULL and A30 Modified_SM.

The original MATLAB files remain outside Git and are never imported. See
PROVENANCE.md and DEVIATIONS.md before interpreting a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EPS = 1e-9
MAX_HELPER_PIVOTS = 100_000

# Terminal algorithm statuses (see DEVIATIONS.md).
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_INCONCLUSIVE = "inconclusive"

SOURCE_SHA256 = {
    "A29": "663625d206758ad80a56dc0ef9f3ea66cbb18b3d374d46b4fc90c4bf19d95a65",
    "A30": "5e0f29b0bed8a87f8ec477cb0f3fae55c66f0e3e3b28021c032b9891afa9ea6a",
}


class PortStop(Exception):
    def __init__(self, status: str, stage: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.stage = stage
        self.reason = reason


@dataclass
class MembershipResult:
    outside: bool
    pivots: int
    basis: tuple[int, ...]  # 1-based A30 column identities


def modified_sm(points: np.ndarray, candidate: np.ndarray) -> MembershipResult:
    """A30's active fixed-epsilon inverse-basis membership tableau."""
    a = np.array(points, dtype=np.float64, copy=True)
    b = np.array(candidate, dtype=np.float64, copy=True)
    dimensions, count = a.shape
    if count == 0:
        raise PortStop(STATUS_INCONCLUSIVE, "A30", "empty support has no MATLAB max result")
    sign = np.where(b < 0, -1.0, 1.0)
    top = np.column_stack((b * sign, a * sign[:, None]))
    original = np.vstack((top, np.ones(count + 1)))
    original = np.vstack((original, np.sum(original, axis=0) + 1))
    tableau = original.copy()
    basis_matrix = np.eye(dimensions + 2)
    basis_columns = np.zeros(dimensions + 2, dtype=int)
    pivots = 0
    while True:
        if np.max(tableau[-1, 1:]) <= EPS:
            return MembershipResult(bool(tableau[-1, 0] > EPS), pivots,
                                    tuple(int(x) for x in basis_columns))
        if pivots >= MAX_HELPER_PIVOTS:
            raise PortStop(STATUS_INCONCLUSIVE, "A30", "pivot capacity exceeded")
        entering = int(np.argmax(tableau[-1, 1:])) + 1
        column = tableau[:-1, entering].copy()
        column[column < EPS] = np.nan
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            ratio = tableau[:-1, 0] / column
        if np.all(np.isnan(ratio)):
            raise PortStop(STATUS_INCONCLUSIVE, "A30", "no eligible leaving row")
        leaving = int(np.nanargmin(ratio))
        basis_columns[leaving] = entering + 1
        basis_matrix[:, leaving] = original[:, entering]
        try:
            with np.errstate(all="raise"):
                tableau = np.linalg.solve(basis_matrix, original)
        except (np.linalg.LinAlgError, FloatingPointError) as error:
            raise PortStop(STATUS_INCONCLUSIVE, "A30", f"tableau solve failed: {error}") from error
        if not np.all(np.isfinite(tableau)):
            raise PortStop(STATUS_INCONCLUSIVE, "A30", "tableau solve was nonfinite")
        pivots += 1


def preprocess(cloud: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A29's unique rows and descending abs(max(signed normalized offset))."""
    unique = np.unique(cloud, axis=0)
    if len(unique) < 2:
        raise PortStop(STATUS_FAILED, "A29 preprocessing",
                       "source selects columns 1:2 but fewer than two unique points exist")
    matrix = unique.T
    maximum, minimum = np.max(matrix, axis=1), np.min(matrix, axis=1)
    midpoint = 0.5 * (maximum + minimum)
    widths = maximum - minimum
    if not np.all(np.isfinite(midpoint)) or not np.all(np.isfinite(widths)):
        raise PortStop(STATUS_INCONCLUSIVE, "A29 sorting", "nonfinite box arithmetic")
    if np.any(widths == 0):
        raise PortStop(STATUS_INCONCLUSIVE, "A29 sorting",
                       "zero-range axis makes source normalized score NaN")
    with np.errstate(all="raise"):
        scores = np.abs(np.max((matrix - midpoint[:, None]) / widths[:, None], axis=0))
    # sortrows on the appended score descending. Equal-score ties keep the
    # lexicographic unique row order as an explicit port convention.
    order = np.argsort(-scores, kind="stable")
    return matrix[:, order], scores[order]


def _record(status: str, reason: str = "", stage: str = "") -> dict:
    return {"algorithm": "A29 Python 3 transcription", "source_sha256": SOURCE_SHA256,
            "algorithm_status": status, "reason": reason, "stage": stage,
            "output": None, "itrt": 0, "helper_calls": 0,
            "stage2_scanned": 0, "final_scanned": 0,
            "stage2_pivots": 0, "final_pivots": 0,
            "grouping_executed": False}


def run(points: list[list[float]]) -> dict:
    """Run active A29 on row-wise points, retaining every terminal outcome."""
    result = _record(STATUS_INCONCLUSIVE)
    try:
        cloud = np.asarray(points, dtype=np.float64)
        if cloud.ndim != 2 or cloud.shape[1] == 0 or not np.all(np.isfinite(cloud)):
            raise PortStop(STATUS_FAILED, "input", "expected finite, nonempty coordinate rows")
        matrix, _ = preprocess(cloud)
        retained = matrix[:, :2].copy()
        # A29 Step 2: each candidate is queried against current C. The
        # proposed Step 3/grouping/SMLP section is wholly commented out.
        for column in range(2, matrix.shape[1]):
            checked = modified_sm(retained, matrix[:, column])
            result["helper_calls"] += 1
            result["stage2_scanned"] += 1
            result["stage2_pivots"] += checked.pivots
            result["itrt"] += checked.pivots
            if checked.outside:
                retained = np.column_stack((retained, matrix[:, column]))
        # A29 Step 4 is simultaneous: every column is tested against the
        # unchanged C minus itself, then the Boolean vector selects output.
        extreme = []
        for column in range(retained.shape[1]):
            others = np.delete(retained, column, axis=1)
            checked = modified_sm(others, retained[:, column])
            result["helper_calls"] += 1
            result["final_scanned"] += 1
            result["final_pivots"] += checked.pivots
            result["itrt"] += checked.pivots
            extreme.append(checked.outside)
        result["output"] = retained[:, extreme].T.tolist()
        result["algorithm_status"] = STATUS_COMPLETED
    except PortStop as stop:
        result["algorithm_status"] = stop.status
        result["reason"] = stop.reason
        result["stage"] = stop.stage
    except (FloatingPointError, OverflowError, ValueError, TypeError, IndexError,
            np.linalg.LinAlgError) as error:
        result["algorithm_status"] = STATUS_INCONCLUSIVE
        result["reason"] = f"numerical or shape failure: {error}"
        result["stage"] = "runtime"
    return result


def main() -> int:
    from oracle import check as check_quality

    parser = argparse.ArgumentParser(description="A29/A30 active-closure Python 3 port")
    parser.add_argument("fixture", type=Path, help="JSON object with row-wise 'points'")
    args = parser.parse_args()
    try:
        with args.fixture.open(encoding="utf-8") as source:
            fixture = json.load(source)
        points = fixture["points"]
        record = run(points)
    except (OSError, ValueError, KeyError, TypeError) as error:
        points = []
        record = _record(STATUS_FAILED, f"fixture intake failed: {error}", "fixture")
    record["quality"] = check_quality(points, record["output"])
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    return 0 if record["algorithm_status"] == STATUS_COMPLETED else 2


if __name__ == "__main__":
    sys.exit(main())
