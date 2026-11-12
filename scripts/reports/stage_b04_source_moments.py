#!/usr/bin/env python3
"""Validate and stage the exact B04 source-candidate certificate and saved figure."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "dcb1783aa16ce19799fec63c6c59b173e5e3225a"
STYLE_PATH = "scripts/reports/figure_style.py"
FROZEN_STYLE_PATH = "benchmarks/reporting/mpc11/evidence/figures-60bda0fb/source/figure_style.py"
EVIDENCE = ROOT / "docs/research/evidence"
FIGURES = EVIDENCE / "b04-source-moment-figures"
INPUT_NAME = "b04-source-moment-inputs.json"
CERT_NAME = "b04-source-moment-certificate.json"
STAGES_NAME = "b04-source-moment-stage-sets.json"
EXPORT_NAME = "figure-export.json"
SVG_NAME = "b04-all-stage-reachability.svg"
PNG_NAME = "b04-all-stage-reachability.png"
SCENARIO_IDS = {
    "commented_initial": "B04-SOURCE-COMMENTED-X0-V1",
    "active_rounded_initial": "B04-SOURCE-ACTIVE-X0-V1",
}
SOURCE_FILES = (
    "docs/research/tools/check_b04_source_moments.py",
    "scripts/reports/b04_source_moments/geometry.py",
    "scripts/reports/b04_source_moments/figures.py",
    "scripts/reports/figure_style.py",
    "benchmarks/reporting/mpc08_explicit/exact_regions.py",
    "benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py",
)
EVIDENCE_FILES = (
    f"docs/research/evidence/{INPUT_NAME}",
    f"docs/research/evidence/{CERT_NAME}",
    f"docs/research/evidence/{STAGES_NAME}",
    f"docs/research/evidence/b04-source-moment-figures/{EXPORT_NAME}",
    f"docs/research/evidence/b04-source-moment-figures/{SVG_NAME}",
    f"docs/research/evidence/b04-source-moment-figures/{PNG_NAME}",
)
SNAPSHOT_FILES = SOURCE_FILES + EVIDENCE_FILES
SNAPSHOT_DATA = {
    f"docs/research/evidence/{INPUT_NAME}": INPUT_NAME,
    f"docs/research/evidence/{CERT_NAME}": CERT_NAME,
    f"docs/research/evidence/{STAGES_NAME}": STAGES_NAME,
    f"docs/research/evidence/b04-source-moment-figures/{EXPORT_NAME}": f"figures/{EXPORT_NAME}",
    f"docs/research/evidence/b04-source-moment-figures/{SVG_NAME}": f"figures/{SVG_NAME}",
    f"docs/research/evidence/b04-source-moment-figures/{PNG_NAME}": f"figures/{PNG_NAME}",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(bool(name) and not path.is_absolute() and path.as_posix() == name and
            all(part not in ("", ".", "..") for part in path.parts), "unsafe bundle path")
    return path


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def source_bytes(repository: Path, name: str) -> bytes:
    relative = FROZEN_STYLE_PATH if name == STYLE_PATH else name
    path = repository
    for part in PurePosixPath(relative).parts:
        path = path / part
        require(not path.is_symlink(), "source snapshot must not contain symlinks: " + relative)
    return path.read_bytes()


def verify_saved_science(snapshot: dict[str, bytes]) -> None:
    """Rebuild saved provenance in its authenticated source tree, not live tools."""
    with tempfile.TemporaryDirectory(prefix="b04-source-check-") as temporary:
        root = Path(temporary)
        for name, content in snapshot.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        command = '''import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path[:0] = [str(root / "docs/research/tools"),
               str(root / "scripts/reports/b04_source_moments")]
import check_b04_source_moments as checker
import geometry
evidence = root / "docs/research/evidence"
inputs = json.loads((evidence / "b04-source-moment-inputs.json").read_bytes())
certificate = json.loads((evidence / "b04-source-moment-certificate.json").read_bytes())
stage_sets = json.loads((evidence / "b04-source-moment-stage-sets.json").read_bytes())
checker.verify_certificate(certificate, inputs)
geometry.verify_stage_sets(stage_sets, certificate)
'''
        checked = subprocess.run([sys.executable, "-I", "-B", "-c", command, str(root)],
                                 capture_output=True, text=True, timeout=60)
        require(checked.returncode == 0,
                "historical scientific recheck failed: " + checked.stderr[-2000:])


def _read_evidence(repository: Path, evidence_dir: Path) -> dict[str, bytes]:
    files = {}
    for repo_path in EVIDENCE_FILES:
        filename = Path(repo_path).name
        source = evidence_dir / filename if filename not in (EXPORT_NAME, SVG_NAME, PNG_NAME) else evidence_dir / "b04-source-moment-figures" / filename
        require(source.is_file() and not source.is_symlink(), f"missing or unsafe public evidence: {filename}")
        files[repo_path] = source.read_bytes()
    return files


def verify_source_anchor(repository: Path = ROOT, evidence_dir: Path | None = None) -> tuple[dict, dict[str, bytes]]:
    """Compare all published scientific/source inputs with Git blobs at the fixed anchor."""
    repository = Path(repository)
    evidence_dir = Path(evidence_dir) if evidence_dir else repository / "docs/research/evidence"
    resolved = subprocess.run(["git", "rev-parse", f"{SOURCE_COMMIT}^{{commit}}"], cwd=repository,
                              check=True, capture_output=True, text=True).stdout.strip()
    require(resolved == SOURCE_COMMIT, "source anchor does not resolve to the immutable full commit")
    snapshot = {**_read_evidence(repository, evidence_dir),
                **{name: source_bytes(repository, name) for name in SOURCE_FILES}}
    result = {}
    for name, data in snapshot.items():
        anchored = subprocess.run(["git", "show", f"{SOURCE_COMMIT}:{name}"], cwd=repository,
                                  check=True, capture_output=True).stdout
        require(data == anchored, f"selected source bytes differ from source-anchor Git blob: {name}")
        result[name] = {"sha256": digest(data), "git_blob_sha1": git_blob_sha1(data), "bytes": len(data)}
    return result, snapshot


def validate(repository: Path = ROOT, evidence_dir: Path | None = None) -> dict:
    repository = Path(repository)
    evidence_dir = Path(evidence_dir) if evidence_dir else repository / "docs/research/evidence"
    anchor_files, snapshot = verify_source_anchor(repository, evidence_dir)
    evidence = {name: snapshot[name] for name in EVIDENCE_FILES}
    inputs = json.loads(evidence[f"docs/research/evidence/{INPUT_NAME}"])
    certificate = json.loads(evidence[f"docs/research/evidence/{CERT_NAME}"])
    stage_sets = json.loads(evidence[f"docs/research/evidence/{STAGES_NAME}"])
    export = json.loads(evidence[f"docs/research/evidence/b04-source-moment-figures/{EXPORT_NAME}"])
    verify_saved_science(snapshot)

    cert_hash = digest(evidence[f"docs/research/evidence/{CERT_NAME}"])
    stages_hash = digest(evidence[f"docs/research/evidence/{STAGES_NAME}"])
    require(export.get("schema") == "b04.source-candidate.figure-export/1", "figure export schema differs")
    relation = export.get("source_relation", {})
    require(relation.get("source_model_sha256") == certificate.get("source_sha256"), "figure source-model binding differs")
    require(relation.get("certificate_sha256") == cert_hash, "figure certificate hash binding differs")
    require(relation.get("stage_sets_path") == f"docs/research/evidence/{STAGES_NAME}" and
            relation.get("stage_sets_sha256") == stages_hash, "figure stage-set binding differs")
    canonical_stages = hashlib.sha256(json.dumps(stage_sets, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(relation.get("verified_stage_data_canonical_sha256") == canonical_stages, "figure canonical stage-data binding differs")
    require(export.get("producer_sha256") == anchor_files["scripts/reports/b04_source_moments/figures.py"]["sha256"],
            "figure producer source hash differs")
    require(export.get("geometry_sha256") == anchor_files["scripts/reports/b04_source_moments/geometry.py"]["sha256"],
            "figure geometry source hash differs")
    require(export.get("checker_sha256") == anchor_files["docs/research/tools/check_b04_source_moments.py"]["sha256"],
            "figure checker source hash differs")
    helper = export.get("helper", {})
    require(helper.get("path") == "scripts/reports/figure_style.py" and
            helper.get("sha256") == anchor_files["scripts/reports/figure_style.py"]["sha256"],
            "figure style helper hash differs")
    outputs = {item.get("path"): item for item in export.get("outputs", [])}
    for filename, expected_name in ((SVG_NAME, SVG_NAME), (PNG_NAME, PNG_NAME)):
        data = evidence[f"docs/research/evidence/b04-source-moment-figures/{filename}"]
        item = outputs.get(expected_name)
        require(item == {"path": expected_name, "sha256": digest(data), "bytes": len(data)},
                f"saved figure export hash differs: {filename}")
    require(set(outputs) == {SVG_NAME, PNG_NAME}, "figure export contains an unexpected output inventory")

    case = certificate["commented_initial"]
    require(case.get("scenario_id") == SCENARIO_IDS["commented_initial"], "commented case ID differs")
    require(certificate["active_rounded_initial"].get("scenario_id") == SCENARIO_IDS["active_rounded_initial"],
            "active rounded case ID differs")
    require(len(case.get("interior_witness_controls", [])) == 16 and
            len(case.get("interior_witness_states", [])) == 17, "certificate witness dimensions differ")
    require(len(stage_sets.get("stages", [])) == 17, "saved stage set does not cover stages 0 through 16")
    return {"inputs": inputs, "certificate": certificate, "stage_sets": stage_sets,
            "figures": {SVG_NAME: evidence[f"docs/research/evidence/b04-source-moment-figures/{SVG_NAME}"],
                        PNG_NAME: evidence[f"docs/research/evidence/b04-source-moment-figures/{PNG_NAME}"]},
            "figure_export": export, "anchor_files": anchor_files, "source_snapshot": snapshot}


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def render_page(route: str, inputs: dict, certificate: dict, figure_export: dict) -> bytes:
    case = certificate["commented_initial"]
    active = certificate["active_rounded_initial"]
    units = inputs["model"]["state_units"]
    names = inputs["model"]["state_order"]
    witness_controls = case["interior_witness_controls"]
    witness_states = case["interior_witness_states"]
    state_rows = "".join(
        f"<tr><th>{k}</th><td>{6.25*k:g}</td>" + "".join(f"<td><code>{html.escape(v)}</code></td>" for v in state) + "</tr>"
        for k, state in enumerate(witness_states))
    control_rows = "".join(
        f"<tr><th>{k}</th><td>{6.25*k:g}–{6.25*(k+1):g}</td><td><code>{html.escape(value)}</code></td></tr>"
        for k, value in enumerate(witness_controls))
    minima = "".join(
        f"<tr><th>{html.escape(cert['scenario_id'])}</th><td><code>{html.escape(cert['minimum_squared'])}</code></td>"
        f"<td><code>{html.escape(cert['minimum_decimal'])}</code></td><td>{'inside' if all(cert['rounding_band_30_899'].values()) else 'outside'} 30.899 rounding band</td></tr>"
        for cert in (case, active))
    source = inputs["source"]
    source_note = (f"ReachableSets.m ({source['ReachableSets.m']['collection']}, SHA-256 "
                   f"{source['ReachableSets.m']['sha256']}); program.m SHA-256 {source['program.m']['sha256']}.")
    scope = html.escape(source["archive_scope"])
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>B04 source-candidate exact moment certificate</title>
<style>
:root{{--bg:#111923;--panel:#192633;--ink:#eef4f7;--muted:#b8c6cf;--line:#354b5b;--accent:#80d3ef;--green:#9ae6b4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:clamp(1rem,4vw,3rem)}}p,li{{overflow-wrap:anywhere}}h1,h2{{line-height:1.2}}h1{{font-size:clamp(2rem,5vw,3.4rem);max-width:24ch}}h2{{margin-top:2.3rem}}p,li{{max-width:88ch}}a{{color:var(--accent)}}.muted{{color:var(--muted)}}.lead{{font-size:1.16rem;color:var(--muted)}}
.card{{padding:1rem 1.25rem;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:1rem 0}}figure{{margin:1.5rem 0}}figure img{{display:block;width:100%;height:auto;background:white;border-radius:8px}}figcaption{{color:var(--muted)}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin:1rem 0}}table{{border-collapse:collapse;width:100%;min-width:680px}}th,td{{text-align:left;padding:.5rem .65rem;border-bottom:1px solid var(--line);vertical-align:top}}thead{{background:var(--panel)}}code{{overflow-wrap:anywhere;color:#f4dca3}}.pill{{color:var(--green)}}
</style></head><body><main>
<p class="muted">B04 source candidate · exact rational proof · staged from saved evidence</p>
<h1>One exact model, two source initializations, a complete optimal family</h1>
<p class="lead">This certificate solves the exact-decimal 16-step candidate model. It proves the global minimum and describes every optimal shared-control sequence under the stated control and all-stage flow bounds. Performance was not measured; objective values follow from exact rational identities, not timed archived software.</p>
<nav class="card"><a href="minimal-inputs.json">Inputs and assumptions</a> · <a href="certificate.json">Exact certificate and full family</a> · <a href="stage-sets.json">All-stage exact sets</a> · <a href="figure-export.json">Figure source and hashes</a> · <a href="publication-manifest.json">Publication manifest</a> · <a href="../{route}.zip">Complete offline ZIP</a> · <a href="README.md">Offline verification</a></nav>
<section id="minimal-example"><h2>Model and exact result</h2>
<p>State order is <code>{', '.join(names)}</code> with units <code>{', '.join(units)}</code>; time is in seconds, step <code>25/4</code>, and horizon <code>16</code>. All 16 controls are shared scalars in <code>[−1,1]</code>. Oxidizer and fuel flow bounds apply at each of all 17 state stages; stock states are unconstrained.</p>
<div class="table-wrap" role="region" aria-label="Exact minima by source initialization" tabindex="0"><table><thead><tr><th>Distinct source case</th><th>Exact minimum squared</th><th>Displayed square root</th><th>Band check</th></tr></thead><tbody>{minima}</tbody></table></div>
<p>The displayed square roots are 70-digit decimal approximations. Exact minimum-squared rationals and the exact half-open rounding-band predicate are in the certificate. The commented initialization is a source comment, not evidence that it was active in the historical run.</p></section>
<section><h2>All 17 stages in the figure</h2>
<figure><a href="figures/{SVG_NAME}"><img src="figures/{SVG_NAME}" alt="Oxidizer and fuel phase planes showing exact forward sets, backward-to-optimum sets, their intersection at all stages 0 through 16, and one exact optimal witness"></a><figcaption>Saved SVG and PNG are copied and hash-checked during staging; staging does not import Matplotlib or rerender. The plotted witness belongs to {SCENARIO_IDS['commented_initial']} and is not a recovered historical control sequence. <a href="figures/{PNG_NAME}">PNG</a>.</figcaption></figure>
<p>Each outline is a separate stage slice. The corridor is the forward/backward intersection at that stage, a projection of a coupled whole-history family; joining these slices does not remove the control-history coupling.</p></section>
<section><h2>One exact witness: 16 controls and 17 states</h2>
<p>This strict-feasibility witness proves that the two independent optimality equalities retain a 14-dimensional family under the inequalities. It is one member, not the family itself.</p>
<div class="table-wrap" role="region" aria-label="Sixteen exact witness controls" tabindex="0"><table><thead><tr><th>Control k</th><th>Time interval (s)</th><th>u[k]</th></tr></thead><tbody>{control_rows}</tbody></table></div>
<div class="table-wrap" role="region" aria-label="Seventeen exact witness states" tabindex="0"><table><thead><tr><th>Stage k</th><th>Time (s)</th>{''.join(f'<th>{html.escape(n)} ({html.escape(u)})</th>' for n,u in zip(names,units))}</tr></thead><tbody>{state_rows}</tbody></table></div></section>
<section id="complete-optimal-family"><h2>Complete 14-dimensional optimal family</h2>
<p>The concrete relation below is for <code>{SCENARIO_IDS["commented_initial"]}</code>. The certificate separately gives the corresponding relation for <code>{SCENARIO_IDS["active_rounded_initial"]}</code>, using its own initial state, moment equalities and prefix bounds.</p>
<p>Every global minimizer is exactly a control vector satisfying both moment equalities and all 64 listed halfspace inequalities. The affine equality rows are independent (columns 0 and 15 give determinant −15). Each such vector has one unique state history under the recurrence.</p>
<div class="card"><p><strong>Moment equalities</strong><br><code>Σ[k=0..15] u[k] = {html.escape(case['sum_control'])}</code><br><code>Σ[k=0..15] (15−k)u[k] = {html.escape(case['weighted_control_sum'])}</code></p>
<p><strong>Control bounds</strong> <code>−1 ≤ u[k] ≤ 1</code> for k=0,…,15.<br><strong>Prefix-flow bounds</strong> <code>{html.escape(case['prefix_bounds'][0])} ≤ Σ[j=0..k−1]u[j] ≤ {html.escape(case['prefix_bounds'][1])}</code> for k=1,…,16.</p>
<p><strong>Affine history lift</strong> <code>q_o[k]=q_o[0]+(2208/110)S[k]</code>, <code>q_f[k]=q_f[0]−(1152/110)S[k]</code>; <code>m_o[k]=m_o[0]−(25/4)(kq_o[0]+(2208/110)M[k])</code>, and <code>m_f[k]=m_f[0]−(25/4)(kq_f[0]−(1152/110)M[k])</code>, where <code>S[k]=Σ[j&lt;k]u[j]</code>, <code>M[k]=Σ[j&lt;k](k−1−j)u[j]</code>. Full 17×4 affine offsets and control matrices are saved in the certificate.</p></div>
<p>The objective square decomposes into the exact minimum squared plus two strictly positive quadratic terms in the moment residuals. Its stock quadratic includes the cross residual <code>(m_o−8m_f/3)^2</code>. Equality holds precisely at the two moment values above. This proves global optimality and family completeness for this candidate profile.</p></section>
<section><h2>Source identity and limits</h2><p>{html.escape(source_note)} The source candidate is not attributed as the historical generator. The original floating-point solver proof, historical control sequence and canonical author intent remain unknown.</p>
<p>{scope} The ZIP contains the checker, exact geometry verifier, renderer source, required helper modules, inputs, certificates, all-stage set data, and saved figure files. It excludes archived MATLAB/Pascal/FIG source and other private research files.</p>
<p class="muted">The report anchors selected repository bytes to source commit <code>{SOURCE_COMMIT}</code>. This is source provenance for the published checker/geometry/renderer and evidence artifacts, distinct from attribution of the historical numerical run.</p></section>
</main></body></html>'''
    return page.encode("utf-8")


def _offline_checker_bytes() -> bytes:
    return b'''#!/usr/bin/env python3
"""Verify the saved B04 exact certificate and stage sets without Git or plotting."""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE = HERE
ROOT = HERE / "source-root"
MANIFEST = json.loads((BUNDLE / "publication-manifest.json").read_text(encoding="utf-8"))

def require(ok, message):
    if not ok: raise ValueError(message)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

checksum_rows = {}
for line in (BUNDLE / "SHA256SUMS").read_text(encoding="ascii").splitlines():
    digest, name = line.split("  ", 1)
    require(len(digest) == 64 and name not in checksum_rows and ".." not in Path(name).parts,
            "invalid checksum inventory")
    checksum_rows[name] = digest
expected_names = set(MANIFEST["files"]) | {"publication-manifest.json"}
require(set(checksum_rows) == expected_names, "checksum inventory differs")
for rel, expected in checksum_rows.items():
    path = BUNDLE / rel
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "bundle checksum mismatch: " + rel)
for rel, expected in MANIFEST["files"].items():
    path = BUNDLE / rel
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "bundle file hash mismatch: " + rel)
for rel, entry in MANIFEST["source_anchor"]["files"].items():
    data = (ROOT / rel).read_bytes()
    require(hashlib.sha256(data).hexdigest() == entry["sha256"], "snapshot SHA-256 mismatch: " + rel)
    git_blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\\0" + data).hexdigest()
    require(git_blob == entry["git_blob_sha1"], "snapshot Git-blob identity mismatch: " + rel)

import sys
sys.path.insert(0, str(ROOT / "benchmarks/reporting/mpc08_explicit"))
sys.path.insert(0, str(ROOT / "docs/research/tools"))
checker = load("b04_source_moment_checker", ROOT / "docs/research/tools/check_b04_source_moments.py")
geometry = load("b04_source_moment_geometry", ROOT / "scripts/reports/b04_source_moments/geometry.py")
inputs = json.loads((ROOT / "docs/research/evidence/b04-source-moment-inputs.json").read_text())
certificate = json.loads((ROOT / "docs/research/evidence/b04-source-moment-certificate.json").read_text())
stage_sets = json.loads((ROOT / "docs/research/evidence/b04-source-moment-stage-sets.json").read_text())
checker.verify_certificate(certificate, inputs)
geometry.verify_stage_sets(stage_sets, certificate)
figure = json.loads((ROOT / "docs/research/evidence/b04-source-moment-figures/figure-export.json").read_text())
for output in figure["outputs"]:
    data = (ROOT / "docs/research/evidence/b04-source-moment-figures" / output["path"]).read_bytes()
    require(hashlib.sha256(data).hexdigest() == output["sha256"] and len(data) == output["bytes"],
            "figure export hash mismatch: " + output["path"])
print("B04 source-candidate certificate, 17 stage sets, and saved figure hashes verified")
'''


def _readme(route: str) -> bytes:
    return f'''# B04 exact source-candidate certificate

Open `index.html` for the result, all-stage figure, exact witness, source scope and the complete 14-dimensional optimal-family description.

This is a mathematical exact-decimal candidate certificate, not a claim that the original floating-point solver was certified or that this source revision generated the historical result. The commented and active rounded initializations remain separate cases. Archived MATLAB, Pascal and FIG files are not included.

## Offline verification

Extract `../{route}.zip` into a fresh directory, enter its report folder, and run:

```sh
sha256sum -c SHA256SUMS
python3 -B offline_check.py
```

Verification uses Python's standard library and the included source-root snapshot. It recomputes the exact certificate and all-stage geometry from saved rational inputs, then checks the saved SVG/PNG hashes. It requires no Git checkout, network, solver, Matplotlib, archive source or private file. The included renderer is provenance and is not executed.

`publication-manifest.json` records the fixed mathematical source anchor, Git blob identities for selected source/evidence bytes, the current staging-adapter hash separately, and hashes of every bundle file except the manifest and checksum list themselves. `certificate.json`, `minimal-inputs.json`, `stage-sets.json`, and `figures/` are directly inspectable.
'''.encode("utf-8")


def _insert_site_links(site: Path, route: str) -> tuple[bytes, bytes]:
    index = site / "index.html"
    gallery = site / "examples/index.html"
    require(index.is_file() and not index.is_symlink() and gallery.is_file() and not gallery.is_symlink(),
            "site indexes must be regular files")
    old_index = index.read_bytes()
    old_gallery = gallery.read_bytes()
    require(old_index.count(b"</body>") == 1 and old_gallery.count(b"</body>") == 1,
            "site index insertion points differ")
    require(route.encode() not in old_index and route.encode() not in old_gallery, "route is already linked")
    section = (f'<section id="{route}"><h2>B04 exact source-candidate certificate</h2>'
               f'<p><a href="{route}/index.html">Read the exact 16-step result and all-stage figure</a> · '
               f'<a href="{route}.zip">Download the complete offline bundle</a>.</p></section>').encode()
    card = (f'<article id="{route}-example"><h3><a href="../{route}/index.html#minimal-example">B04 exact source-candidate certificate</a></h3>'
            f'<a href="../{route}/index.html#minimal-example"><img src="../{route}/figures/{SVG_NAME}" alt="All-stage oxidizer and fuel reachability projections"></a>'
            f'<p>Exact-rational global minimum and complete 14-dimensional optimal-control family; historical run attribution remains unknown.</p>'
            f'<p><a href="../{route}.zip">Complete offline evidence bundle</a></p></article>').encode()
    return old_index.replace(b"</body>", section + b"</body>"), old_gallery.replace(b"</body>", card + b"</body>")


def stage(site: Path, *, repository: Path = ROOT, evidence_dir: Path | None = None) -> str:
    """Stage the saved public certificate and return its immutable route ID."""
    site = Path(site)
    repository = Path(repository)
    evidence_dir = Path(evidence_dir) if evidence_dir else repository / "docs/research/evidence"
    require(site.is_dir() and not site.is_symlink(), "site must be a regular directory")
    for path in (site / "index.html", site / "examples", site / "examples/index.html"):
        require(not path.is_symlink(), "symlink site destination refused")
    validation = validate(repository, evidence_dir)
    source_snapshot = validation["source_snapshot"]
    generated = {
        "minimal-inputs.json": _json_bytes(validation["inputs"]),
        "certificate.json": _json_bytes(validation["certificate"]),
        "stage-sets.json": _json_bytes(validation["stage_sets"]),
        "figure-export.json": _json_bytes(validation["figure_export"]),
        f"figures/{SVG_NAME}": validation["figures"][SVG_NAME],
        f"figures/{PNG_NAME}": validation["figures"][PNG_NAME],
        "offline_check.py": _offline_checker_bytes(),
    }
    adapter_bytes = Path(__file__).read_bytes()
    generated["adapter/stage_b04_source_moments.py"] = adapter_bytes
    with tempfile.TemporaryDirectory(prefix="b04-source-moment-stage-") as temporary:
        scratch = Path(temporary)
        snapshot_root = scratch / "source-root"
        for name, data in source_snapshot.items():
            target = snapshot_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        generated["index.html"] = render_page("pending", validation["inputs"], validation["certificate"], validation["figure_export"])
        generated["README.md"] = _readme("pending")
        generated.update({f"source-root/{name}": data for name, data in source_snapshot.items()})
        id_files = {name: digest(data) for name, data in sorted(generated.items())}
        route = "b04-source-moments-" + digest(_json_bytes({"source_anchor": SOURCE_COMMIT,
                                                             "adapter_sha256": digest(adapter_bytes),
                                                             "files": id_files}))[:20]
        generated["index.html"] = render_page(route, validation["inputs"], validation["certificate"], validation["figure_export"])
        generated["README.md"] = _readme(route)
        source_receipt = {name: {"sha256": value["sha256"], "git_blob_sha1": value["git_blob_sha1"], "bytes": value["bytes"]}
                          for name, value in validation["anchor_files"].items()}
        manifest = {
            "schema": "csl.b04-source-moments-publication/1",
            "report_id": route,
            "source_anchor": {"commit": SOURCE_COMMIT, "files": source_receipt,
                              "scope": "Selected source/evidence bytes verified against Git blobs at the immutable anchor; historical generator attribution is not implied."},
            "source_provenance": validation["inputs"]["source"],
            "adapter_provenance": {"path": "scripts/reports/stage_b04_source_moments.py",
                                   "sha256": digest(adapter_bytes), "bytes": len(adapter_bytes)},
            "historical_source_assets": {STYLE_PATH: {"snapshot_path": FROZEN_STYLE_PATH,
                                                       "sha256": digest(source_snapshot[STYLE_PATH])}},
            "figure_export": validation["figure_export"],
            "files": {name: digest(data) for name, data in sorted(generated.items())},
        }
        generated["publication-manifest.json"] = _json_bytes(manifest)
        generated["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(generated.items())).encode()
        archive_data = {}
        for name, data in generated.items():
            safe_name(name)
            archive_data[name] = data
        with zipfile.ZipFile(scratch / f"{route}.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(archive_data.items()):
                info = zipfile.ZipInfo(f"{route}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        new_index, new_gallery = _insert_site_links(site, route)
        original_index = (site / "index.html").read_bytes()
        original_gallery = (site / "examples/index.html").read_bytes()
        route_path = site / route
        zip_path = site / f"{route}.zip"
        require(not route_path.exists() and not route_path.is_symlink() and
                not zip_path.exists() and not zip_path.is_symlink(), "immutable report route already exists")
        require(not route_path.parent.is_symlink() and not zip_path.parent.is_symlink(), "symlink report parent refused")
        route_path.mkdir()
        try:
            for name, data in generated.items():
                target = route_path / safe_name(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(data)
            with zip_path.open("xb") as output:
                output.write((scratch / f"{route}.zip").read_bytes())
            (site / "index.html").write_bytes(new_index)
            (site / "examples/index.html").write_bytes(new_gallery)
        except Exception:
            shutil.rmtree(route_path, ignore_errors=True)
            zip_path.unlink(missing_ok=True)
            (site / "index.html").write_bytes(original_index)
            (site / "examples/index.html").write_bytes(original_gallery)
            raise
    return route


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, type=Path)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    try:
        print(stage(args.site, repository=args.repository, evidence_dir=args.evidence_dir))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
