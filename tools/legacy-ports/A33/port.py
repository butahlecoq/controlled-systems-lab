"""Python 3 transcription of the active A33/A16/constrained Modified_SM closure.

Original MATLAB files are intentionally neither imported nor redistributed.
See PROVENANCE.md and DEVIATIONS.md before interpreting a result.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EPS = 1e-9
CONSECUTIVE_REDUNDANT = 10
GROUP_RADIUS_FACTOR = 0.05
MAX_HELPER_PIVOTS = 100_000
SOURCE_SHA256 = {
    "A33": "6ea9ee74cb376c644ab5441e7ca747b0ad5856d7c7c32e2518ec680502c8d7ae",
    "A16": "ec23c8b9984f0b475044320141d07b00823b47ae052ffbe6f9e9fa9e2551321a",
    "constrained_Modified_SM": "072745d6448f70d17fd12e8eea8027a87eb56be115cc33fb40737c3cc1d210b9",
}


class PortStop(Exception):
    def __init__(self, status: str, stage: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.stage = stage
        self.reason = reason


@dataclass
class HelperResult:
    points: np.ndarray
    outside: bool
    pivots: int
    front_count: int


@dataclass
class MembershipResult:
    outside: bool
    pivots: int
    basis: tuple[int, ...]  # original helper's 1-based column identities


def _solve(basis: np.ndarray, original: np.ndarray, stage: str) -> np.ndarray:
    try:
        with np.errstate(all="raise"):
            answer = np.linalg.solve(basis, original)
    except (np.linalg.LinAlgError, FloatingPointError) as error:
        raise PortStop("inconclusive", stage, f"tableau solve failed: {error}") from error
    if not np.all(np.isfinite(answer)):
        raise PortStop("inconclusive", stage, "tableau solve was nonfinite")
    return answer


def _entering_row(tableau: np.ndarray, target: int, stage: str) -> tuple[int, int]:
    scores = tableau[-1, :].copy()
    scores[target] = np.nan
    if np.all(np.isnan(scores)):
        raise PortStop("inconclusive", stage, "no eligible entering column")
    entering = int(np.nanargmax(scores))  # first maximum, matching MATLAB's tie index
    column = tableau[:-1, entering].copy()
    column[column < EPS] = np.nan
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        ratio = tableau[:-1, target] / column
    if np.all(np.isnan(ratio)):
        raise PortStop("inconclusive", stage, "no eligible leaving row")
    leaving = int(np.nanargmin(ratio))
    return entering, leaving


def simplex_hull_mod(points: np.ndarray, column: int) -> HelperResult:
    """A16's active tableau, bulk deletion, front move, and first-tie pivots."""
    x = np.array(points, dtype=np.float64, copy=True)
    dimensions, count = x.shape
    if count == 0 or column < 0 or column >= count:
        raise PortStop("failed", "A16", "invalid target column")
    sign = np.where(x[:, column] >= 0, 1.0, -1.0)
    transformed = x * sign[:, None]
    original = np.vstack((transformed, np.ones(count)))
    original = np.vstack((original, np.sum(original, axis=0) + 1))
    tableau = original.copy()
    basis_matrix = np.eye(dimensions + 2)
    basis_columns = np.full(dimensions + 2, -1, dtype=int)
    pivots = 0
    while True:
        other = np.ones(count, dtype=bool)
        other[column] = False
        if np.all(tableau[-1, other] <= EPS):
            if abs(tableau[-1, column]) > EPS:
                return HelperResult(x, True, pivots, 0)
            active = basis_columns[basis_columns >= 0]
            moved = active[active >= column]
            reduced = tableau[:-1, :].copy()
            reduced[:, active] = np.nan
            small = np.flatnonzero(np.sum(np.abs(reduced), axis=0) < 1 + EPS)
            remove = np.unique(np.concatenate((small, moved)))
            kept = np.delete(x, remove, axis=1)
            front = x[:, moved]
            return HelperResult(np.concatenate((front, kept), axis=1), False,
                                pivots, int(moved.size))
        if pivots >= MAX_HELPER_PIVOTS:
            raise PortStop("inconclusive", "A16", "pivot capacity exceeded")
        entering, leaving = _entering_row(tableau, column, "A16")
        basis_matrix[:, leaving] = original[:, entering]
        tableau = _solve(basis_matrix, original, "A16")
        basis_columns[leaving] = entering
        pivots += 1


