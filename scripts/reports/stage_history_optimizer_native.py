"""Validate and stage the saved native whole-history source-cost example."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
import zipfile
from html import escape
from pathlib import Path

import report_data
import site_design

REPORT_ID = "history-optimizer-native-2d-v1"
ROUTE = REPORT_ID + "/index.html"
FIGURE = REPORT_ID + "/history.svg"
CSV = REPORT_ID + "/history.csv"
RECORD = REPORT_ID + "/records/receipt.json"
ARCHIVE = REPORT_ID + "/" + REPORT_ID + ".zip"
BUNDLE = Path("reports/algorithm-results") / REPORT_ID
SCHEMA = "csl.history-optimizer-native-2d/1"
EXPECTED_FILES = {
    "index.html",
    "history.csv",
    "history.svg",
    "records/build.log",
    "records/CMakeCache.txt",
    "records/native-output.html",
    "records/receipt.json",
    "records/stdout.txt",
}
SOURCE_PATHS = (
    "include/csl/optimization/history_optimizer.hpp",
    "src/optimization/history_optimizer.cpp",
    "include/csl/adapters/nlp/casadi_history_optimizer.hpp",
    "src/adapters/nlp/casadi_history_optimizer.cpp",
    "include/csl/adapters/nlp/casadi_superscs_history_optimizer.hpp",
    "src/adapters/nlp/casadi_superscs_history_optimizer.cpp",
    "include/csl/optimization/history_cost.hpp",
    "src/optimization/history_cost.cpp",
    "src/synthesis/Module.cmake",
    "CMakeLists.txt",
    "tests/unit/optimization/history_optimizer_tests.cpp",
    "tests/unit/optimization/history_optimizer_casadi_tests.cpp",
    "tests/unit/optimization/history_optimizer_superscs_tests.cpp",
    "tests/installed/casadi_superscs_history_optimizer_client.cpp",
    "tests/installed/CMakeLists.txt",
    "scripts/reports/capture_history_optimizer_native.py",
    "scripts/reports/stage_history_optimizer_native.py",
    "tools/history_optimizer_2d_example.cpp",
)
LOCAL_PATH = re.compile(r"(?<!:)(?<!/)/(?:[^/\s;<>\"']+/)*[^/\s;<>\"']+")


def _safe_read(root: Path, relative: str) -> bytes:
    report_data.require(not root.is_symlink(), "history optimizer bundle root is symlinked")
    path = root
    for part in Path(relative).parts:
        path /= part
        report_data.require(
            not path.is_symlink(), "history optimizer evidence path is symlinked: " + relative
        )
    report_data.require(path.is_file(), "history optimizer evidence is missing: " + relative)
    report_data.require(
        path.resolve().is_relative_to(root.resolve()), "history optimizer evidence escapes bundle"
    )
    return path.read_bytes()


def _receipt(bundle: Path) -> dict:
    receipt = json.loads(_safe_read(bundle, "records/receipt.json"))
    report_data.require(receipt.get("schema") == SCHEMA, "history optimizer receipt schema differs")
    source = receipt.get("source_commit", "")
    binary = receipt.get("binary_sha256", "")
    report_data.require(
        re.fullmatch(r"[0-9a-f]{40}", source) is not None,
        "history optimizer source commit is not pinned",
    )
    report_data.require(
        re.fullmatch(r"[0-9a-f]{64}", binary) is not None,
        "history optimizer native binary hash is not pinned",
    )
    report_data.require(
        receipt.get("provider") == "csl.conic.superscs.history-cost@1",
        "history optimizer provider identity differs",
    )
    initialization = receipt.get("initialization", {})
    report_data.require(
        initialization.get("start_mode") == "cold_start"
        and initialization.get("backend_identity") == receipt.get("provider")
        and bool(initialization.get("start_policy"))
        and bool(initialization.get("readback_unavailable_reason")),
        "history optimizer cold-start evidence is incomplete",
    )
    report_data.require(
        receipt.get("source_objective") == "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "history optimizer authored source objective differs",
    )
    result = receipt.get("result", {})
    report_data.require(
        abs(float(result.get("source_J", float("nan"))) - 1.0) <= 1e-6,
        "history optimizer source objective is not the analytic 2D answer",
    )
    report_data.require(
        abs(float(result.get("u0", float("nan"))) - 1.0) <= 1e-5
        and abs(float(result.get("u1", float("nan"))) - 1.0) <= 1e-5,
        "history optimizer did not return the analytic 2D history",
    )
    report_data.require(
        float(result.get("maximum_history_violation", float("inf"))) <= 1e-7,
        "history optimizer full-H readback exceeds its recorded tolerance",
    )
    artifacts = receipt.get("artifacts", {})
    for field, relative in (
        ("csv_sha256", "history.csv"),
        ("figure_sha256", "history.svg"),
        ("native_html_sha256", "records/native-output.html"),
        ("stdout_sha256", "records/stdout.txt"),
        ("build_log_sha256", "records/build.log"),
        ("cmake_cache_sha256", "records/CMakeCache.txt"),
    ):
        expected = artifacts.get(field, "")
        actual = hashlib.sha256(_safe_read(bundle, relative)).hexdigest()
        report_data.require(
            expected == actual, "history optimizer receipt digest differs: " + relative
        )
    return receipt


def _page(receipt: dict) -> bytes:
    source = receipt["source_commit"]
    source_url = f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"
    example_url = (
        "https://github.com/butahlecoq/controlled-systems-lab/blob/"
        + source
        + "/tools/history_optimizer_2d_example.cpp"
    )
    figure = '<figure><img src="history.svg" alt="The actual whole-history solver trajectory reaches target (1,1), while the squared-terminal surrogate stops at (0.75,0.75)."><figcaption>Blue: the native full-history solve. Dashed orange: the distinct squared-terminal surrogate, reevaluated under the original source objective.</figcaption></figure>'
    body = [
        site_design.page_start(
            "Native whole-history source-cost optimization in 2D",
            stylesheet_href="../examples.css",
            crumbs=(
                ("Learn", "../../index.html"),
                ("Examples", "../index.html"),
                ("Whole-history source cost", ""),
            ),
        ),
        '<p class="eyebrow">Nominal optimization · native CasADi/SuperSCS result</p>',
        "<h1>Optimize the complete history under the authored source cost</h1>",
        "<p>The fixture is a two-state, two-step integrator: <code>x₀=(0,0)</code>, "
        "<code>x₁=x₀+(u₀,0)</code>, <code>x₂=x₁+(0,u₁)</code>, and "
        "<code>u₀,u₁∈[0,1]</code>. The complete canonical decision vector contains "
        "all three states and both controls.</p>",
        "<p>The authored objective is <code>J=‖x₂−(1,1)‖₂ + 0.5(|u₀|+|u₁|)</code>. "
        "For <code>a=1−u₀</code> and <code>b=1−u₁</code>, its value is "
        "<code>1+√(a²+b²)−(a+b)/2</code>. Since <code>√(a²+b²)≥(a+b)/√2</code>, "
        "the unique minimum on this fixture is <code>(u₀,u₁)=(1,1)</code> with "
        "<code>J=1</code>.</p>",
        figure,
        "<table><thead><tr><th>Candidate</th><th>u₀</th><th>u₁</th><th>Original source J</th></tr></thead><tbody>"
        f"<tr><td>Native full-history solve</td><td>{float(receipt['result']['u0']):.9g}</td>"
        f"<td>{float(receipt['result']['u1']):.9g}</td><td>{float(receipt['result']['source_J']):.9g}</td></tr>"
        "<tr><td>Squared-terminal surrogate minimizer</td><td>0.75</td><td>0.75</td><td>1.1035533906</td></tr>"
        "</tbody></table>",
        "<p>Squaring only the terminal norm changes the authored objective. The surrogate "
        "selects <code>(0.75,0.75)</code>, whose original source cost is "
        "<code>1.1035533906</code>. The native SuperSCS provider instead models each source norm "
        "separately over all history coordinates; the checked result independently "
        "reevaluates the authored <code>J</code> and the full H-relation.</p>",
        "<p>This provider uses an explicit cold start: it creates a fresh conic function "
        "without primal or dual warm-start inputs. CasADi's conic result does not expose "
        "internal initialization readbacks; the native receipt records the policy and reason: "
        f"<code>{escape(receipt['initialization']['readback_unavailable_reason'])}</code>. The "
        "core still checks the returned complete history against H and recomputes source J.</p>",
        "<h2>Saved native result</h2>",
        f"<p>Provider: <code>{escape(receipt['provider'])}</code>; binary SHA-256: "
        f"<code>{escape(receipt['binary_sha256'])}</code>; maximum full-H violation: "
        f"<code>{float(receipt['result']['maximum_history_violation']):.9g}</code>.</p>",
        '<p><a href="history.csv">Actual solver history CSV</a> · '
        '<a href="records/stdout.txt">Captured native stdout</a> · '
        '<a href="records/receipt.json">Source and result receipt</a> · '
        '<a href="records/build.log">Build log</a> · '
        f'<a href="{REPORT_ID}.zip">Offline evidence bundle</a></p>',
        "<h2>Reproduce</h2>",
        site_design.code_block(
            receipt["reproduction_command"], "Native Release build and run commands"
        ),
        f'<p>Example source: <a href="{example_url}">2D native driver at {source[:8]}</a>. '
        f'Source tree: <a href="{source_url}">{source}</a>.</p>',
        '<p class="limits">This is one two-dimensional functional demonstration with '
        "a checked local numerical candidate. The analytic derivation establishes the "
        "answer for this fixture only; it makes no global-optimality claim for general "
        "nonlinear problems, no nonlinear safety claim, and no performance comparison.</p>",
        site_design.page_end(),
    ]
    return "".join(body).encode("utf-8")


def finalize_capture(bundle: Path) -> None:
    """Add the source-bound report, hash manifest, and offline archive after a real run."""
    bundle = Path(bundle)
    receipt = _receipt(bundle)
    (bundle / "index.html").write_bytes(_page(receipt))
    files = {}
    for relative in sorted(EXPECTED_FILES):
        data = _safe_read(bundle, relative)
        files[relative] = hashlib.sha256(data).hexdigest()
    manifest = {
        "schema": SCHEMA,
        "source_commit": receipt["source_commit"],
        "binary_sha256": receipt["binary_sha256"],
        "files": files,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    (bundle / "manifest.json").write_bytes(manifest_bytes)
    archive = bundle / (REPORT_ID + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for relative in sorted((*EXPECTED_FILES, "manifest.json")):
            output.write(bundle / relative, relative)
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{archive_hash}  {archive.name}\n", encoding="ascii"
    )


def validate(bundle: Path, repository_root: Path) -> dict:
    bundle = Path(bundle)
    report_data.require(
        not bundle.is_symlink() and bundle.is_dir(),
        "native history optimizer bundle is missing or symlinked",
    )
    manifest = json.loads(_safe_read(bundle, "manifest.json"))
    receipt = _receipt(bundle)
    report_data.require(
        manifest.get("schema") == SCHEMA
        and manifest.get("source_commit") == receipt["source_commit"]
        and manifest.get("binary_sha256") == receipt["binary_sha256"],
        "native history optimizer manifest provenance differs",
    )
    source_files = receipt.get("source_files", {})
    report_data.require(
        isinstance(source_files, dict) and set(source_files) == set(SOURCE_PATHS),
        "native history optimizer source fingerprint set differs",
    )
    for relative in SOURCE_PATHS:
        blob = subprocess.run(
            ["git", "show", f"{receipt['source_commit']}:{relative}"],
            cwd=Path(repository_root).resolve(strict=True),
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        report_data.require(
            hashlib.sha256(blob).hexdigest() == source_files[relative],
            "native history optimizer Git source bytes differ: " + relative,
        )
    files = manifest.get("files")
    report_data.require(
        isinstance(files, dict) and set(files) == EXPECTED_FILES,
        "native history optimizer evidence file set differs",
    )
    for relative, expected in files.items():
        report_data.require(
            hashlib.sha256(_safe_read(bundle, relative)).hexdigest() == expected,
            "native history optimizer file digest differs: " + relative,
        )
    for relative in ("records/build.log", "records/CMakeCache.txt"):
        text = _safe_read(bundle, relative).decode("utf-8", errors="replace")
        report_data.require(
            LOCAL_PATH.search(text) is None,
            "native history optimizer evidence contains a local path: " + relative,
        )
    csv_bytes = _safe_read(bundle, "history.csv").decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(csv_bytes)))
    report_data.require(
        len(rows) >= 3 and rows[0]["series"] == "whole-history-source-J",
        "native history optimizer CSV does not retain the solved history",
    )
    archive = bundle / (REPORT_ID + ".zip")
    report_data.require(
        not archive.is_symlink() and archive.is_file(),
        "native history optimizer offline archive is missing",
    )
    with zipfile.ZipFile(archive) as saved:
        names = set(saved.namelist())
        report_data.require(
            names == EXPECTED_FILES | {"manifest.json"} and saved.testzip() is None,
            "native history optimizer archive entries differ",
        )
        for name in names:
            expected = _safe_read(bundle, name)
            report_data.require(
                saved.read(name) == expected,
                "native history optimizer archive bytes differ: " + name,
            )
            if name in {"records/build.log", "records/CMakeCache.txt"}:
                report_data.require(
                    LOCAL_PATH.search(saved.read(name).decode("utf-8", errors="replace")) is None,
                    "native history optimizer archive contains a local path: " + name,
                )
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    report_data.require(
        not checksum.is_symlink()
        and checksum.is_file()
        and checksum.read_text(encoding="ascii").split()[0]
        == hashlib.sha256(archive.read_bytes()).hexdigest(),
        "native history optimizer archive checksum differs",
    )
    return receipt


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    bundle = root / BUNDLE
    receipt = validate(bundle, root)
    outputs = {}
    for relative in sorted(
        (*EXPECTED_FILES, "manifest.json", REPORT_ID + ".zip", REPORT_ID + ".zip.sha256")
    ):
        name = f"{REPORT_ID}/{relative}"
        outputs[name] = _safe_read(bundle, relative)
    inventory = [
        {
            "family": "Nominal optimization · source-cost fidelity",
            "title": "Optimize the complete history under the original source cost",
            "status": "native-current-source-example",
            "anchor": REPORT_ID,
            "page": ROUTE,
            "figure": FIGURE,
            "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{receipt['source_commit']}",
            "raw_record": RECORD,
        }
    ]
    card = (
        f'<article class="saved-figure" id="{REPORT_ID}">'
        '<p class="eyebrow">Nominal optimization · source-cost fidelity</p>'
        f'<h3><a href="{ROUTE}">Optimize the complete history under the original source cost</a></h3>'
        f'<a href="{ROUTE}"><img src="{FIGURE}" alt="Actual native full-history source-cost solve compared with a squared-terminal surrogate in two state coordinates."></a>'
        "<p>A native CasADi/SuperSCS solve over all state and control coordinates, with "
        "separate source-norm epigraphs and an independent source-J and full-H readback.</p>"
        f'<p><a href="{ROUTE}">Read the inputs and checked answer →</a> · '
        f'<a href="{ARCHIVE}">Offline evidence bundle</a> · '
        f'<a href="{RECORD}">Raw source and result receipt</a></p></article>'
    )
    return outputs, inventory, card
