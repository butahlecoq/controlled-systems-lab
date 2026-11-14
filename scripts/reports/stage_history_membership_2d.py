"""Validate and stage the source-pinned typed-membership 2D example."""

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

REPORT_ID = "history-membership-zonotope-2d-v1"
ROUTE = REPORT_ID + "/index.html"
FIGURE = REPORT_ID + "/history.svg"
CSV = REPORT_ID + "/history.csv"
RECORD = REPORT_ID + "/records/receipt.json"
ARCHIVE = REPORT_ID + "/" + REPORT_ID + ".zip"
BUNDLE = Path("reports/algorithm-results") / REPORT_ID
SCHEMA = "csl.history-membership-zonotope-2d/1"
ABSOLUTE_PATH = re.compile(
    r"(?<![:/A-Za-z0-9])/(?:home|tmp|workspace(?:s)?|__w|Users|root|mnt|opt|usr|var)/"
    r"[^\s<>\"']*|(?<![A-Za-z0-9])[A-Za-z]:\\(?:[^\\\s<>\"']+\\)*"
    r"[^\\\s<>\"']*"
)
EXPECTED_FILES = {
    "index.html",
    "history.csv",
    "history.svg",
    "records/build.log",
    "records/build-configuration.json",
    "records/native-output.html",
    "records/receipt.json",
    "records/stdout.txt",
}
SOURCE_PATHS = (
    "CMakeLists.txt",
    "include/csl/optimization/history_domain.hpp",
    "include/csl/optimization/history_optimizer.hpp",
    "src/optimization/history_domain.cpp",
    "src/optimization/history_optimizer.cpp",
    "include/csl/adapters/nlp/casadi_history_optimizer.hpp",
    "src/adapters/nlp/casadi_history_optimizer.cpp",
    "src/synthesis/Module.cmake",
    "tools/history_membership_2d_example.cpp",
    "scripts/reports/capture_history_membership_2d.py",
    "scripts/reports/stage_history_membership_2d.py",
)


def _read(root: Path, relative: str) -> bytes:
    report_data.require(not root.is_symlink(), "membership report root is symlinked")
    path = root
    for part in Path(relative).parts:
        path /= part
        report_data.require(
            not path.is_symlink(), "membership evidence path is symlinked: " + relative
        )
    report_data.require(path.is_file(), "membership evidence is missing: " + relative)
    report_data.require(
        path.resolve().is_relative_to(root.resolve()), "membership evidence escapes bundle"
    )
    return path.read_bytes()


def _require_public_text(relative: str, content: str) -> None:
    report_data.require(
        ABSOLUTE_PATH.search(content) is None,
        "public membership evidence contains a local path: " + relative,
    )


