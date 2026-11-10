#!/usr/bin/env python3
"""Capture and verify immutable BTULSHOR comparison bundles.

Capture is intentionally separate from the native algorithms. It executes an
already-built comparison driver in fresh processes and stores its stdout bytes
before adding independent exact-check annotations to derived records.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from fractions import Fraction
from pathlib import Path, PurePosixPath

REPORT_ID = "btulshor-source-faithful-20261110-v1"
SOURCE_SHA256 = "06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442"
SUMMARY_SCHEMA = "csl.btulshor-summary/1"
COMPARISON_SCHEMA = "csl.btulshor-comparison/1"
METHODS = (
    "csl.legacy.btulshor.kpabep.source-v1",
    "csl.geometry.quickhull-2d",
    "csl.hull.lp-membership",
    "csl.hull.itis17.a43-artificial-basis",
    "csl.hull.itis17.a43-largest-norm-tie",
    "csl.hull.itis17.a44-paper-farthest-incremental-lp",
)
FIXTURES = (
    ("custom-square-point-classes", [[0, 0], [2, 0], [2, 2], [0, 2], [1, 1], [1, 0], [0, 0]]),
    ("custom-a43-tie-rule", [[1, 0], [0, 1], [-1, 0], [0, -1], [0, 0], [2, -1]]),
    ("square", None), ("interior", None), ("edge", None), ("duplicate", None),
    ("seeded-cloud", None), ("near-tolerance", None), ("simplex-3d", None), ("simplex-4d", None),
)
REPO_SOURCES = (
    "include/csl/geometry/legacy_btulshor.hpp",
    "src/geometry/legacy_btulshor.cpp",
    "benchmarks/reporting/btulshor/driver.cpp",
    "scripts/reports/btulshor/render.py",
    "scripts/reports/btulshor/capture.py",
    "scripts/reports/figure_style.py",
    "docs/research/tools/check_btulshor_hulls.py",
)

OFFLINE_CHECK_SOURCE = b'''#!/usr/bin/env python3
"""Verify an extracted BTULSHOR bundle using only Python's standard library."""
import hashlib, json, re, sys, zipfile
from pathlib import Path, PurePosixPath

REPORT_ID = "btulshor-source-faithful-20261110-v1"
ROOT = Path(__file__).resolve().parent
def fail(message): raise SystemExit("BTULSHOR bundle check failed: " + message)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
try:
    manifest_path, sums_path = ROOT / "manifest.json", ROOT / "SHA256SUMS"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.btulshor-source-faithful-bundle/1": fail("unknown manifest schema")
    if manifest.get("source_sha256") != "06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442": fail("source hash differs")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("capture_source_commit", "")): fail("invalid source commit")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files: fail("empty file inventory")
    sums = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match.group(2) in sums: fail("malformed checksums")
        sums[match.group(2)] = match.group(1)
    expected = set(files) | {"manifest.json"}
    if set(sums) != expected: fail("checksum inventory differs")
    for name, value in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts: fail("unsafe manifest path")
        candidate = ROOT.joinpath(*path.parts)
        if candidate.is_symlink() or not candidate.is_file() or digest(candidate) != value or sums[name] != value:
            fail("hash mismatch: " + name)
    if digest(manifest_path) != sums["manifest.json"]: fail("manifest hash mismatch")
    allowed = expected | {"SHA256SUMS", REPORT_ID + ".zip", "report-envelope.json", "publication-manifest.json"}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in ROOT.rglob("*")) or actual - allowed: fail("unlisted or unsafe bundle files")
    for required in ("index.html", "point-projections.svg", "offline_check.py", "raw/summary.json"):
        if required not in files: fail("missing required file: " + required)
    summary = json.loads((ROOT / "raw/summary.json").read_text(encoding="utf-8"))
    if summary.get("schema") != "csl.btulshor-summary/1": fail("unknown summary schema")
    for name in files:
        if name == "raw/oracle-differential.json":
            receipt = json.loads((ROOT / name).read_text(encoding="utf-8"))
            if receipt.get("source_sha256") != manifest.get("source_sha256") or receipt.get("driver_sha256") != summary.get("driver_sha256"):
                fail("oracle receipt source or driver identity differs")
            continue
        if not name.startswith("raw/") or not name.endswith(".json") or name == "raw/summary.json": continue
        document = json.loads((ROOT / name).read_text(encoding="utf-8"))
        if document.get("schema") != "csl.btulshor-comparison/1": fail("unknown raw comparison schema")
        for provider in document.get("providers", []):
            if not isinstance(provider.get("status"), str): fail("provider status missing")
            check = provider.get("exact_check")
            if check is not None and check.get("status") not in {"verified", "rejected", "inconclusive", "not_applicable"}:
                fail("unknown exact-check status")
    archive = ROOT / (REPORT_ID + ".zip")
    if archive.exists():
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if len(names) != len(set(names)): fail("duplicate archive entries")
            for name in names:
                if not name.startswith(REPORT_ID + "/"): fail("archive path outside report prefix")
                rel = name[len(REPORT_ID) + 1:]
                if rel not in expected | {"SHA256SUMS"}: fail("unexpected archive entry")
                if zf.read(name) != (ROOT / rel).read_bytes(): fail("archive bytes differ: " + rel)
