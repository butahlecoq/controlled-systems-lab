"""Independent saved-data checks; this script is not a model producer."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import numpy as np
from scipy.linalg import expm


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check(root: Path) -> dict:
    coefficients, supports, projections = 0, 0, 0
    maximum = 0.0
    for n in (8, 12, 16):
        matrices = {}
        with (root / f"{n}-state-matrices.csv").open() as stream:
            for record in csv.DictReader(stream):
                key = (record["kind"], int(record["stage"]))
                row, column = int(record["row"]), int(record["column"])
                width = 1 if key[0].endswith("B") else n
                matrix = matrices.setdefault(key, np.zeros((n, width)))
                require(np.isfinite(float(record["value"])), "nonfinite matrix record")
                matrix[row, column] = float(record["value"])
        E, implicitA, implicitB = (matrices[(kind, 0)] for kind in ("descriptor_E", "implicit_A", "implicit_B"))
        A, B = (matrices[(kind, 0)] for kind in ("rate_A", "rate_B"))
        # Separate transcription of source equation (3) with the declared
        # synthetic coefficient schedule; no production-model import.
        bends, tanks = {8: (1, 1), 12: (2, 2), 16: (4, 2)}[n]
        expectedE = np.eye(n); expectedA = np.zeros((n, n)); expectedB = np.zeros((n, 1))
        expectedA[0, 1] = expectedA[2, 3] = 1
        expectedA[1, 0], expectedA[1, 3], expectedB[1, 0] = -0.08, -0.002, -0.4
        expectedA[3, 0], expectedA[3, 3], expectedB[3, 0] = 0.3, -0.04, 0.6
        for mode in range(1, bends + 1):
            j = 4 + 2 * (mode - 1); frequency = 1.2 + 0.8 * mode
            expectedA[j, j + 1] = 1
            expectedA[j + 1, j], expectedA[j + 1, j + 1] = -(frequency * frequency), -0.08 * frequency
            expectedB[j + 1, 0] = 0.05 / mode
            expectedA[1, j], expectedA[3, j] = -0.015 / mode, -0.025 / mode
        for tank in range(1, tanks + 1):
            j = 4 + 2 * bends + 2 * (tank - 1); frequency = 0.35 + 0.25 * tank; squared = frequency * frequency
            expectedA[j, j + 1] = 1
            expectedA[j + 1, j], expectedA[j + 1, j + 1], expectedA[j + 1, 0] = -squared, -(0.05 + 0.03 * tank), -squared
            expectedA[1, j] = -0.012 / tank
            expectedE[1, j + 1], expectedE[3, j + 1] = 0.025 / tank, -0.045 / tank
            expectedE[j + 1, 3], expectedE[j + 1, 1] = -0.02 / tank, 0.04 / tank
        require(np.array_equal(E, expectedE) and np.array_equal(implicitA, expectedA) and
                np.array_equal(implicitB, expectedB), "source-equation/synthetic-parameter transcription differs")
        require(np.linalg.matrix_rank(E) == n, "singular descriptor")
        require(np.max(np.abs(E @ A - implicitA)) < 1e-12 and
                np.max(np.abs(E @ B - implicitB)) < 1e-12, "descriptor reconstruction differs")
        H = np.zeros((n + 1, n + 1)); H[:n, :n], H[:n, n:] = A, B
        discrete = expm(0.1 * H)
        for stage in range(40):
            for kind, reference in (("discrete_A", discrete[:n, :n]), ("discrete_B", discrete[:n, n:])):
                actual = matrices[(kind, stage)]
                require(np.max(np.abs(actual - reference)) < 2e-9, "independent exponential differs")
                coefficients += actual.size
        sets = {}
        factor_ids = {}
        with (root / f"{n}-state-generators.csv").open() as stream:
            reader = csv.DictReader(stream)
            coordinates = reader.fieldnames[4:]
            require(len(coordinates) == n, "physical coordinate count differs")
            for row in reader:
                stage = int(row["stage"])
                require(abs(float(row["time_s"]) - 0.1 * stage) < 1e-14, "physical time differs")
                vector = np.array([float(row[name]) for name in coordinates])
                require(np.all(np.isfinite(vector)), "nonfinite generator record")
                if row["kind"] == "center":
                    require(stage not in sets, "repeated center")
                    require(np.max(np.abs(vector)) == 0, "unexpected nonzero center")
                    sets[stage], factor_ids[stage] = [], []
                else:
                    require(row["kind"] == "generator", "unknown raw row kind")
                    sets[stage].append(vector); factor_ids[stage].append(row["factor_id"])
        require(set(sets) == set(range(41)), "missing full-state stage")
        sets = {stage: np.array(columns).T for stage, columns in sets.items()}
        radians = np.pi / 180
        initial_radii = [0.2 * radians, 0.05 * radians, 0.2, 0.02]
        initial_radii += [0.0005, 0.001] * bends + [0.001, 0.002] * tanks
        require(np.array_equal(sets[0], np.diag(initial_radii)), "declared synthetic initial box differs")
        reference = sets[0].copy()
        for stage in range(41):
            G = sets[stage]
            require(G.shape == (n, n + stage), "independent factor count differs")
            require(len(set(factor_ids[stage])) == n + stage, "factor identity reused")
            require(factor_ids[stage][:n] == factor_ids[0], "initial factor lineage changed")
            expected_controls = [f"flexible-pitch/synthetic-{n}-state/1/control/{k}/delta" for k in range(stage)]
            require(factor_ids[stage][n:] == expected_controls, "control factors not independent stage identities")
            error = float(np.max(np.abs(G - reference)))
            maximum = max(maximum, error)
            require(error < 2e-8 * (1 + np.max(np.abs(reference))), "independent full-state recurrence differs")
            reference = np.column_stack((discrete[:n, :n] @ reference,
                discrete[:n, n] * (4 * np.pi / 180)))
        with (root / f"{n}-state-support.csv").open() as stream:
            for row in csv.DictReader(stream):
                stage = int(row["stage"])
                direction = np.array([float(row["d_" + name]) for name in coordinates])
                actual = np.sum(np.abs(direction @ sets[stage]))
                reported = float(row["native_support"])
                require(abs(actual - reported) < 1e-12 * (1 + abs(actual)), "support CSV differs from generators")
                require(abs(reported - float(row["exponential_reference"])) < 2e-8 * (1 + abs(reported)), "reference support differs")
                supports += 1
        boundaries = {}
        with (root / f"{n}-state-projection-witnesses.csv").open() as stream:
            for row in csv.DictReader(stream):
                key = int(row["stage"]), int(row["plane"])
                boundaries.setdefault(key, []).append([float(row[name]) for name in coordinates])
        require(set(boundaries) == {(stage, plane) for stage in range(41) for plane in range(n // 2)}, "missing all-stage physical projection")
        for (stage, plane), points in boundaries.items():
            points = np.array(points)[:, 2 * plane:2 * plane + 2]
            require(np.all(np.isfinite(points)), "nonfinite boundary witness")
            angles = np.arange(97) * (2 * np.pi / 97)
            directions = np.column_stack((np.cos(angles), np.sin(angles)))
            boundary_support = np.max(points @ directions.T, axis=0)
            full_support = np.sum(np.abs(sets[stage][2 * plane:2 * plane + 2].T @ directions.T), axis=0)
            require(np.max(np.abs(boundary_support - full_support)) < 1e-10 * (1 + np.max(np.abs(full_support))), "saved projection differs from full-state support")
            projections += len(angles)
    return {"independent_exponential_coefficients": coefficients, "full_state_support_records": supports,
            "saved_projection_support_checks": projections, "maximum_generator_recurrence_difference": maximum,
            "assurance": "binary64 numerical saved-data audit; not a certified global inclusion proof"}


if __name__ == "__main__":
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    print(json.dumps(check(parser.parse_args().capture), indent=2))
