"""Versioned, immutable GEO-04 scenario inputs and analytic output oracles."""

CATALOG_VERSION = "geo04-analytic-v1"
SCENARIOS = ("crossing_octagon", "empty_intersection", "affine_equality", "essential_rows_highs")
EXPECTED = {
    "crossing_octagon": {"inputs": {"left_A": [[1,0],[-1,0],[0,1],[0,-1]], "left_b": [1,1,1,1],
                                     "right_A": [[1,1],[1,-1],[-1,1],[-1,-1]], "right_b": [1.5]*4},
                         "vertices": [[1,.5],[1,-.5],[-1,.5],[-1,-.5],[.5,1],[-.5,1],[.5,-1],[-.5,-1]], "inequalities": 8, "equalities": 0},
    "empty_intersection": {"inputs": {"left_A": [[1,0]], "left_b": [0], "right_A": [[-1,0]], "right_b": [-1]}, "vertices": [], "inequalities": 2},
    "affine_equality": {"inputs": {"A": [[1,0],[-1,0]], "b": [2,0], "E": [[0,1]], "f": [1]},
                        "vertices": [[0,1],[2,1]], "inequalities": 4, "equalities": 2},
    "essential_rows_highs": {"inputs": {"A": [[1,0],[-1,0],[0,1]], "b": [1,0,0], "E": [[0,1]], "f": [0]},
                             "inequalities": 3, "equalities": 1, "reduction_status": "incomplete", "lp_calls": 3, "removed_inequalities": []},
}