except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
    fail(str(exc))
print("verified")
'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def exact_geometry(points: list[list[float]]) -> tuple[list[int], list[str]]:
    """Return display-only monotone-chain boundary and full-input point classes."""
    if not points or any(len(p) != 2 for p in points):
        raise ValueError("display geometry requires nonempty 2D points")
    coords = [(Fraction.from_float(float(p[0])), Fraction.from_float(float(p[1]))) for p in points]
    unique = sorted(set(coords))
    def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    if len(unique) <= 1:
        hull = unique
    else:
        lower = []
        for p in unique:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0: lower.pop()
            lower.append(p)
        upper = []
        for p in reversed(unique):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0: upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
    boundary = [next(i for i, c in enumerate(coords) if c == p) for p in hull]
    first = {}
    classes = []
    for i, p in enumerate(coords):
        if p in first:
            classes.append("duplicate")
        else:
            first[p] = i
            classes.append("pending")
    hull_set = set(hull)
    for i, p in enumerate(coords):
        if classes[i] == "duplicate": continue
        if p in hull_set:
            classes[i] = "vertex"
        elif len(hull) >= 2 and any(cross(hull[j], hull[(j+1) % len(hull)], p) == 0 and
                min(hull[j][0], hull[(j+1) % len(hull)][0]) <= p[0] <= max(hull[j][0], hull[(j+1) % len(hull)][0]) and
                min(hull[j][1], hull[(j+1) % len(hull)][1]) <= p[1] <= max(hull[j][1], hull[(j+1) % len(hull)][1])
                for j in range(len(hull))):
            classes[i] = "edge"
        else:
            classes[i] = "interior"
    return boundary, classes


def git_identity(root: Path) -> tuple[str, bool]:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                                check=True, capture_output=True, text=True).stdout.strip())
    return head, dirty