def modified_sm(points: np.ndarray, candidate: np.ndarray) -> MembershipResult:
    """The constrained-directory sibling, not selected-source A30."""
    a = np.array(points, dtype=np.float64, copy=True)
    b = np.array(candidate, dtype=np.float64, copy=True)
    dimensions, count = a.shape
    sign = np.where(b < 0, -1.0, 1.0)
    top = np.column_stack((b * sign, a * sign[:, None]))
    original = np.vstack((top, np.ones(count + 1)))
    original = np.vstack((original, np.sum(original, axis=0) + 1))
    tableau = original.copy()
    basis_matrix = np.eye(dimensions + 2)
    basis_columns = np.zeros(dimensions + 2, dtype=int)
    pivots = 0
    while True:
        # max([]) is undefined in the archived helper. Preserve uncertainty.
        if count == 0:
            raise PortStop("inconclusive", "constrained Modified_SM",
                           "empty support has no MATLAB max result")
        if np.max(tableau[-1, 1:]) <= EPS:
            return MembershipResult(bool(tableau[-1, 0] > EPS), pivots,
                                    tuple(int(x) for x in basis_columns))
        if pivots >= MAX_HELPER_PIVOTS:
            raise PortStop("inconclusive", "constrained Modified_SM",
                           "pivot capacity exceeded")
        entering = int(np.argmax(tableau[-1, 1:])) + 1
        column = tableau[:-1, entering].copy()
        column[column < EPS] = np.nan
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            ratio = tableau[:-1, 0] / column
        if np.all(np.isnan(ratio)):
            raise PortStop("inconclusive", "constrained Modified_SM",
                           "no eligible leaving row")
        leaving = int(np.nanargmin(ratio))
        basis_matrix[:, leaving] = original[:, entering]
        tableau = _solve(basis_matrix, original, "constrained Modified_SM")
        basis_columns[leaving] = entering + 1
        pivots += 1


def _record(status: str, reason: str = "", stage: str = "") -> dict:
    return {"algorithm": "A33 Python 3 transcription", "algorithm_status": status,
            "source_sha256": SOURCE_SHA256,
            "reason": reason, "stage": stage, "output": None,
            "itrt": 0, "observed_helper_pivots": 0, "helper_calls": {"A16": 0,
            "constrained_Modified_SM": 0}, "stage2_scanned": 0,
            "stage3_scanned": 0, "grouping_triggered": False,
            "group_fixed_count": 0, "group_nearby_appends": 0}


