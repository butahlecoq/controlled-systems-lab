"""Stage immutable 35-model native tracking evidence; never reruns a solver."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
import subprocess
from html import escape
from io import BytesIO
from pathlib import Path

from report_data import require

ROOT = Path(__file__).resolve().parents[2]
ROUTE = "native-model-tracking-first-pass-v1"
CAPTURE = "capture-20261113T183906Z"
CHECKS = "independent-checks-20261113T190626Z"
FIGURES = "visual-example-20261113T184921Z"
CAPTURE_MANIFEST_SHA256 = "2ce8a1783b4a32463c2accb7c4af80d73b4f6617d8c1ffd8fba13b6c59f491a2"
INPUT_INVENTORY_SHA256 = "df9e747702b2807d1657e6ce5ca0eebe2da4c50869d1bad02d4bbe5461242fec"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root) / "reports/algorithm-results/native-model-tracking-first-pass-v1"
    capture = root / CAPTURE
    manifest_bytes = (capture / "manifest.json").read_bytes()
    require(digest(manifest_bytes) == CAPTURE_MANIFEST_SHA256, "frozen model tracking capture changed")
    manifest = json.loads(manifest_bytes)
    require(manifest["summary"] == {"attempted_model_records": 35, "completed_models": 32,
            "failed_models": 3, "timed_out_models": 0}, "capture outcome inventory changed")
    files: dict[str, bytes] = {}

    input_inventory_path = root / "publication-input-inventory.json"
    inventory_bytes = input_inventory_path.read_bytes()
    require(digest(inventory_bytes) == INPUT_INVENTORY_SHA256, "published input inventory changed")
    inventory = json.loads(inventory_bytes)
    require(inventory.get("capture_manifest_sha256") == CAPTURE_MANIFEST_SHA256,
            "input inventory does not bind the frozen capture")
    expected_paths = inventory.get("files_sha256", {})
    actual_paths = set()
    for directory in (capture, root / CHECKS, root / FIGURES):
        require(not directory.is_symlink(), "saved evidence directory is symlinked")
        for source in directory.rglob("*"):
            require(not source.is_symlink(), "saved evidence contains a symlink")
            if source.is_file():
                relative = source.relative_to(root).as_posix()
                actual_paths.add(relative)
                require(relative in expected_paths, "unlisted saved evidence file: "+relative)
                require(digest(source.read_bytes()) == expected_paths[relative],
                        "saved evidence digest differs: "+relative)
    require(actual_paths == set(expected_paths), "saved evidence inventory is incomplete")

    def add(source: Path, target: str) -> None:
        require(source.is_file() and not source.is_symlink(), f"missing or linked saved evidence: {source}")
        files[target] = source.read_bytes()

    # Keep the committed capture immutable. Publish a location-free projection and bind it to
    # the exact original manifest digest above.
    public_manifest = {key: value for key, value in manifest.items() if key not in {
        "executables", "branch", "installed_sdk_component_qualification"}}
    public_manifest["source_capture_manifest_sha256"] = CAPTURE_MANIFEST_SHA256
    if "catalogue_capture" in public_manifest:
        public_manifest["catalogue_capture"]["command"] = [Path(arg).name for arg in public_manifest["catalogue_capture"].get("command", [])]
    public_manifest["outcomes"] = [{key: value for key, value in row.items() if key != "command"}
                                    for row in public_manifest.get("outcomes", [])]
    public_manifest["installed_sdk_component_qualification"] = {
        "source_commit": "c16a19dd900bc5e186273008f610a712dc177981",
        "archive_sha256": "12efd2001ee09b2154e6b18fc5a78e937dface24207bdd850a964f3beedcb00b",
        "scope": "history compiler component only; not a whole-SDK qualification"}
    sdk = dict(public_manifest.get("frozen_installed_sdk_snapshot", {}))
    for key in ("prefix", "inventory_file"):
        sdk.pop(key, None)
    public_manifest["frozen_installed_sdk_snapshot"] = sdk
    receipt = dict(public_manifest.get("native_build_receipt", {}))
    for key in ("cmake_executable", "compiler_executable"):
        if key in receipt:
            receipt[key] = Path(receipt[key]).name
    public_manifest["native_build_receipt"] = receipt
    files["capture-manifest.json"] = (json.dumps(public_manifest, indent=2, sort_keys=True)+"\n").encode()
    files["source-input-inventory.json"] = inventory_bytes
    add(Path(repository_root) / "docs/examples/examples.css", "examples.css")
    add(capture / "outcomes.csv", "outcomes.csv")
    catalogue_path = capture / "catalogue-data/native-output/catalogue.csv"
    with catalogue_path.open(newline="", encoding="utf-8") as stream:
        catalogue_rows = list(csv.DictReader(stream))
    # Omit any owner-private source locator while retaining source title/hash, qualification,
    # time grid, dimensions, coordinate names/units, and exact numeric model CSV.
    safe_catalogue = []
    for row in catalogue_rows:
        row["source_locator"] = ""
        safe_catalogue.append(row)
    import io
    safe_csv = io.StringIO(newline="")
    writer = csv.DictWriter(safe_csv, fieldnames=list(safe_catalogue[0]))
    writer.writeheader()
    writer.writerows(safe_catalogue)
    files["raw/catalogue.csv"] = safe_csv.getvalue().encode()
    add(capture / "catalogue-data/native-output/models.csv", "raw/models.csv")
    add(capture / "catalogue-data/native-output/coordinates.csv", "raw/coordinates.csv")
    models_path = capture / "catalogue-data/native-output/models.csv"
    model_values: dict[str, dict[str, dict[int, dict[int, str]]]] = {}
    with models_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            model_values.setdefault(row["model"], {}).setdefault(row["kind"], {}).setdefault(int(row["row"]), {})[int(row["column"])] = row["value"]
    matrix_sections = []
    for index, model in enumerate(safe_catalogue, 1):
        ident = model["model"]
        kinds = model_values[ident]
        dims = f"A {len(kinds.get('A', {}))}×{max((len(row) for row in kinds.get('A', {}).values()), default=0)}, B {len(kinds.get('B', {}))}×{max((len(row) for row in kinds.get('B', {}).values()), default=0)}"
        matrices = []
        for kind in ("A", "B", "G"):
            rows = kinds.get(kind, {})
            if not rows:
                continue
            nrows, ncols = max(rows)+1, max(max(row) for row in rows.values())+1
            body = "".join("<tr>"+"".join(f"<td>{escape(rows.get(r, {}).get(c, '0'))}</td>" for c in range(ncols))+"</tr>" for r in range(nrows))
            matrices.append(f"<h4>{kind} ({nrows}×{ncols})</h4><div class=matrix><table>{body}</table></div>")
        for kind in ("a", "x0", "nominal_w"):
            rows = kinds.get(kind, {})
            if rows:
                vector = ", ".join(escape(rows.get(r, {}).get(0, "0")) for r in range(max(rows)+1))
                matrices.append(f"<h4>{kind}</h4><p><code>{vector}</code></p>")
        matrix_sections.append(f"<details><summary>{index}. {escape(model['title'])} · {escape(model['source_title'])} · {escape(dims)} · Δt={escape(model['time_step'])} {escape(model['time_unit'])}</summary><p>Source SHA-256: <code>{escape(model['source_sha256'])}</code><br>Qualification: {escape(model['source_qualification'])}</p>{''.join(matrices)}</details>")
    for index in range(1, 36):
        case = capture / f"model-{index:02d}"
        for name in ("attempt.json", "stdout.log", "stderr.log"):
            source = case / name
            if source.exists():
                if name == "attempt.json":
                    record = json.loads(source.read_text())
                    record["command"] = [Path(arg).name if i == 0 else (Path(arg).name if Path(arg).is_absolute() else arg) for i, arg in enumerate(record.get("command", []))]
                    files[f"raw/model-{index:02d}/{name}"] = (json.dumps(record, indent=2, sort_keys=True)+"\n").encode()
                else:
                    add(source, f"raw/model-{index:02d}/{name}")
        out = case / ("source21-output" if index == 21 else "tracking-output")
        for name in ("plans.csv", "trace.csv", "refusal.json", "result.json", "run.txt"):
            source = out / name
            if source.exists():
                if name == "run.txt":
                    safe = "\n".join(line for line in source.read_text(encoding="utf-8").splitlines()
                                       if not line.startswith("source_locator=")) + "\n"
                    files[f"raw/model-{index:02d}/{name}"] = safe.encode()
                else:
                    add(source, f"raw/model-{index:02d}/{name}")
    for index in (23, 27, 28):
        ident = f"catalogue-2026/model-{index}/1"
        candidates = []
        for kind in ("A", "B", "G"):
            for row, columns in model_values[ident].get(kind, {}).items():
                for column, value in columns.items():
                    numeric = abs(float(value))
                    if numeric and numeric <= 1e-12:
                        candidates.append({"matrix":kind,"row":row,"column":column,"value":value})
        attempt = json.loads((capture / f"model-{index:02d}/attempt.json").read_text(encoding="utf-8"))
        diagnostic = (capture / f"model-{index:02d}/stderr.log").read_text(encoding="utf-8").strip()
        files[f"raw/model-{index:02d}/native-refusal.json"] = (json.dumps({
            "schema":"csl.native-model-tracking-refusal/1", "model":ident,
            "status":manifest["outcomes"][index-1]["status"], "returncode":attempt["returncode"],
            "diagnostic":diagnostic, "stderr_sha256":attempt["stderr_sha256"],
            "source_matrix_candidates_at_or_below_threshold":candidates,
            "candidate_scope":"source catalogue entries; the native error reports a coefficient in its transformed QP matrix but does not print its value"
        },indent=2,sort_keys=True)+"\n").encode()
    for name in ("independent_results.csv", "full_state_trajectory_checked.csv", "checks.json"):
        source = root / CHECKS / name
        if name == "checks.json":
            checker = json.loads(source.read_text(encoding="utf-8"))
            checker["capture"] = CAPTURE
            files["checks/"+name] = (json.dumps(checker, indent=2, sort_keys=True)+"\n").encode()
        else:
            add(source, "checks/"+name)
    figure_root = root / FIGURES / "figures"
    for source in sorted(figure_root.glob("*.svg")):
        add(source, "figures/"+source.name)

    source_commit = "635ac5ba59d230e2b09062690adc943ea6451568"
    for relative, expected in manifest["working_source_sha256"].items():
        result = subprocess.run(["git", "show", f"{source_commit}:{relative}"],
                                cwd=repository_root, capture_output=True)
        require(result.returncode == 0 and digest(result.stdout) == expected,
                "producer source commit does not match the capture bytes: "+relative)
    files["source-binding.json"] = (json.dumps({
        "schema": "csl.native-model-tracking-source-binding/1",
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "capture_source_head": manifest["code_head"],
        "producer_commit": source_commit,
        "producer_permalink": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source_commit}",
        "producer_source_sha256": manifest["working_source_sha256"],
        "supervisor_note": "This binding authenticates the committed producer bytes; the frozen captures predate this staging supervisor and were not run by it.",
    }, indent=2, sort_keys=True)+"\n").encode()
    files["README.txt"] = ("Functional native tracking evidence for 35 catalogue records. Saved outcomes include all refusals. "
        "No performance comparison or nonlinear stability claim is made. The HTML report links to raw records; this folder is self-contained.\n").encode()

    links = ''.join('<li>model %d: %s</li>' % (i, ' · '.join(
        f'<a href="raw/model-{i:02d}/{name}">{label}</a>'
        for name, label in (("attempt.json", "attempt"), ("run.txt", "task and outcome"),
                            ("plans.csv", "plans"), ("trace.csv", "executed trace"),
                            ("native-refusal.json", "typed refusal"),
                            ("stdout.log", "stdout"), ("stderr.log", "stderr"))
        if f"raw/model-{i:02d}/{name}" in files)) for i in range(1, 36))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Native model tracking · saved functional evidence</title><link rel="stylesheet" href="examples.css"><style>.matrix{{overflow:auto;max-width:100%}}.matrix table{{border-collapse:collapse;font:0.75rem monospace;white-space:nowrap}}.matrix td{{padding:.15rem .35rem;border:1px solid #8884}}details{{margin:.5rem 0}}summary{{cursor:pointer}}</style></head><body><a class="skip" href="#main">Skip to report</a><main id="main" class="page-content"><nav class="breadcrumbs" aria-label="Breadcrumb"><ol><li>Examples</li><li aria-current="page">Native model tracking</li></ol></nav><p class="eyebrow">Native C++ · functional first pass</p><h1>35 native models: matrix inputs and observed-state tracking</h1><p>This saved first pass attempted all 35 public discrete-model records. It completed 32 closed-loop cases and preserved three typed solver refusals. The objectives for 34 horizon-free records are authored educational tracking profiles; source21 keeps its literal source task. These results do not establish a cross-model performance winner, physical calibration, or nonlinear stability.</p><nav><a href="{ROUTE}.zip">Download complete evidence ZIP</a> · <a href="capture-manifest.json">Capture metadata</a> · <a href="source-binding.json">Source binding</a> · <a href="source-input-inventory.json">Input hashes</a> · <a href="https://github.com/butahlecoq/controlled-systems-lab/tree/{source_commit}">Producer source commit</a></nav><h2>Complete model inputs</h2><p>Each record below exposes its full A, B, G, affine offset, initial state and nominal external input. The matrix-first CSV preserves every exact captured numeric cell by model identity and row/column; coordinate names and units are in the companion CSV. Owner-private source locators are omitted; source labels, hashes, qualification, and time units remain.</p><p><a href="raw/models.csv">models.csv</a> · <a href="raw/catalogue.csv">catalogue.csv</a> · <a href="raw/coordinates.csv">coordinates.csv</a></p>{''.join(matrix_sections)}<h2>Saved projections</h2><p>Each available two-state model projection shows the executed path against its saved per-replan prediction. The full-state trajectory and independent dynamics/objective checks are available below and remain authoritative over these two-axis views.</p>{''.join(f'<figure><img src="figures/{Path(name).name}" alt="Saved model projection"><figcaption>{escape(Path(name).stem)}</figcaption></figure>' for name in sorted(n for n in files if n.startswith('figures/')))}<h2>Independent checks and complete trajectories</h2><ul><li><a href="checks/independent_results.csv">Per-model independent objective and dynamics results</a></li><li><a href="checks/full_state_trajectory_checked.csv">All-stage full-state replay trajectories</a></li><li><a href="checks/checks.json">Checker provenance</a></li></ul><h2>Every attempted case</h2><ul>{links}</ul><p>Raw stdout and stderr are preserved for every attempt. Plans, traces, and typed refusals are linked where the solver emitted them. The original capture manifest remains in the repository report archive; the published metadata is a location-free projection bound to its SHA-256.</p></main></body></html>'''
    files["index.html"] = page.encode()
    # Include the page and a checksum inventory in the offline bundle. The inventory excludes
    # itself and the ZIP to avoid recursive hashes; the adjacent .zip.sha256 authenticates ZIP.
    files.pop("SHA256SUMS.json", None)
    files["SHA256SUMS.json"] = (json.dumps({n: digest(b) for n, b in sorted(files.items())}, indent=2, sort_keys=True)+"\n").encode()
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    files[ROUTE+".zip"] = archive_buffer.getvalue()
    files[ROUTE+".zip.sha256"] = (digest(files[ROUTE+".zip"])+"  "+ROUTE+".zip\n").encode()
    outputs = {ROUTE+"/"+name: content for name, content in files.items()}
    figure = ROUTE+"/figures/model-21-state-3-9.svg"
    entry = {"family":"Native mathematical models", "title":"Track 35 source-catalogue models with native MPC",
             "status":"saved-data-companion", "anchor":"native-model-tracking-first-pass",
             "page":ROUTE+"/index.html", "figure":figure, "source_page":f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source_commit}",
             "raw_record":ROUTE+"/capture-manifest.json"}
    card = (f'<article class="saved-figure" id="{entry["anchor"]}"><p class="eyebrow">Native C++ · 35 model records</p>'
            f'<h3><a href="{entry["page"]}">{escape(entry["title"])}</a></h3><a href="{entry["page"]}"><img src="{figure}" alt="Source21 full-state trajectory projection in coordinates three and nine"></a>'
            '<p>Matrix-first inputs, 35 attempted cases, 32 completed runs, three retained solver refusals, and independent full-state/objective checks.</p>'
            f'<p><a href="{entry["page"]}">Open the saved report →</a> · <a href="{ROUTE}/{ROUTE}.zip">Download raw evidence</a></p></article>')
    return outputs, [entry], card