def load_checker(root: Path):
    path = root / "docs/research/tools/check_btulshor_hulls.py"
    spec = importlib.util.spec_from_file_location("btulshor_exact_checker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.check_hull


def _annotate(document: dict, check_hull) -> dict:
    points = document.get("input_points")
    if not isinstance(points, list) or document.get("input_count") != len(points):
        raise ValueError("driver input_points/input_count mismatch")
    document = json.loads(json.dumps(document))
    if document.get("dimension") == 2:
        boundary, classes = exact_geometry(points)
        document["point_classes"] = classes
    else:
        boundary = None
    for provider in document.get("providers", []):
        indices = provider.get("retained_indices")
        if isinstance(indices, list) and all(isinstance(i, int) and not isinstance(i, bool) and
                                            0 <= i < len(points) for i in indices):
            retained_points = provider.get("retained_points")
            if retained_points is not None and retained_points:
                if len(retained_points) != len(indices) or retained_points != [points[i] for i in indices]:
                    raise ValueError(f"{provider.get('method_id')} retained_points disagree with source indices")
            provider["exact_check"] = check_hull(points, indices)
        else:
            provider["exact_check"] = {"status": "inconclusive", "hull_equal": None,
                "irredundancy": None, "reason": "raw output has no valid retained source indices"}
        if provider.get("method_id") == METHODS[0] and boundary is not None:
            provider["display_boundary_indices"] = boundary
    return document


def _read_provenance(run: dict, expected_commit: str) -> dict:
    if run.get("schema") != COMPARISON_SCHEMA or not isinstance(run.get("provenance"), dict):
        raise ValueError("driver emitted an unknown comparison schema or missing provenance")
    provenance = run["provenance"]
    for key in ("source_commit", "compiler_id", "compiler_version", "build_config"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ValueError(f"driver provenance missing {key}")
    if provenance["source_commit"] != expected_commit:
        raise ValueError("compiled driver source_commit does not match clean capture HEAD")
    if provenance["build_config"] != "Release":
        raise ValueError("capture requires a Release comparison driver")
    return provenance


def _host_metadata() -> dict:
    values = {"os": platform.platform(), "kernel": platform.release(),
              "architecture": platform.machine(), "logical_cpu_count": os.cpu_count(),
              "python_version": platform.python_version()}
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="replace")
        values["cpu_model"] = next((line.split(":", 1)[1].strip() for line in cpuinfo.splitlines()
                                     if line.lower().startswith(("model name", "hardware")) and ":" in line),
                                    "unavailable")
        meminfo = Path("/proc/meminfo").read_text(errors="replace")
        values["memory_total_kib"] = next((int(line.split()[1]) for line in meminfo.splitlines()
                                           if line.startswith("MemTotal:")), None)
    except OSError:
        values["proc_hardware_metadata"] = {"status": "unavailable", "reason": "/proc not available"}
    try:
        values["load_average_1_5_15"] = list(os.getloadavg())
    except (AttributeError, OSError):
        values["load_average_1_5_15"] = {"status": "unavailable", "reason": "platform does not expose load average"}
    values["requested_backend_threads"] = 1
    values["requested_parallelism"] = "off"
    values["backend_thread_policy_source"] = "src/adapters/highs_session.hpp"
    values["observed_native_workers"] = {"status": "unavailable", "reason": "driver does not expose native worker count"}
    return values


def _invoke(driver: Path, input_path: Path, stdout_path: Path, stderr_path: Path) -> tuple[dict, dict]:
    start = time.perf_counter_ns()
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        child = subprocess.Popen([str(driver), "--run", str(input_path)], stdout=out, stderr=err)
        usage = None
        try:
            import resource
            pid, status, usage = os.wait4(child.pid, 0)
            child.returncode = os.waitstatus_to_exitcode(status)
        except (ImportError, AttributeError):
            child.wait()
        end = time.perf_counter_ns()
    stdout_bytes = stdout_path.read_bytes()
    if child.returncode != 0:
        raise RuntimeError(f"driver failed ({child.returncode}); see private failed capture directory {stderr_path.parent}")
    try:
        result = json.loads(stdout_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("driver stdout is not valid JSON") from exc
    external = {"elapsed_ns": end-start, "rss_process_lifetime_including_spawn": None,
                "rss_units": "bytes", "rss_status": "unavailable"}
    if usage is not None:
        rss = int(usage.ru_maxrss * (1024 if sys.platform != "darwin" else 1))
        external.update(rss_process_lifetime_including_spawn=rss, rss_status="measured",
                        user_cpu_seconds=usage.ru_utime, system_cpu_seconds=usage.ru_stime)
    return result, external


def _provider_order(document: dict) -> list[str]:
    ids = [p.get("method_id") for p in document.get("providers", [])]
    if len(ids) != len(METHODS) or set(ids) != set(METHODS):
        raise ValueError("comparison driver did not return exactly the six registered providers")
    return ids


def capture(driver: Path, output: Path, *, render_python: Path | None = None,
            oracle_receipt: Path | None = None) -> None:
    root = Path(__file__).resolve().parents[3]
    if output.exists():
        raise FileExistsError(f"immutable output already exists: {output}")
    head, dirty = git_identity(root)
    if dirty:
        raise ValueError("tracked source tree must be clean before capture")
    if not driver.is_file() or not os.access(driver, os.X_OK):
        raise ValueError("--driver must name an executable comparison driver")
    if not output.parent.is_dir():
        raise ValueError("output parent directory must already exist")
    for source in REPO_SOURCES:
        if not (root / source).is_file(): raise ValueError(f"required public source is missing: {source}")
    source_hashes = {name: sha256((root / name).read_bytes()) for name in REPO_SOURCES}
    if oracle_receipt:
        receipt = json.loads(oracle_receipt.read_text(encoding="utf-8"))
        if receipt.get("source_sha256") != SOURCE_SHA256 or receipt.get("driver_sha256") != sha256(driver.read_bytes()):
            raise ValueError("oracle receipt source or driver hash mismatch")
    temp = Path(tempfile.mkdtemp(prefix=f".{REPORT_ID}.capture-", dir=output.parent))
    (temp / "input").mkdir(); (temp / "raw/runs").mkdir(parents=True); (temp / "raw").mkdir(exist_ok=True); (temp / "source").mkdir()
    (temp / ".private").mkdir()
    try:
        checker = load_checker(root)
        baseline = None
        summary = {"schema": SUMMARY_SCHEMA, "source_commit": head, "sample_count_per_fixture": 5,
                   "fixture_ids": [x[0] for x in FIXTURES], "method_ids": list(METHODS),
                   "comparison_files": {}, "method_statuses": {}, "exact_checks": {},
                   "elapsed_ns_samples": {}, "driver_runs": [], "host": _host_metadata(),
                   "limiter_profile": {"status": "not_collected", "comparison_verdict": "inconclusive"}}
        for fixture_id, custom_points in FIXTURES:
            annotated_runs = []
            fixture_directory = temp / "raw/runs" / fixture_id
            fixture_directory.mkdir()
            for sample, reverse in enumerate((False, True, False, True, False), start=1):
                request = {"fixture_id": fixture_id, "reverse_order": reverse}
                if custom_points is not None: request["points"] = custom_points
                input_bytes = canonical(request)
                input_path = temp / "input" / f"{fixture_id}-r{sample}.json"
                input_path.write_bytes(input_bytes)
                stdout_path = fixture_directory / f"{fixture_id}-r{sample}.json"
                stderr_path = temp / ".private" / f"{fixture_id}-r{sample}.stderr"
                try:
                    raw, external = _invoke(driver, input_path, stdout_path, stderr_path)
                    if raw.get("fixture_id") != fixture_id:
                        raise ValueError("driver returned wrong fixture_id")
                    prov = _read_provenance(raw, head)
                    if baseline is None: baseline = prov
                    elif prov != baseline: raise ValueError("compiled driver provenance varied across runs")
                    ordered = _provider_order(raw)
                    annotated_runs.append(_annotate(raw, checker))
                    summary["driver_runs"].append({"fixture_id": fixture_id, "sample": sample,
                        "path": f"raw/runs/{fixture_id}/{fixture_id}-r{sample}.json", "provider_order": raw["provider_order"],
                        "input_path": f"input/{fixture_id}-r{sample}.json", "external_process": external})
                except Exception:
                    # Keep failed stdout/stderr private and never create a report bundle.
                    raise
            representative = json.loads(json.dumps(annotated_runs[0]))
            representative["raw_file"] = f"raw/{fixture_id}.json"
            representative["input_manifest"] = [{"path": f"input/{fixture_id}-r{i}.json",
                "sha256": sha256((temp / "input" / f"{fixture_id}-r{i}.json").read_bytes())} for i in range(1, 6)]
            for pi, provider in enumerate(representative["providers"]):
                mid = provider["method_id"]
                runs_for_provider = [next(p for p in run["providers"] if p["method_id"] == mid) for run in annotated_runs]
                samples, statuses, checks = [], [], []
                for item in runs_for_provider:
                    statuses.append(item.get("status", "missing"))
                    samples.append(item.get("elapsed_ns") if isinstance(item.get("elapsed_ns"), int) else None)
                    checks.append(item.get("exact_check", {"status": "inconclusive", "reason": "missing"}))
                if all(isinstance(value, int) and not isinstance(value, bool) for value in samples):
                    provider["elapsed_ns_samples"] = samples
                else:
                    provider.pop("elapsed_ns_samples", None)
                provider["sample_statuses"] = statuses
                provider["exact_check_samples"] = checks
                provider["exact_check_representative"] = checks[0]
                provider["outputs_vary"] = len({json.dumps({k:v for k,v in item.items() if k not in {"elapsed_ns", "interval"}}, sort_keys=True) for item in runs_for_provider}) > 1
                summary["method_statuses"].setdefault(fixture_id, {})[mid] = statuses
                summary["exact_checks"].setdefault(fixture_id, {})[mid] = checks
                summary["elapsed_ns_samples"].setdefault(fixture_id, {})[mid] = samples
            document_bytes = canonical(representative)
            (temp / "raw" / f"{fixture_id}.json").write_bytes(document_bytes)
            summary["comparison_files"][fixture_id] = f"raw/{fixture_id}.json"
        summary["provenance"] = baseline
        summary["source_sha256"] = SOURCE_SHA256
        summary["driver_sha256"] = sha256(driver.read_bytes())
        summary["build_config"] = baseline["build_config"]
        summary["compiler_id"] = baseline["compiler_id"]
        summary["compiler_version"] = baseline["compiler_version"]
        if oracle_receipt:
            shutil.copyfile(oracle_receipt, temp / "raw/oracle-differential.json")
        (temp / "raw/summary.json").write_bytes(canonical(summary))
        shutil.rmtree(temp / ".private")
        for name in REPO_SOURCES:
            target = temp / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target)
        optional_figures = root / "scripts/reports/btulshor/figures.py"
        if optional_figures.is_file():
            target = temp / "source/scripts/reports/btulshor/figures.py"
            shutil.copyfile(optional_figures, target)
        (temp / "offline_check.py").write_bytes(OFFLINE_CHECK_SOURCE)
        # Renderer output is produced in the pinned environment; its figure manifest, if any,
        # is placed under raw/ to preserve the public root allowlist.
        python = str(render_python or sys.executable)
        renderer = temp / "source/scripts/reports/btulshor/render.py"
        primary = temp / "raw/custom-square-point-classes.json"
        additional = [temp / "raw" / f"{fid}.json" for fid, _ in FIXTURES[1:]]
        subprocess.run([python, str(renderer), str(primary), "--output", str(temp / "index.html"),
            *sum((["--additional", str(p)] for p in additional), []), "--offline-zip-name", REPORT_ID + ".zip"],
            cwd=temp, check=True, capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        for cache in temp.rglob("__pycache__"):
            shutil.rmtree(cache)
        # Renderer supports only HTML and SVG as outputs. Copy generated figure manifest, when present.
        for candidate in temp.glob("figure-export.json"):
            candidate.rename(temp / "raw" / candidate.name)
        changed = {name: sha256((root / name).read_bytes()) for name in REPO_SOURCES}
        if changed != source_hashes or git_identity(root) != (head, False):
            raise ValueError("tracked source changed during capture")
        payload = {}
        for path in sorted(temp.rglob("*")):
            if path.is_file() and path.name not in {"manifest.json", "SHA256SUMS", REPORT_ID + ".zip"}:
                rel = path.relative_to(temp).as_posix()
                payload[rel] = sha256(path.read_bytes())
        manifest = {"schema": "csl.btulshor-source-faithful-bundle/1", "report_id": REPORT_ID,
            "capture_source_commit": head, "source_sha256": SOURCE_SHA256, "files": payload}
        (temp / "manifest.json").write_bytes(canonical(manifest))
        sums = {**payload, "manifest.json": sha256((temp / "manifest.json").read_bytes())}
        (temp / "SHA256SUMS").write_text("".join(f"{sums[n]}  {n}\n" for n in sorted(sums)), encoding="ascii")
        with zipfile.ZipFile(temp / (REPORT_ID + ".zip"), "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted([*payload, "manifest.json", "SHA256SUMS"]):
                archive.write(temp / name, f"{REPORT_ID}/{name}")
        if output.exists(): raise FileExistsError(f"immutable output appeared during capture: {output}")
        os.replace(temp, output)
    except Exception:
        # Failed outputs are private and clearly separated from report IDs.
        failed = output.parent / f".{REPORT_ID}.failed-{time.time_ns()}"
        if temp.exists(): os.replace(temp, failed)
        raise RuntimeError(f"capture failed; preserved private logs at {failed}") from None


def verify_bundle(directory: Path) -> None:
    """Verify an extracted bundle without Git, native code, FPC, or plotting imports."""
    manifest_path = directory / "manifest.json"
    sums_path = directory / "SHA256SUMS"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.btulshor-source-faithful-bundle/1": raise ValueError("unknown manifest schema")
    files = manifest.get("files")
    if not isinstance(files, dict): raise ValueError("manifest files must be a mapping")
    expected = set(files) | {"manifest.json"}
    sums = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        digest, sep, name = line.partition("  ")
        if not sep or len(digest) != 64 or name in sums: raise ValueError("malformed or duplicate SHA256SUMS entry")
        sums[name] = digest
    if set(sums) != expected: raise ValueError("SHA256SUMS inventory differs from manifest")
    for name, digest in {**files, "manifest.json": sha256(manifest_path.read_bytes())}.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts: raise ValueError("unsafe manifest path")
        candidate = directory.joinpath(*path.parts)
        if not candidate.is_file() or sha256(candidate.read_bytes()) != digest or sums[name] != digest:
            raise ValueError(f"bundle hash mismatch: {name}")
    allowed_unhashed = {"report-envelope.json", "publication-manifest.json", manifest.get("report_id", "") + ".zip"}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in directory.rglob("*")):
        raise ValueError("bundle must not contain symbolic links")
    extras = actual - expected - {"SHA256SUMS"} - allowed_unhashed
    if extras: raise ValueError(f"unlisted bundle files: {sorted(extras)}")
    raw = directory / "raw/summary.json"
    if raw.is_file():
        summary = json.loads(raw.read_text(encoding="utf-8"))
        if summary.get("schema") != SUMMARY_SCHEMA: raise ValueError("unknown summary schema")
        for fixture, rel in summary.get("comparison_files", {}).items():
            doc = json.loads((directory / rel).read_text(encoding="utf-8"))
            if doc.get("fixture_id") != fixture: raise ValueError("comparison fixture identity mismatch")
            for provider in doc.get("providers", []):
                check = provider.get("exact_check_representative", provider.get("exact_check", {}))
                if check.get("status") not in {"verified", "rejected", "inconclusive"}:
                    raise ValueError("unknown exact-check status")
        oracle = directory / "raw/oracle-differential.json"
        if oracle.is_file():
            receipt = json.loads(oracle.read_text(encoding="utf-8"))
            if receipt.get("source_sha256") != manifest.get("source_sha256") or receipt.get("driver_sha256") != summary.get("driver_sha256"):
                raise ValueError("oracle receipt source or driver identity differs")
    zip_path = directory / (manifest.get("report_id", "") + ".zip")
    if zip_path.is_file():
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if not name.startswith(manifest.get("report_id", "") + "/"):
                    raise ValueError("ZIP entry outside report prefix")
                if name.endswith("/"): continue
                rel = name.split("/", 1)[1]
                if rel not in expected | {"SHA256SUMS"}: raise ValueError("unexpected ZIP member")
                if archive.read(name) != (directory / rel).read_bytes(): raise ValueError(f"ZIP member mismatch: {rel}")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--render-python", type=Path)
    parser.add_argument("--oracle-receipt", type=Path)
    parser.add_argument("--check", type=Path, metavar="BUNDLE",
                        help="verify an extracted bundle without repository or native dependencies")
    # The optional word keeps earlier scripted `capture ...` calls readable.
    if argv and argv[0] == "capture": argv.pop(0)
    args = parser.parse_args(argv)
    try:
        if args.check:
            verify_bundle(args.check)
        else:
            if not args.driver or not args.output:
                parser.error("--driver and --output are required for capture")
            capture(args.driver.resolve(), args.output.resolve(), render_python=args.render_python.resolve() if args.render_python else None,
                    oracle_receipt=args.oracle_receipt.resolve() if args.oracle_receipt else None)
    except Exception as exc:
        print(f"btulshor capture: {exc}", file=sys.stderr)
        return 1
    print("verified" if args.check else f"captured {REPORT_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
