#!/usr/bin/env python3
"""Create source-bound illustrative batches and render them offline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reports.stage_projection_data import dumps_stage_projection_batch
from scripts.reports.stage_projection_figures import render_batch

EXAMPLES = Path(__file__).resolve().parent / "examples"
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
BUNDLE_README = Path(__file__).resolve().parent / "BUNDLE-README.md"


def _parse(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if value.get("schema") != "csl.stage-projection-demo-source/1":
        raise ValueError(f"unsupported demo source schema: {path}")
    dimension = len(value["state_names"])
    if dimension != len(value["state_units"]) or dimension != len(value["initial_state"]):
        raise ValueError(f"state metadata dimension mismatch: {path}")
    matrix = value["dynamics"]["A"]
    control = value["dynamics"]["B"]
    if len(matrix) != dimension or any(len(row) != dimension for row in matrix) or len(control) != dimension:
        raise ValueError(f"dynamics dimension mismatch: {path}")
    lo, hi = value["dynamics"]["control_bounds"]
    if not lo < hi or value["dynamics"]["horizon"] < 1:
        raise ValueError(f"invalid control bounds or horizon: {path}")
    for first, second in value["coordinate_pairs"]:
        if first == second or min(first, second) < 0 or max(first, second) >= dimension:
            raise ValueError(f"invalid coordinate pair: {path}")
    return value, raw


def _stages(source: dict) -> list[list[list[float]]]:
    dynamics = source["dynamics"]
    matrix, control = dynamics["A"], dynamics["B"]
    low, high = dynamics["control_bounds"]
    current = [list(source["initial_state"])]
    stages = [current]
    for _ in range(dynamics["horizon"]):
        following = []
        for state, u in itertools.product(current, (low, high)):
            following.append([
                sum(matrix[row][column] * state[column] for column in range(len(state)))
                + control[row] * u
                for row in range(len(state))
            ])
        current = following
        stages.append(current)
    return stages


def _geometry_kind(points: list[list[float]]) -> tuple[str, list[list[float]]]:
    unique = list(dict.fromkeys(tuple(point) for point in points))
    if len(unique) == 1:
        return "point", [list(unique[0])]
    x0, y0 = unique[0]
    x1, y1 = unique[1]
    dx, dy = x1 - x0, y1 - y0
    has_area = any(dx * (y - y0) - dy * (x - x0) != 0.0 for x, y in unique[2:])
    if has_area:
        return "polygon", [list(point) for point in points]
    return "segment", [list(point) for point in points]


def _normalize_render_paths(directory: Path) -> None:
    """Make checked-in render outputs portable after absolute CLI paths print."""
    index = directory / "index.html"
    html = index.read_text(encoding="utf-8")
    html = html.replace(
        f'Output directory: <code class="path">{directory.resolve(strict=True)}</code>',
        'Output directory: <code class="path">this bundle directory</code>',
    )
    index.write_text(html, encoding="utf-8")

    receipt_path = directory / "render-manifest.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["output_directory"] = "."
    receipt["files"]["index.html"] = hashlib.sha256(index.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _batch(source: dict, source_bytes: bytes) -> dict:
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    coordinates = [
        {"id": f"x{index}", "name": name, "unit": source["state_units"][index]}
        for index, name in enumerate(source["state_names"])
    ]
    stages = _stages(source)
    pairs = source["coordinate_pairs"]
    records = []
    for stage_index, state_points in enumerate(stages):
        for pair_index, (first, second) in enumerate(pairs):
            projected = [[point[first], point[second]] for point in state_points]
            kind, vertices = _geometry_kind(projected)
            set_id = f"demo-state-set-R{stage_index}"
            projection_id = f"stage-projection/pair/{pair_index}/stage/{stage_index}"
            records.append({
                "stage": stage_index,
                "physical_time": None,
                "pair_index": pair_index,
                "source_assurance": "numerical",
                "source_set_ids": [set_id],
                "outcome": {
                    "status": "success",
                    "relation": "equivalent",
                    "assurance": "numerical",
                    "provider": {"id": "csl.demo.affine-box-coordinate-selection", "version": "1.0.0"},
                    "evidence": [{
                        "request_id": f"{source['request_id']}/pair/{pair_index}/stage/{stage_index}",
                        "ideal_output_id": projection_id,
                        "scope": "set_relation",
                        "input_set_ids": [set_id],
                        "support": {"kind": "symbolic_argument", "reference": "coordinate selection commutes with affine image"},
                        "assumptions": [
                            "binary64 affine arithmetic over the declared box-control model",
                            "all control-box corners are retained as V generators",
                            "projection preserves the requested coordinate order",
                        ],
                    }],
                    "components": [{
                        "component_id": f"demo/pair/{pair_index}/stage/{stage_index}",
                        "kind": kind,
                        "interpretation": "conv_vertices_plus_cone_rays",
                        "vertices": vertices,
                        "rays": [],
                    }],
                },
            })

    trajectory_series = []
    _, high = source["dynamics"]["control_bounds"]
    control_value = high
    state = list(source["initial_state"])
    trajectory = [state]
    for _ in range(source["dynamics"]["horizon"]):
        matrix, control = source["dynamics"]["A"], source["dynamics"]["B"]
        state = [sum(matrix[row][column] * state[column] for column in range(len(state)))
                 + control[row] * control_value for row in range(len(state))]
        trajectory.append(state)
    for pair in pairs:
        first, second = pair
        trajectory_series.append({
            "kind": "trajectory",
            "source_run_id": source["run_id"],
            "coordinate_ids": [f"x{first}", f"x{second}"],
            "points": [[point[first], point[second]] for point in trajectory],
            "evidence": f"illustrative fixed control u={control_value:g} at every stage; not optimized",
        })

    return {
        "schema": "csl.stage-projection-batch/1",
        "provenance": {
            "run_id": source["run_id"],
            "record_schema": source["record_schema"],
            "source_sha256": source_hash,
        },
        "problem_id": source["problem_id"],
        "request_id": source["request_id"],
        "route_id": source["route_id"],
        "coordinates": coordinates,
        "requested_pairs": pairs,
        "stage_axis": {"kind": "stage", "points": [float(index) for index in range(len(stages))], "unit": None},
        "relation": "equivalent",
        "assurance": "numerical",
        "records": records,
        "trajectory_series": trajectory_series,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    args = parser.parse_args()
    output = args.out.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    os.environ.setdefault("MPLCONFIGDIR", str(output / "mpl-config"))
    shutil.copyfile(BUNDLE_README, output / "README.md")
    inputs = []
    for stem in ("fuel-four-state", "nonfuel-integrator"):
        source_path = EXAMPLES / f"{stem}.json"
        source, raw = _parse(source_path)
        inputs.append({"path": str(source_path.relative_to(ROOT)),
                       "sha256": hashlib.sha256(raw).hexdigest()})
        batch = _batch(source, raw)
        expected = {
            "expected_run_id": source["run_id"],
            "expected_problem_id": source["problem_id"],
            "expected_request_id": source["request_id"],
            "expected_route_id": source["route_id"],
            "expected_record_schema": source["record_schema"],
            "expected_source_sha256": hashlib.sha256(raw).hexdigest(),
        }
        batch_bytes = dumps_stage_projection_batch(batch, **expected)
        batch_path = output / f"{stem}.stage-projection-batch.json"
        batch_path.write_bytes(batch_bytes)
        figures = render_batch(batch_path, output / f"{stem}-figures", expected_identity=expected,
                               style_path=STYLE.resolve(strict=True))
        _normalize_render_paths(output / f"{stem}-figures")
        print(f"{source['description']}")
        print(f"batch: {batch_path}")
        print(f"index: {(output / f'{stem}-figures/index.html').resolve()}")
        for figure in figures:
            print(f"{figure['title']}: {(output / f'{stem}-figures' / figure['svg']).resolve()} | "
                  f"{(output / f'{stem}-figures' / figure['png']).resolve()}")

    cache = output / "mpl-config"
    if cache.exists():
        shutil.rmtree(cache)
    source_files = ["benchmarks/reporting/stage-projection/prepare_demos.py",
                    "benchmarks/reporting/stage-projection/BUNDLE-README.md",
                    "scripts/reports/stage_projection_data.py",
                    "scripts/reports/stage_projection_figures.py",
                    "scripts/reports/figure_style.py",
                    "scripts/reports/styles/control-v1.json"]
    manifest = {
        "schema": "csl.stage-projection-demo-bundle/1",
        "classification": "illustrative demonstration; not benchmark results",
        "generator": "benchmarks/reporting/stage-projection/prepare_demos.py",
        "inputs": inputs,
        "source_files": [{"path": path,
                          "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
                         for path in source_files],
        "environment": {"python": platform.python_version(),
                        "matplotlib": importlib.metadata.version("matplotlib")},
        "artifacts": [],
    }
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS"}:
            manifest["artifacts"].append({
                "path": path.relative_to(output).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_paths = sorted(path for path in output.rglob("*")
                            if path.is_file() and path.name != "SHA256SUMS")
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(output).as_posix()}\n"
        for path in checksum_paths)
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    print(f"manifest: {manifest_path.resolve()}")
    print(f"checksums: {(output / 'SHA256SUMS').resolve()}")


if __name__ == "__main__":
    main()