def _receipt(bundle: Path) -> dict:
    receipt = json.loads(_read(bundle, "records/receipt.json"))
    for relative in EXPECTED_FILES:
        if relative == "index.html" and not (bundle / relative).exists():
            continue
        _require_public_text(relative, _read(bundle, relative).decode("utf-8"))
    report_data.require(receipt.get("schema") == SCHEMA, "membership receipt schema differs")
    source = receipt.get("source_commit", "")
    report_data.require(
        re.fullmatch(r"[0-9a-f]{40}", source) is not None, "membership source commit is not pinned"
    )
    report_data.require(
        re.fullmatch(r"[0-9a-f]{64}", receipt.get("binary_sha256", "")) is not None,
        "membership binary hash is not pinned",
    )
    report_data.require(
        receipt.get("provider") == "csl.nlp.casadi-ipopt.history-cost@1",
        "membership provider identity differs",
    )
    build_identity = json.loads(_read(bundle, "records/build-configuration.json"))
    report_data.require(
        build_identity == receipt.get("build_identity")
        and build_identity.get("schema") == "csl.history-membership-build-identity/1"
        and build_identity.get("source_commit") == source
        and build_identity.get("source_root_matches_checkout") is True
        and build_identity.get("casadi_enabled") is True
        and build_identity.get("casadi_version")
        and build_identity.get("example_enabled") is True
        and build_identity.get("build_type") == "Release"
        and build_identity.get("compiler", {}).get("id")
        and build_identity.get("compiler", {}).get("version"),
        "verified source-matched build identity differs",
    )
    expected_stdout_prefix = (
        f"source_commit={source}; compiler={build_identity['compiler']['id']}"
        f"-{build_identity['compiler']['version']}; "
        f"casadi_version={build_identity['casadi_version']}; provider={receipt['provider']};"
    )
    report_data.require(
        _read(bundle, "records/stdout.txt").decode("utf-8").startswith(expected_stdout_prefix),
        "native stdout source/compiler identity differs from its build receipt",
    )
    report_data.require(
        receipt.get("source_objective") == "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "membership source objective differs",
    )
    membership = receipt.get("selected_membership", {})
    report_data.require(
        membership
        == {
            "stage": 1,
            "family": "zonotope",
            "center": [0.4, 0.0],
            "generator_matrix_rows": [[0.2], [0.0]],
            "coefficient_bounds": [-1.0, 1.0],
            "source_geometry_identity": "source-stage-1-zonotope",
        },
        "selected membership geometry differs from the source-pinned case",
    )
    result = receipt.get("result", {})
    reference = receipt.get("analytic_reference", {})
    for key in ("u0", "u1", "source_J"):
        report_data.require(
            abs(float(result.get(key, float("nan"))) - float(reference.get(key, float("inf"))))
            <= 1e-5,
            "membership result differs from independent analytic reference: " + key,
        )
    report_data.require(
        abs(float(result.get("x1", [float("nan")])[0]) - float(result.get("u0", float("nan"))))
        <= 1e-5
        and abs(float(result.get("x1", [0.0, float("nan")])[1])) <= 1e-6
        and abs(float(result.get("x2", [float("nan")])[0]) - float(result.get("u0", float("nan"))))
        <= 1e-5
        and abs(
            float(result.get("x2", [0.0, float("nan")])[1]) - float(result.get("u1", float("nan")))
        )
        <= 1e-5,
        "membership trajectory does not satisfy the integrator equations",
    )
    report_data.require(
        abs(float(result.get("membership_coefficients", [float("nan")])[0]) - 1.0) <= 1e-5
        and receipt.get("initialization", {}).get("primal_readback_matches") is True
        and float(result.get("maximum_history_violation", float("inf"))) <= 1e-7,
        "membership witness or full-history/start readback check failed",
    )
    artifacts = receipt.get("artifacts", {})
    for name, relative in (
        ("history.csv", "history.csv"),
        ("history.svg", "history.svg"),
        ("records/stdout.txt", "records/stdout.txt"),
        ("records/build.log", "records/build.log"),
        ("records/build-configuration.json", "records/build-configuration.json"),
        ("records/native-output.html", "records/native-output.html"),
    ):
        report_data.require(
            artifacts.get(name) == hashlib.sha256(_read(bundle, relative)).hexdigest(),
            "membership artifact hash differs: " + relative,
        )
    return receipt


