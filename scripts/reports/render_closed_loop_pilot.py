#!/usr/bin/env python3
"""Render versioned closed-loop pilot pages from immutable saved episode records."""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from contracts import canonical_sha256

ROOT = Path(__file__).resolve().parents[2]
REPORT_ID = "closed-loop-pilot-v1"
ATTEMPTS = {
    "syn-nl-lv-01": "syn-nl-lv-01-20261111T114908Z-8dc20bed",
    "earth-orbit": "earth-orbit-20261111T114923Z-e26a58ff",
    "syn-nl-fuel-01": "syn-nl-fuel-01-20261111T114928Z-bf3654d0",
}
COVERAGE = "coverage-20261111T115150Z-05590667.json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def task_manifest(name: str) -> dict:
    return read_json(ROOT / f"docs/contracts/closed-loop/{name}.json")


def attempt_paths(name: str) -> tuple[Path, dict, dict, dict]:
    path = ROOT / "reports/closed-loop-pilot" / name / "attempts" / ATTEMPTS[name]
    record = read_json(path / "attempt.json")
    run = read_json(path / "run-manifest.json")
    common = read_json(path / "full-replay-common/independent-check.json")
    tight = read_json(path / "full-replay-tight/independent-check.json")
    task = task_manifest(name)
    require(record["status"] == "complete" and record["completed_holds"] == task["episode"]["intervals"],
            f"saved episode is not complete: {record['attempt_id']}")
    require(record["task_sha256"] == run["task_sha256"] == common["task_sha256"] == tight["task_sha256"],
            f"task identities differ for {name}")
    require(math.isclose(record["physical_objective"]["total"],
                         common["task_adapter_objective"]["total"], rel_tol=1e-12, abs_tol=1e-14),
            f"task and independent objective totals differ for {name}")
    require(common["status"] == tight["status"] == "complete", f"independent replay incomplete for {name}")
    return path, record, run, common


def project(task: dict, states: list[list[float]], name: str) -> tuple[list[tuple[str, str, list[int]]], dict | None]:
    case = task["model"]["case_id"]
    if name == "syn-nl-fuel-01":
        planes = [(p["names"], p["units"], p["indices"]) for p in task["coordinate_maps"]["requested_physical_planes"]]
        target = task["objective"]["source_definition"]["terminal_target"]
    elif name == "earth-orbit":
        planes = [(["r", "ω"], ["km", "rad/s"], [0, 3])]
        target = None
    else:
        planes = [([s["name"] for s in task["model"]["states"][:2]],
                   [s["unit"] for s in task["model"]["states"][:2]], [0, 1])]
        target = task["objective"]["source_definition"]["terminal_target"]
    if name == "earth-orbit": target = task["objective"]["target"]
    return planes, target


