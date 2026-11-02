"""Validate and stage the registered B04-C Strategy A verification report."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docs.research.tools.check_b04_c_exact_fiber import check

SOURCE = ROOT / "reports/algorithm-results/b04-c-strategy-a-verification-v1"
EXACT_RECORD = ROOT / "reports/algorithm-results/b04-c-exact-dyadic-v1/record.json"
EXACT_CHECK = ROOT / "reports/algorithm-results/b04-c-exact-dyadic-v1/verification.json"
SCENARIO_ID = "B04-c-exact-dyadic-20261102"
TEST_COMMIT = "cfe72885b4544e5b005c27395d805faec219a4fc"
TEST_NAME = "registered Strategy A publishes the compiled B04-C exact optimal family"
CI_RUN_ID = 41467988977
CI_RUN_URL = f"https://github.com/butahlecoq/controlled-systems-lab/actions/runs/{CI_RUN_ID}"
CI_SOURCE_FILES = (
    "tests/synthesis/strategy_a/strategy_tests.cpp",
    "src/synthesis/strategy_a/strategy.cpp",
    "src/synthesis/b04_c_exact_family.cpp",
    "src/synthesis/b04_c_exact_family.hpp",
    "src/registry/b04_c_exact_verifier.cpp",
    "src/registry/compiled_verifiers.cpp",
    "include/csl/synthesis/b04_c_exact_family.hpp",
    "docs/contracts/b04-c-exact-family.md",
)
FILES = (
    "README.md", "index.html", "record.json", "verification.json",
    "strategy-a-ci.json", "trajectory.svg", "SHA256SUMS", "manifest.json",
)
PUBLISHED_FILES = (
    "README.md", "index.html", "record.json", "verification.json",
    "strategy-a-ci.json", "trajectory.svg", "SHA256SUMS", "manifest.json",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha_file(path: Path) -> str:
    return digest(path.read_bytes())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path.name}")
    return value


def expected_ci_source_hashes() -> dict[str, str]:
    result = {}
    for name in CI_SOURCE_FILES:
        completed = subprocess.run(
            ["git", "show", f"{TEST_COMMIT}:{name}"], cwd=ROOT,
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result[name] = digest(completed.stdout)
    return result


def validate_ci_record(ci: dict) -> None:
    require(ci.get("schema") == "csl.b04-c-strategy-a-ci-evidence/1", "CI evidence schema differs")
    require(ci.get("scenario_id") == SCENARIO_ID, "CI scenario identity differs")
    require(ci.get("source_commit") == TEST_COMMIT, "CI source commit differs")
    run = ci.get("run")
    require(isinstance(run, dict), "CI run identity is missing")
    require(run == {
        "run_id": CI_RUN_ID,
        "url": CI_RUN_URL,
        "workflow": "Native C++20",
        "head_sha": TEST_COMMIT,
        "status": "completed",
        "conclusion": "success",
    }, "CI run is not the accepted exact-head native matrix")
    require(ci.get("claim_type") == "functional_test_not_benchmark", "CI scope must remain functional only")
    test = ci.get("test")
    require(isinstance(test, dict), "Strategy A functional-test details are missing")
    require(test.get("target") == "strategy_a_tests" and test.get("name") == TEST_NAME,
            "Strategy A test identity differs")
    required_assertions = {
        "termination_completed", "complete_optimal_family", "exact_relation_coordinates",
        "requested_representation", "objective_interval_inside_confirmation_band",
        "registered_b04_c_verifier", "full_history_membership_boundary_query",
    }
    require(set(test.get("assertions", [])) == required_assertions, "Strategy A acceptance assertions differ")
    require(ci.get("source_files") == expected_ci_source_hashes(), "CI test-source hashes differ from the exact tested commit")
    jobs = ci.get("successful_jobs")
    expected_jobs = {
        "route / route", "Linux GCC 13 / highs installed package",
        "Linux GCC 13 / core installed package",
        "Linux GCC 13 / ASan and UBSan (public modules and consumers)",
        "Release / Linux GCC 13 x64", "Release / Windows MSVC x64",
        "Release / Linux Clang 18 x64", "Native validation",
    }
    require(isinstance(jobs, list) and set(jobs) == expected_jobs,
            "exact-head native CI job inventory differs")


def validate_bundle(source: Path = SOURCE) -> dict[str, bytes]:
    require(not source.is_symlink() and source.is_dir(), "B04-C Strategy A bundle is missing or unsafe")
    actual = {path.name for path in source.iterdir() if path.is_file()}
    require(actual == set(FILES), "B04-C Strategy A bundle inventory differs")
    files = {name: (source / name).read_bytes() for name in FILES}
    require(not any(path.is_symlink() for path in source.iterdir()), "B04-C Strategy A bundle contains symlinks")

    checksums = {}
    for line in files["SHA256SUMS"].decode("ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "invalid B04-C Strategy A checksum line")
        require(match.group(2) not in checksums, "duplicate B04-C Strategy A checksum")
        checksums[match.group(2)] = match.group(1)
    expected_checksums = {name: digest(value) for name, value in files.items()
                          if name not in {"SHA256SUMS", "manifest.json"}}
    require(checksums == expected_checksums, "B04-C Strategy A SHA256SUMS mismatch")

    manifest = json.loads(files["manifest.json"])
    require(manifest.get("schema") == "csl.b04-c-strategy-a-publication-input/1",
            "B04-C Strategy A manifest schema differs")
    require(manifest.get("scenario_id") == SCENARIO_ID, "B04-C Strategy A manifest scenario differs")
    require(manifest.get("source_commit") == TEST_COMMIT, "B04-C Strategy A source commit differs")
    expected_files = {name: digest(value) for name, value in files.items()
                      if name != "manifest.json"}
    require(manifest.get("files") == expected_files, "B04-C Strategy A manifest file hashes differ")
    require(manifest.get("exact_record_sha256") == sha_file(EXACT_RECORD),
            "B04-C exact record binding differs")
    require(manifest.get("exact_check_sha256") == sha_file(EXACT_CHECK),
            "B04-C exact check binding differs")

    record = json.loads(files["record.json"])
    verify_result = check(EXACT_RECORD)
    require(record == read_json(EXACT_RECORD), "B04-C Strategy A report record differs from exact record")
    require(json.loads(files["verification.json"]) == verify_result == read_json(EXACT_CHECK),
            "independent B04-C exact check differs")
    require(record.get("scenario_id") == SCENARIO_ID, "B04-C report scenario differs")
    require(record["optimality"]["pre_registered_bands_unchanged"] == [
        "|J* - 30.899| <= 0.0005", "J* < 30.8985", "J* > 30.8995"],
        "pre-registered B04-C acceptance bands changed")
    require(record["optimality"]["band_verdict"] == "within pre-registered confirmation band",
            "B04-C acceptance-band verdict differs")
    require(record["optimal_family"]["representation"] ==
            "bounded 16-control H-polytope with an exact affine lift to the 84 state/control coordinates",
            "B04-C optimal-family representation differs")
    ci = json.loads(files["strategy-a-ci.json"])
    validate_ci_record(ci)
    require(files["index.html"].decode("utf-8") == render_report(record, ci),
            "B04-C Strategy A HTML differs from the saved result and CI evidence")
    svg = files["trajectory.svg"].decode("utf-8")
    require("Oxidizer phase plane" in svg and "x1 — oxidizer flow" in svg and
            "x2 — oxidizer stock balance" in svg and "Fuel phase plane" in svg and
            "x3 — fuel flow" in svg and "x4 — fuel stock balance" in svg,
            "B04-C trajectory figure omits a labelled phase-plane projection")
    return files


def render_report(record: dict, ci: dict) -> str:
    import html
    objective = html.escape(record["optimality"]["objective_approximation"])
    band = html.escape(record["optimality"]["band_verdict"])
    residuals = record["reachability"]["plane_residuals"]
    flow = html.escape(residuals["flow"])
    stock = html.escape(residuals["stock"])
    scenario = html.escape(record["scenario_id"])
    representation = html.escape(record["optimal_family"]["representation"])
    test_name = html.escape(ci["test"]["name"])
    run_url = html.escape(ci["run"]["url"], quote=True)
    band_rows = "".join(
        f"<tr><td><code>{html.escape(name)}</code></td><td>{html.escape(verdict)}</td></tr>"
        for name, verdict in zip(record["optimality"]["pre_registered_bands_unchanged"],
                                 [band, "not applicable", "not applicable"], strict=True))
    nonlinear_rows = "".join(
        "<tr><td>" + html.escape(row["model"]) + "</td><td><code>" +
        html.escape(row["reported_objective"]) + "</code></td><td><code>(" +
        ", ".join(html.escape(value) for value in row["terminal"]) + ")</code></td></tr>"
        for row in record["published_context"]["nonlinear_rows"])
    source_url = ("https://github.com/butahlecoq/controlled-systems-lab/blob/"
                  f"{TEST_COMMIT}/tests/synthesis/strategy_a/strategy_tests.cpp#L1869-L1893")
    code_url = f"https://github.com/butahlecoq/controlled-systems-lab/commit/{TEST_COMMIT}"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>B04-C corrected-track registered Strategy A verification</title>
<style>
:root{{color-scheme:dark;--bg:#101923;--panel:#172431;--ink:#edf4f8;--muted:#b0c0cc;--line:#324656;--accent:#74d0ee}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1100px;margin:auto;padding:clamp(1rem,4vw,3rem)}}h1,h2{{line-height:1.2}}h1{{font-size:clamp(2rem,5vw,3.3rem);max-width:22ch}}h2{{margin-top:2.5rem}}
p,li{{max-width:82ch}}a{{color:var(--accent)}}.lede,.muted{{color:var(--muted)}}.lede{{font-size:1.15rem}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem 1.25rem;margin:1rem 0}}
figure{{margin:1.5rem 0}}figure img{{display:block;width:100%;height:auto;border:1px solid var(--line);border-radius:8px}}
figcaption{{color:var(--muted)}}table{{border-collapse:collapse;max-width:900px;width:100%}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:.55rem .7rem;vertical-align:top}}code{{overflow-wrap:anywhere}}
</style></head><body><main>
<p class="muted">Corrected-track result · exact represented-dyadic record · registered Strategy A functional verification</p>
<h1>B04-C exact family: from rational certificate to Strategy A</h1>
<p class="lede">This page joins an independent exact-rational mathematical record to the compiled Strategy A prepared-request test. The CI test is functional verification; it is not a measured solver run or a performance benchmark.</p>
<div class="card"><strong>Result.</strong> The exact represented-dyadic objective is approximately <code>{objective}</code>. The complete family is represented as {representation}. The compiled Strategy A test asserts that the prepared request returned <code>completed</code> and <code>CompleteOptimalFamily</code> under the registered B04-C verifier.</div>
<h2>Pre-registered acceptance bands</h2>
<table><thead><tr><th>Band</th><th>Verdict</th></tr></thead><tbody>{band_rows}</tbody></table>
<h2>Two distinct checks</h2>
<table><thead><tr><th>Evidence</th><th>What it establishes</th></tr></thead><tbody>
<tr><td>Independent exact-rational record</td><td>Feasibility, exact KKT stationarity, convex global optimality for the represented-dyadic profile, the unchanged pre-registered bands, and the 16-dimensional control fiber with its exact affine lift.</td></tr>
<tr><td>Compiled Strategy A functional test</td><td>The prepared request completes, returns the complete optimal family with the expected 84-coordinate relation and representation, uses the registered verifier, and places its objective interval inside the confirmation band. The test also exercises a full-history membership boundary query.</td></tr>
</tbody></table>
<p>The mathematical record reports the exact corrected-track objective as approximately <code>{objective}</code>. The Strategy A test asserts the interval bounds but does not save a separate numerical run record. No timing, speedup, or performance comparison is claimed.</p>
<h2>Published-point reachability</h2>
<p>The published rounded terminal point is reachable within its coordinate-wise rounding box. The exact residuals of the two terminal-plane functionals are:</p>
<table><tbody><tr><th>Flow plane</th><td><code>{flow}</code></td></tr><tr><th>Stock plane</th><td><code>{stock}</code></td></tr></tbody></table>
<p>Reachability of the rounded point is separate from the optimality result.</p>
<h2>Full optimal family and visual example</h2>
<p>The exact record describes a bounded 16-control H-polytope with a lift into the 84 joint state/control coordinates <code>x0,...,x16,u0,...,u15</code>; the induced terminal set is a singleton. The plot shows one representative member only.</p>
<figure><img src="trajectory.svg" alt="One representative B04-C history in the oxidizer (x1,x2) and fuel (x3,x4) phase planes."><figcaption>One representative corrected-track trajectory in the two requested phase planes. Other optimal control histories can have different intermediate states.</figcaption></figure>
<h2>Model scope and historical context</h2>
<p>Scenario <code>{scenario}</code> uses the saved A39/A01/A40 family and represented-dyadic inputs. It is separate from <code>B04-historical</code> and <code>b04-reference-v1</code>, and does not reproduce a historical result. The A40 fourfold coefficient scaling retains an open unit-convention question; this run uses the archive's coefficients without endorsing a normalization.</p>
<p>The published linear objective <code>30.899</code> and the four nonlinear rows below remain immutable context. This corrected-track result explains or reproduces none of the nonlinear rows.</p>
<table><thead><tr><th>Published model row</th><th>Objective</th><th>Displayed terminal state</th></tr></thead><tbody>{nonlinear_rows}</tbody></table>
<h2>Reproduce and inspect</h2>
<ul><li><a href="record.json">Exact rational record</a></li><li><a href="verification.json">Independent exact-check result</a></li><li><a href="strategy-a-ci.json">Strategy A CI evidence and source hashes</a></li><li><a href="README.md">Reproduction notes and limitations</a></li><li><a href="manifest.json">Source evidence manifest</a></li></ul>
<p>The registered test is <code>{test_name}</code>. It ran in the <a href="{run_url}">successful exact-head Native C++20 matrix</a>; its source is at the pinned <a href="{code_url}">reviewed commit</a> (see the <a href="{source_url}">test case</a>).</p>
<p class="muted">This report contains no measured performance result. The exact mathematical record and the compiled functional test are separate evidence sources; neither is a historical reproduction.</p>
</main></body></html>
'''


def stage(source: Path, site: Path) -> str:
    files = validate_bundle(source)
    index = site / "index.html"
    page = index.read_text(encoding="utf-8")
    manifest = json.loads(files["manifest.json"])
    route_identity = {
        "source_report_id": manifest["source_report_id"],
        "files": manifest["files"],
        "exact_record_sha256": manifest["exact_record_sha256"],
        "exact_check_sha256": manifest["exact_check_sha256"],
    }
    route = "b04-c-strategy-a-" + digest(json.dumps(
        route_identity, sort_keys=True, separators=(",", ":")).encode())[:20]
    destination, archive_path = site / route, site / f"{route}.zip"
    require(not destination.exists() and not archive_path.exists(), "B04-C Pages route already exists")
    require(page.count("</body>") == 1, "report landing page insertion point differs")

    generated = {name: files[name] for name in PUBLISHED_FILES}
    local_page = generated["index.html"].decode("utf-8")
    footer = (f'<p>Immutable report <code>{route}</code> · '
              '<a href="publication-manifest.json">Publication manifest</a>.</p>')
    generated["index.html"] = local_page.replace("</main>", footer + "</main>").encode("utf-8")
    generated["SHA256SUMS"] = "".join(
        f"{digest(generated[name])}  {name}\n" for name in sorted(generated)
        if name != "SHA256SUMS").encode("ascii")
    publication_manifest = {
        "schema": "csl.b04-c-strategy-a-publication/1",
        "report_id": route,
        "scenario_id": SCENARIO_ID,
        "source_commit": TEST_COMMIT,
        "exact_record_sha256": manifest["exact_record_sha256"],
        "exact_check_sha256": manifest["exact_check_sha256"],
        "ci_run": json.loads(files["strategy-a-ci.json"])["run"],
        "source_files": manifest["files"],
        "published_files": {name: digest(value) for name, value in sorted(generated.items())},
    }
    generated["publication-manifest.json"] = json_bytes(publication_manifest)
    destination.mkdir()
    for name, value in generated.items():
        (destination / name).write_bytes(value)
    section = (f'<section><h2>B04-C registered Strategy A verification</h2>'
               f'<p>The corrected-track exact record is paired with the registered Strategy A functional test. '
               f'This is not a benchmark or historical reproduction. '
               f'<a href="{route}/index.html">Open the versioned report</a> · '
               f'<a href="{route}.zip">Download the offline report bundle</a>.</p></section>')
    index.write_text(page.replace("</body>", section + "</body>"), encoding="utf-8")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in sorted(generated.items()):
            item = zipfile.ZipInfo(f"{route}/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, value)
    return route


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))