def _page(receipt: dict) -> bytes:
    source = receipt["source_commit"]
    source_url = f"https://github.com/butahlecoq/controlled-systems-lab/tree/{source}"
    example_url = f"https://github.com/butahlecoq/controlled-systems-lab/blob/{source}/tools/history_membership_2d_example.cpp"
    result = receipt["result"]
    figure = '<figure><img src="history.svg" alt="Rank-one stage-1 zonotope segment and the actual optimized state trajectory from initial to terminal state"><figcaption>Orange: the selected rank-one zonotope for the intermediate state. Blue: the solver-returned full state history. Green: the terminal state.</figcaption></figure>'
    body = [
        site_design.page_start(
            "Typed stage membership in 2D",
            stylesheet_href="../examples.css",
            crumbs=(
                ("Learn", "../../index.html"),
                ("Examples", "../index.html"),
                ("History membership", ""),
            ),
        ),
        '<p class="eyebrow">Whole-history optimization · typed zonotope membership</p>',
        "<h1>Constrain an intermediate state to a zonotope</h1>",
        "<p>The two-state, two-step integrator is <code>x₀=(0,0)</code>, "
        "<code>x₁=x₀+(u₀,0)</code>, <code>x₂=x₁+(0,u₁)</code>, with "
        "<code>0≤u₀,u₁≤1</code>. The full H relation remains in the optimization. At "
        "stage 1, the selected state must also satisfy the typed membership "
        "<code>x₁ = c + Gλ</code>, where the column vectors are:</p>",
        '<p class="math"><code>c = [0.4; 0], &nbsp; G = [0.2; 0], &nbsp; −1 ≤ λ ≤ 1.</code></p>',
        figure,
        "<p>The authored source objective is "
        "<code>J=‖x₂−(1,1)‖₂+0.5(|u₀|+|u₁|)</code>. The selected region forces "
        "<code>u₀∈[0.2,0.6]</code>. Writing <code>a=1−u₀</code> and "
        "<code>b=1−u₁</code> gives <code>J=1+√(a²+b²)−(a+b)/2</code>; its minimum "
        "on this domain is <code>a=0.4</code>, <code>b=a/√3</code>.</p>",
        "<h2>Native result and independent checks</h2>",
        "<table><thead><tr><th>Quantity</th><th>Solver result</th><th>Analytic reference</th></tr></thead><tbody>"
        f"<tr><td>u₀</td><td>{float(result['u0']):.10g}</td><td>0.6</td></tr>"
        f"<tr><td>u₁</td><td>{float(result['u1']):.10g}</td><td>{float(receipt['analytic_reference']['u1']):.10g}</td></tr>"
        f"<tr><td>J</td><td>{float(result['source_J']):.10g}</td><td>{float(receipt['analytic_reference']['source_J']):.10g}</td></tr>"
        f"<tr><td>x₁</td><td>({float(result['x1'][0]):.10g}, {float(result['x1'][1]):.10g})</td><td>(u₀,0)</td></tr>"
        f"<tr><td>x₂</td><td>({float(result['x2'][0]):.10g}, {float(result['x2'][1]):.10g})</td><td>(u₀,u₁)</td></tr>"
        f"<tr><td>Membership λ</td><td>{float(result['membership_coefficients'][0]):.10g}</td><td>−1≤λ≤1</td></tr>"
        f"<tr><td>Full-H maximum violation</td><td>{float(result['maximum_history_violation']):.4g}</td><td>≤1e−7</td></tr>"
        '<tr><td>Supplied-start primal readback</td><td colspan="2">Matches</td></tr></tbody></table>',
        f"<p>Backend: <code>{escape(receipt['provider'])}</code>; binary SHA-256: "
        f"<code>{escape(receipt['binary_sha256'])}</code>; source commit: "
        f"<code>{source}</code>.</p>",
        '<p><a href="history.csv">Actual state/control history and membership witness</a> · '
        '<a href="records/stdout.txt">Native stdout</a> · '
        '<a href="records/receipt.json">Pinned source/result receipt</a> · '
        '<a href="records/build.log">Normalized build receipt</a> · '
        '<a href="records/build-configuration.json">Verified build configuration</a> · '
        f'<a href="{REPORT_ID}.zip">Offline evidence bundle</a></p>',
        "<h2>Reproduce</h2>",
        site_design.code_block(
            receipt["reproduction_command"], "Build and run the native IPOPT example"
        ),
        f'<p>Example source: <a href="{example_url}">C++ driver at {source[:8]}</a>. '
        f'Source tree: <a href="{source_url}">{source}</a>.</p>',
        '<p class="limits">This is a functional local numerical example for one 2D integrator and one selected zonotope. The analytic derivation establishes the optimum only for this fixture. Membership does not prove a source-set inclusion relation or global optimality for general nonlinear problems. No performance comparison is claimed.</p>',
        site_design.page_end(),
    ]
    return "".join(body).encode("utf-8")