def _render_candidate(output: Path) -> dict:
    pilot = ROOT / "reports/closed-loop-pilot"
    coverage_path = pilot / COVERAGE
    coverage = read_json(coverage_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    stylesheet = ROOT / "docs/examples/examples.css"
    shutil.copyfile(stylesheet, output / "examples.css")
    successful = []
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    portable_coverage = copy.deepcopy(coverage)
    attempt_map = {}
    for row in portable_coverage["attempts"]:
        original = row.get("attempt_record", "")
        parts = Path(original).parts
        require(len(parts) >= 4 and parts[1] == "attempts", f"unrecognized attempt reference: {original}")
        task_name, attempt_id = parts[0], parts[2]
        source = pilot / task_name / "attempts" / attempt_id
        require(source.is_dir(), f"coverage attempt directory is missing: {source}")
        destination = raw / "attempts" / task_name / attempt_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
        row["repository_record_path"] = original
        row["attempt_record"] = f"attempts/{task_name}/{attempt_id}/{parts[-1]}"
        row["attempt_directory"] = f"attempts/{task_name}/{attempt_id}"
        attempt_map[row.get("attempt_id", attempt_id)] = row["attempt_record"]
    portable_coverage["attempt_map"] = attempt_map
    portable_coverage["evidence_root"] = "attempts/"
    (raw / "coverage.json").write_text(json.dumps(portable_coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    source_identities = {"schema": "csl.closed-loop.report-source-identities/1", "tasks": {},
        "capability_manifest": {"source": "docs/catalogue/closed-loop-pilot-capabilities-v1.json",
            "path": "capabilities/closed-loop-pilot-capabilities-v1.json"}}
    capability_dir = raw / "capabilities"; capability_dir.mkdir(parents=True, exist_ok=True)
    for capability_file in ("closed-loop-pilot-capabilities-v1.json", "closed-loop-pilot-capabilities-v1.sha256"):
        shutil.copyfile(ROOT / "docs/catalogue" / capability_file, capability_dir / capability_file)
    source_identities["capability_manifest"]["sha256"] = digest((capability_dir / "closed-loop-pilot-capabilities-v1.json").read_bytes())
    source_dir = raw / "source"
    for name in ATTEMPTS:
        task = task_manifest(name)
        task_dir = raw / "contracts"; task_dir.mkdir(parents=True, exist_ok=True)
        contract_path = ROOT / f"docs/contracts/closed-loop/{name}.json"
        shutil.copyfile(contract_path, task_dir / f"{name}.json")
        task_record_path = pilot / name / "attempts" / ATTEMPTS[name] / "attempt.json"
        task_sha256 = read_json(task_record_path)["task_sha256"]
        source_identities["tasks"][name] = {"task_sha256": task_sha256,
            "contract": f"contracts/{name}.json", "source_path": task["source"]["path"],
            "source_sha256": task["source"]["sha256"]}
        profile_source = ROOT / task["source"]["path"]
        require(profile_source.is_file(), f"source task profile is missing: {task['source']['path']}")
        actual_source_hash = (canonical_sha256(read_json(profile_source))
            if task["source"]["kind"] == "mpc11-scenario" else digest(profile_source.read_bytes()))
        require(actual_source_hash == task["source"]["sha256"],
                f"source task profile hash changed: {task['source']['path']}")
        profile_target = source_dir / task["source"]["path"]
        profile_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(profile_source, profile_target)
    (raw / "source-identities.json").write_text(json.dumps(source_identities, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for name, attempt_id in ATTEMPTS.items():
        source, record, run, common = attempt_paths(name)
        task = task_manifest(name)
        tight = read_json(source / "full-replay-tight/independent-check.json")
        graph = read_json(source / "resolved-graph.json")
        for identity in graph["source_files"]:
            source_file = ROOT / identity["path"]
            require(source_file.is_file() and digest(source_file.read_bytes()) == identity["sha256"],
                    f"controller or execution source hash changed: {identity['path']}")
            copy_target = source_dir / identity["path"]
            copy_target.parent.mkdir(parents=True, exist_ok=True)
            if not copy_target.exists(): shutil.copyfile(source_file, copy_target)
        planes, target = project(task, record["physical_states"], name)
        filename = f"{name}-phase.png"
        (output / "assets").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / "phase.png", output / "assets" / filename)
        plots = [{"filename": filename, "planes": planes}]
        successful.append({"name": name, "attempt_id": attempt_id, "record": record, "run": run,
            "common": common, "tight": tight, "task": task, "plots": plots})
    failures = [row for row in portable_coverage["attempts"]
        if row.get("overall_status", row.get("status")) != "complete"]
    rows = []
    sections = []
    example_data = next(row for row in successful if row["name"] == "syn-nl-lv-01")
    for row in successful:
        record = row["record"]; task = row["task"]; name = row["name"]
        run = row["run"]; objective = record["physical_objective"]
        record_path = f"raw/attempts/{name}/{record['attempt_id']}"
        relative = f"{record_path}/attempt.json"
        checks = f"{record_path}/full-replay-common/independent-check.json"
        rows.append(f"<tr><th>{html.escape(task['model']['case_id'])}</th><td>{record['completed_holds']}/{task['episode']['intervals']}</td>"
            f"<td>{objective['terminal']:.16g} + {objective['running']:.16g} = {objective['total']:.16g}</td>"
            f"<td>{row['common']['objective_difference']:.3g}; tight {row['tight']['objective_difference']:.3g}</td>"
            f"<td><a href=\"{relative}\">attempt</a> · <a href=\"{checks}\">common check</a></td></tr>")
        for plot in row["plots"]:
            axes = "; ".join(f"({', '.join(names)}) in ({', '.join(units)})" for names, units, _ in plot["planes"])
            sections.append(f"<figure><img src=\"assets/{plot['filename']}\" alt=\"Saved Matplotlib phase projections of the observed source-bound {html.escape(name)} trajectory.\"><figcaption>{html.escape(name)} saved phase projection: {html.escape(axes)}. This shows the numerical observed-state trajectory only.</figcaption></figure>")
    failure_html = "".join(f"<li><a href=\"raw/{html.escape(row.get('attempt_record','coverage.json'))}\">{html.escape(row.get('attempt_id','unknown'))}</a>: {html.escape(str(row.get('overall_status', row.get('status'))))}; {row.get('completed_holds',0)} holds recorded</li>" for row in failures)
    commit = successful[0]["run"]["source_commit"]
    index = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Closed-loop pilot: three source-bound tasks</title><link rel="stylesheet" href="examples.css"></head><body><div class="shell"><aside aria-hidden="true"></aside><main>
<h1>Closed-loop pilot: three source-bound tasks</h1><p class="muted">Versioned numerical report · publication status: review and main-only Pages deployment pending</p>
<section class="panel"><h2>What ran</h2><p>Each task used the source-bound continuous NMPC profile. At every original stage, the controller queried the observed physical state, applied one control hold, and advanced the nonlinear plant through the common CSL adaptive RK4 step-doubling executor. Every trajectory retains its original task, action profile, N/T, objective and absolute-stage identities. Solver predictions are distinct from applied plant observations.</p><p>Controller source commit <code>{html.escape(commit)}</code>. Reports are one-off numerical observations; there is no global-optimality, reachability, safety, robustness or speed-winner claim.</p></section>
<section><h2>Episode results</h2><div class="scroll" role="region" tabindex="0" aria-label="Closed-loop episode results table"><table><thead><tr><th>Task</th><th>Applied holds</th><th>Terminal + running = total</th><th>Objective disagreement (common; tight)</th><th>Raw evidence</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="panel"><h2>Observed trajectories</h2>{''.join(sections)}</section>
<section class="panel"><h2>Independent checks and limits</h2><p>Both common and tighter full-episode CSL replays completed. Physical state bounds were checked on each replay's numerical report grid (20 samples per original hold plus the initial state); applied input bounds were checked on the original held controls. These sampled checks are not continuous-time certificates.</p><p>Initial episodes retained in the coverage record:</p><ul>{failure_html}</ul><p><a href="raw/coverage.json">Portable append-only coverage map</a> · <a href="raw/source-identities.json">Task and controller source identities</a> · <a href="raw/capabilities/closed-loop-pilot-capabilities-v1.json">Capability manifest</a> · <a href="example-2d.html">Minimal Lotka–Volterra 2D example</a> · <a href="../closed-loop-pilot-v1.zip">Offline report and raw-record bundle</a></p></section>
<p class="provenance">Source-bound attempt and check JSON is included under <code>raw/</code>. Report publication and live URL/hash verification remain pending.</p></main></div></body></html>'''
    lv = example_data["record"]; lv_task = example_data["task"]
    lv_obj = lv["physical_objective"]
    example = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lotka–Volterra observed-state trajectory</title><link rel="stylesheet" href="examples.css"></head><body><div class="shell"><aside aria-hidden="true"></aside><main>
<h1>Lotka–Volterra observed-state trajectory</h1><p class="muted">Minimal 2D example from saved episode <code>{html.escape(lv['attempt_id'])}</code></p>
<section class="panel"><h2>Model and loop</h2><p>State coordinates are prey <code>P</code> and predator <code>R</code>; one observed-state NMPC update occurs at each of the source task's 30 original 0.05-hour stages. The controller proposes the first input, CSL advances one held interval, and the next solve receives the resulting physical observation.</p><p>Source equations: <code>{html.escape('; '.join(lv_task['model']['equations']))}</code></p><p>Goal: soft terminal reference <code>{html.escape(str(lv_task['objective']['source_definition']['terminal_target']))}</code>. It is an objective target, not a terminal constraint.</p></section>
<figure><img src="assets/syn-nl-lv-01-phase.png" alt="Saved Lotka–Volterra Matplotlib phase projection with start, end, and soft objective target markers."><figcaption>Saved Matplotlib phase plot from the episode renderer, showing the observed plant states. The star is the initial observation, the red cross is the terminal observation, and the gold cross is the soft objective reference. This single path does not represent a reachable set.</figcaption></figure>
<section><h2>Checkable result</h2><div class="scroll" role="region" tabindex="0" aria-label="Lotka–Volterra objective and replay checks"><table><tbody><tr><th>Terminal objective</th><td>{lv_obj['terminal']:.16g}</td></tr><tr><th>Running objective</th><td>{lv_obj['running']:.16g}</td></tr><tr><th>Total</th><td>{lv_obj['total']:.16g}</td></tr><tr><th>Independent objective difference</th><td>{example_data['common']['objective_difference']:.3g}</td></tr><tr><th>Common replay endpoint difference, by state</th><td>{html.escape(str(example_data['common']['hold_endpoint_max_abs_difference_from_applied_execution']))}</td></tr></tbody></table></div><p><a href="raw/attempts/syn-nl-lv-01/{lv['attempt_id']}/full-replay-common/independent-check.json">Independent common replay check</a> · <a href="raw/attempts/syn-nl-lv-01/{lv['attempt_id']}/full-replay-tight/independent-check.json">Tighter replay check</a> · <a href="raw/attempts/syn-nl-lv-01/{lv['attempt_id']}/attempt.json">Full saved attempt and per-update records</a></p></section>
<section class="panel"><h2>Reproduce the saved report</h2><p>This rendering uses the repository's pinned Linux CPython 3.11 lock for the runner environment. Set <code>PYTHON</code> to the qualified interpreter; set <code>MPC11_VENV</code> and <code>MPC11_WHEELS</code> to new directories when creating a fresh environment.</p><pre><code>python3.11 -m venv "$MPC11_VENV"
"$MPC11_VENV/bin/python" -m pip download --only-binary=:all: --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock --dest "$MPC11_WHEELS"
"$MPC11_VENV/bin/python" -m pip install --no-index --find-links "$MPC11_WHEELS" --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock
PYTHON="${{PYTHON:-$MPC11_VENV/bin/python}}"
"$PYTHON" scripts/reports/render_closed_loop_pilot.py --output reports/closed-loop-pilot/closed-loop-pilot-v1</code></pre></section>
<p><a href="index.html">Back to three-task report</a></p></main></div></body></html>'''
    (output / "index.html").write_text(index, encoding="utf-8")
    (output / "example-2d.html").write_text(example, encoding="utf-8")
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name != "manifest.json")
    manifest = {"schema": "csl.closed-loop-published-report/1", "report_id": REPORT_ID,
        "numerical_source_commit": commit, "report_source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "coverage_record": COVERAGE, "attempt_ids": {name: ATTEMPTS[name] for name in ATTEMPTS},
        "stylesheet": {"path": "examples.css", "sha256": digest((output / "examples.css").read_bytes()),
            "source": "docs/examples/examples.css"},
        "files": {path.relative_to(output).as_posix(): digest(path.read_bytes()) for path in files},
        "publication_status": "pending independent report review and main-only Pages deployment"}
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    archive = output.parent / f"{REPORT_ID}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(f"{REPORT_ID}/{path.relative_to(output).as_posix()}", (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
                bundle.writestr(info, path.read_bytes())
    return manifest


def file_map(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path.read_bytes())
            for path in sorted(root.rglob("*")) if path.is_file()}


def render_bundle(output: Path) -> dict:
    output = output.resolve()
    archive = output.parent / f"{REPORT_ID}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f".{REPORT_ID}-candidate-", dir=output.parent))
    candidate = scratch / output.name
    candidate_archive = scratch / archive.name
    try:
        manifest = _render_candidate(candidate)
        shutil.move(str(scratch / archive.name), str(candidate_archive))
        if output.exists() or archive.exists():
            require(output.is_dir() and archive.is_file(),
                    "versioned report destination is incomplete; choose a new report ID")
            require(file_map(output) == file_map(candidate) and
                    digest(archive.read_bytes()) == digest(candidate_archive.read_bytes()),
                    "versioned report ID already exists with different content; choose a new report ID")
            return manifest
        candidate.rename(output)
        candidate_archive.rename(archive)
        return manifest
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/closed-loop-pilot/closed-loop-pilot-v1")
    args = parser.parse_args()
    manifest = render_bundle(args.output.resolve())
    print(json.dumps({"status": "complete", "report_id": REPORT_ID,
        "manifest_sha256": digest((args.output.resolve() / "manifest.json").read_bytes()),
        "files": len(manifest["files"]), "archive": str(args.output.resolve().parent / f"{REPORT_ID}.zip")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
