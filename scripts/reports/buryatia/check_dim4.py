#!/usr/bin/env python3
"""Run and independently check the literal affine 4D approximation record."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path


EXPECTED_FAMILIES = {
    "exact_affine_polytope", "unreduced_zonotope", "reduced_zonotope",
    "box", "parallelotope", "ellipsoid",
}
EXPECTED_MODULES = {
    "exact_affine_polytope": "csl.geometry.affine-sum",
    "unreduced_zonotope": "csl.geometry.generators.operations",
    "box": "csl.approximation.box",
    "parallelotope": "csl.approximation.parallelotope",
    "ellipsoid": "csl.geometry.ellipsoidal.factor",
}
SOURCE_SHA256 = "f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a"
REFERENCE_VOLUME = 40808.165574887396


def validate(record: dict) -> None:
    assert record["schema"] == "csl.buryatia.recursive-approximation-4d/1"
    assert record["case_id"] == "buryatia-dim4-matlab-literal-affine/1"
    assert record["source_variant_id"] == "buryatia-dim4-literal-script-affine/1"
    assert record["source_sha256"] == SOURCE_SHA256
    assert record["state_dimension"] == 4 and record["control_dimension"] == 2
    assert record["intervals"] == 7 and len(record["stage_models"]) == 7
    assert len(record["records"]) == 8
    reference = record["reference"]
    assert reference["terminal_vertex_count"] == 756
    assert abs(reference["terminal_volume"] - REFERENCE_VOLUME) <= 1e-10

    for stage_index, stage in enumerate(record["records"]):
        assert stage["stage"] == stage_index
        exact = stage["exact_reference"]
        assert exact["v_candidate_rows_are_minimal"] is False
        assert len(exact["vertices"]) == exact["v_candidate_rows"]
        assert all(len(point) == 4 for point in exact["vertices"])
        assert len(exact["projections_3d"]) == 3 and len(exact["projections_2d"]) == 6
        assert set(stage["families"][i]["family"] for i in range(6)) == EXPECTED_FAMILIES
        by_family = {item["family"]: item for item in stage["families"]}
        assert set(by_family) == EXPECTED_FAMILIES
        for family in by_family.values():
            assert family["status"] == "completed"
            assert math.isfinite(family["volume"])
            assert math.isfinite(family["excess_volume"])
            assert family["volume_assurance"].startswith("floating-point binary64")
            assert len(family["support_diagnostics"]) == 24
            if family["family"] in {"exact_affine_polytope", "unreduced_zonotope"}:
                assert family["coordinate_projections"] == {"derived_from": "exact_reference.vertices"}
                assert family["coordinate_projections_2d"] == {"derived_from": "exact_reference.vertices"}
            else:
                assert len(family["coordinate_projections"]) == 3
                assert len(family["coordinate_projections_2d"]) == 6
            invocations = family["module_invocations"]
            expected_provider = EXPECTED_MODULES.get(family["family"])
            if expected_provider is not None:
                assert invocations["provider"] == expected_provider
            if stage_index:
                if family["family"] == "exact_affine_polytope":
                    assert invocations["operations"]["provider"] == "csl.geometry.affine-sum"
                elif family["family"] == "unreduced_zonotope":
                    assert invocations["operations"]["affine_image"] == "csl.geometry.generators.operations"
                    assert invocations["operations"]["minkowski_sum"] == "csl.geometry.generators.operations"
                elif family["family"] == "reduced_zonotope":
                    assert invocations["reduction"].startswith("csl.geometry.zonotope.axis-cover/")
                    assert invocations["reduced_image"] == "csl.geometry.generators.operations"
                    assert invocations["minkowski_sum"] == "csl.geometry.generators.operations"
                    assert invocations["generator_v_conversion"] == "csl.geometry.generators.v-conversion/1.0.0"
                    assert invocations["hull_materialization"]["provider"] == "csl.geometry.affine-sum"
                elif family["family"] in {"box", "parallelotope"}:
                    operation = invocations["operation"]
                    assert operation["affine_sum"] == "csl.geometry.affine-sum"
                    assert operation["approximation"].startswith(expected_provider + "/")
                    assert operation["inclusion_basis"] == "v_h_containment"
                elif family["family"] == "ellipsoid":
                    operations = invocations["operations"]
                    assert operations["affine_image"] == "csl.geometry.ellipsoidal.factor-affine/1"
                    assert operations["control_box_outer"] == "csl.geometry.ellipsoidal.factor-box/1"
                    assert operations["outer_sum"] == "csl.geometry.ellipsoidal.factor-minkowski/1"
            assert family["max_abs_support_error_sampled_directions"] >= 0.0
            for sample in family["support_diagnostics"]:
                tolerance = 2e-9 * (1.0 + abs(sample["exact_support"]))
                if family["family"] in {"exact_affine_polytope", "unreduced_zonotope"}:
                    assert abs(sample["support_excess"]) <= tolerance
                else:
                    assert sample["support_excess"] >= -tolerance
        assert by_family["exact_affine_polytope"]["represented_set"]["vertices_ref"] == "exact_reference.vertices"
        assert by_family["unreduced_zonotope"]["generator_count"] == 2 * stage_index
        assert by_family["unreduced_zonotope"]["volume"] == by_family["exact_affine_polytope"]["volume"]
        assert by_family["reduced_zonotope"]["volume"] + 1e-8 >= exact["volume"]
        assert by_family["box"]["volume"] + 1e-8 >= exact["volume"]
        assert by_family["parallelotope"]["volume"] + 1e-8 >= exact["volume"]
        assert by_family["ellipsoid"]["volume"] + 1e-8 >= exact["volume"]
        ellipse = by_family["ellipsoid"]["represented_set"]
        assert ellipse["factor_rows"] == 4 and ellipse["factor_columns"] == 2 * stage_index
        for projection in by_family["ellipsoid"]["coordinate_projections"].values():
            assert projection["kind"] == "factor_ellipsoid_projection"
            assert projection["dimension"] == 3 and projection["factor_columns"] == 2 * stage_index
        assert len(by_family["ellipsoid"]["coordinate_projections_2d"]) == 6
        for projection in by_family["ellipsoid"]["coordinate_projections_2d"].values():
            assert projection["kind"] == "factor_ellipsoid_projection"
            assert projection["dimension"] == 2 and projection["factor_columns"] == 2 * stage_index
        assert by_family["exact_affine_polytope"]["module_invocations"]["provider"] == "csl.geometry.affine-sum"
    terminal = record["records"][-1]
    assert terminal["exact_reference"]["v_candidate_rows"] == 16384
    assert abs(terminal["exact_reference"]["volume"] - REFERENCE_VOLUME) <= 1e-9


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()
    result = subprocess.run([str(args.exe.resolve(strict=True)), "--dim4-literal-affine"],
                            check=False, capture_output=True, text=True)
    if result.returncode:
        print(result.stderr, file=sys.stderr, end="")
        return result.returncode
    validate(json.loads(result.stdout))
    print("Buryatia Dim4: eight full-state stages, six families, source reference, support diagnostics, and 3D ellipsoid projections pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