def finalize_capture(bundle: Path) -> None:
    receipt = _receipt(Path(bundle))
    (bundle / "index.html").write_bytes(_page(receipt))
    files = {
        name: hashlib.sha256(_read(bundle, name)).hexdigest() for name in sorted(EXPECTED_FILES)
    }
    manifest = {
        "schema": SCHEMA,
        "source_commit": receipt["source_commit"],
        "binary_sha256": receipt["binary_sha256"],
        "files": files,
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    archive = bundle / (REPORT_ID + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name in sorted(EXPECTED_FILES | {"manifest.json"}):
            output.write(bundle / name, name)
    (bundle / (REPORT_ID + ".zip.sha256")).write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="ascii"
    )


def validate(bundle: Path, repository_root: Path) -> dict:
    bundle = Path(bundle)
    report_data.require(
        not bundle.is_symlink() and bundle.is_dir(), "membership bundle is missing or symlinked"
    )
    manifest = json.loads(_read(bundle, "manifest.json"))
    receipt = _receipt(bundle)
    report_data.require(
        manifest.get("schema") == SCHEMA
        and manifest.get("source_commit") == receipt["source_commit"]
        and manifest.get("binary_sha256") == receipt["binary_sha256"],
        "membership manifest provenance differs",
    )
    report_data.require(
        set(manifest.get("files", {})) == EXPECTED_FILES, "membership file manifest differs"
    )
    for relative in SOURCE_PATHS:
        blob = subprocess.run(
            ["git", "show", f"{receipt['source_commit']}:{relative}"],
            cwd=Path(repository_root).resolve(strict=True),
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        report_data.require(
            hashlib.sha256(blob).hexdigest() == receipt["source_files"].get(relative),
            "membership source fingerprint differs: " + relative,
        )
    for relative, expected in manifest["files"].items():
        report_data.require(
            hashlib.sha256(_read(bundle, relative)).hexdigest() == expected,
            "membership file hash differs: " + relative,
        )
    rows = list(csv.DictReader(io.StringIO(_read(bundle, "history.csv").decode("utf-8"))))
    report_data.require(
        len(rows) >= 5
        and any(row["series"] == "optimized" for row in rows)
        and any(row["series"] == "selected-zonotope" for row in rows),
        "membership CSV does not contain history and selected-region endpoints",
    )
    archive = bundle / (REPORT_ID + ".zip")
    report_data.require(
        archive.is_file() and not archive.is_symlink(), "membership offline archive is missing"
    )
    with zipfile.ZipFile(archive) as saved:
        report_data.require(
            set(saved.namelist()) == EXPECTED_FILES | {"manifest.json"} and saved.testzip() is None,
            "membership archive entries or CRC differ",
        )
        for name in saved.namelist():
            report_data.require(
                saved.read(name) == _read(bundle, name), "membership archived file differs: " + name
            )
    checksum = _read(bundle, REPORT_ID + ".zip.sha256").decode("ascii").split()
    report_data.require(
        checksum[0] == hashlib.sha256(archive.read_bytes()).hexdigest(),
        "membership archive checksum differs",
    )
    return receipt


def build(repository_root: Path) -> tuple[dict[str, bytes], list[dict[str, str]], str]:
    root = Path(repository_root)
    bundle = root / BUNDLE
    receipt = validate(bundle, root)
    outputs = {}
    for relative in sorted(
        EXPECTED_FILES | {"manifest.json", REPORT_ID + ".zip", REPORT_ID + ".zip.sha256"}
    ):
        outputs[f"{REPORT_ID}/{relative}"] = _read(bundle, relative)
    inventory = [
        {
            "family": "Nominal optimization · typed set membership",
            "title": "Constrain an intermediate 2D state to a zonotope",
            "status": "native-current-source-example",
            "anchor": REPORT_ID,
            "page": ROUTE,
            "figure": FIGURE,
            "source_page": f"https://github.com/butahlecoq/controlled-systems-lab/tree/{receipt['source_commit']}",
            "raw_record": RECORD,
        }
    ]
    card = (
        f'<article class="saved-figure" id="{REPORT_ID}"><p class="eyebrow">'
        "Whole-history optimization · typed membership</p>"
        f'<h3><a href="{ROUTE}">Constrain an intermediate 2D state to a zonotope</a></h3>'
        f'<a href="{ROUTE}"><img src="{FIGURE}" alt="Selected stage-one zonotope and actual optimized state trajectory"></a>'
        "<p>A native full-history IPOPT solve with an independently checked rank-one zonotope witness and original H relation.</p>"
        f'<p><a href="{ROUTE}">Inputs, answer and reproduction ↗</a> · <a href="{ARCHIVE}">Offline evidence bundle</a></p></article>'
    )
    return outputs, inventory, card