def preprocess(cloud: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A33's unique rows and signed max-abs box score, before Step 2."""
    unique = np.unique(cloud, axis=0)
    if len(unique) < 2:
        raise PortStop("failed", "A33 preprocessing",
                       "source selects columns 1:2 but fewer than two unique points exist")
    matrix = unique.T
    maximum, minimum = np.max(matrix, axis=1), np.min(matrix, axis=1)
    midpoint = 0.5 * (maximum + minimum)
    widths = maximum - minimum
    if not np.all(np.isfinite(midpoint)) or not np.all(np.isfinite(widths)):
        raise PortStop("inconclusive", "A33 sorting", "nonfinite box arithmetic")
    if np.any(widths == 0):
        raise PortStop("inconclusive", "A33 sorting",
                       "zero-range axis makes source normalized score NaN")
    with np.errstate(all="raise"):
        scores = np.max(np.abs((matrix - midpoint[:, None]) / widths[:, None]), axis=0)
    # sortrows([unique,score],-last): descending signed max-abs score.
    # Stable ties retain the lexicographic unique order.
    order = np.argsort(-scores, kind="stable")
    return matrix[:, order], widths, scores[order]


def run(points: list[list[float]]) -> dict:
    """Run A33 on row-wise input; always return a result/failure record."""
    result = _record("inconclusive")
    try:
        cloud = np.asarray(points, dtype=np.float64)
        if cloud.ndim != 2 or cloud.shape[1] == 0 or not np.all(np.isfinite(cloud)):
            raise PortStop("failed", "input", "expected finite, nonempty coordinate rows")
        matrix, widths, _ = preprocess(cloud)
        retained = matrix[:, :2].copy()
        consecutive = 0
        trigger_column = None
        for column in range(2, matrix.shape[1]):
            retained = np.column_stack((retained, matrix[:, column]))
            checked = simplex_hull_mod(retained, retained.shape[1] - 1)
            result["helper_calls"]["A16"] += 1
            result["observed_helper_pivots"] += checked.pivots
            result["stage2_scanned"] += 1
            retained = checked.points
            consecutive = 0 if checked.outside else consecutive + 1
            if consecutive >= CONSECUTIVE_REDUNDANT:
                trigger_column = column
                break
        if trigger_column is not None:
            result["grouping_triggered"] = True
            # Source A=M(:,i:end) includes the just-tested tenth redundant point.
            remaining = matrix[:, trigger_column:]
            fixed = retained.copy()  # floor(size(C,2)*1) takes all current C
            result["group_fixed_count"] = fixed.shape[1]
            retained = np.empty((matrix.shape[0], 0))
            nearby = np.empty((matrix.shape[0], 0))
            for column in range(remaining.shape[1]):
                candidate = remaining[:, column]
                # Cj persists across candidates, and current C grows only for
                # points classified outside by the constrained sibling helper.
                for previous in range(retained.shape[1]):
                    if np.linalg.norm(candidate - retained[:, previous]) <= GROUP_RADIUS_FACTOR * np.min(widths):
                        nearby = np.column_stack((nearby, retained[:, previous]))
                        result["group_nearby_appends"] += 1
                checked = modified_sm(np.column_stack((fixed, nearby)), candidate)
                result["helper_calls"]["constrained_Modified_SM"] += 1
                result["observed_helper_pivots"] += checked.pivots
                result["stage3_scanned"] += 1
                if checked.outside:
                    retained = np.column_stack((retained, candidate))
            retained = np.column_stack((retained, fixed))
        column = 0
        while column < retained.shape[1]:
            checked = simplex_hull_mod(retained, column)
            result["helper_calls"]["A16"] += 1
            result["observed_helper_pivots"] += checked.pivots
            retained = checked.points
            column += 1 if checked.outside else checked.front_count
            if column < 0 or result["helper_calls"]["A16"] > MAX_HELPER_PIVOTS:
                raise PortStop("inconclusive", "A33 final reduction",
                               "final scan capacity exceeded")
        result["algorithm_status"] = "completed"
        result["output"] = retained.T.tolist()
    except PortStop as stop:
        result["algorithm_status"] = stop.status
        result["reason"] = stop.reason
        result["stage"] = stop.stage
    except (FloatingPointError, OverflowError, ValueError, TypeError, IndexError,
            np.linalg.LinAlgError) as error:
        result["algorithm_status"] = "inconclusive"
        result["reason"] = f"numerical or shape failure: {error}"
        result["stage"] = "runtime"
    return result


def main() -> int:
    from oracle import check as check_quality

    parser = argparse.ArgumentParser(description="A33 active-closure Python 3 port (no benchmark)")
    parser.add_argument("fixture", type=Path, help="JSON object with row-wise 'points'")
    args = parser.parse_args()
    try:
        with args.fixture.open(encoding="utf-8") as source:
            fixture = json.load(source)
        points = fixture["points"]
        record = run(points)
    except (OSError, ValueError, KeyError, TypeError) as error:
        points = []
        record = _record("failed", f"fixture intake failed: {error}", "fixture")
    record["quality"] = check_quality(points, record["output"])
    print(json.dumps(record, sort_keys=True, allow_nan=False))
    return 0 if record["algorithm_status"] == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
