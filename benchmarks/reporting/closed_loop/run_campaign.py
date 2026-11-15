"""Freeze and resume the admitted closed-loop composition campaign."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import run_closed_loop
from capabilities import (
    COMPOSITIONS_MANIFEST,
    HISTORY_MANIFEST,
    MANIFEST,
    NATIVE_MANIFEST,
    manifest_digest,
    validate_manifest,
)

from contracts import ROOT, load_task, manifest_sha256

MANIFEST_PATHS = (MANIFEST, NATIVE_MANIFEST, HISTORY_MANIFEST, COMPOSITIONS_MANIFEST)
TASK_NAMES = ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")
CAMPAIGN_SCHEMA = "csl.closed-loop-composition-campaign/2"
RUNTIME_PACKAGES = ("numpy", "scipy", "do-mpc", "casadi", "matplotlib")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_packages() -> dict[str, str | None]:
    versions = {}
    for name in RUNTIME_PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def cmake_variable(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"set\({re.escape(name)}(?:\s+\"([^\"]+)\"|\s+([^\s\)]+))\)", text)
    return (match.group(1) or match.group(2)) if match else None


def native_build_profile(cache_path: Path) -> dict[str, str | None]:
    if not cache_path.is_file():
        raise ValueError(f"native policy CMake cache does not exist: {cache_path}")
    values = {}
    for line in cache_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("//") or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        _, separator, value = value.partition("=")
        if separator:
            values[key] = value
    source_root = values.get("CSL_SOURCE_ROOT")
    if source_root is None or Path(source_root).resolve() != ROOT.resolve():
        raise ValueError("native policy build cache does not belong to the frozen source tree")
    compiler_id = values.get("CMAKE_CXX_COMPILER_ID")
    compiler_version = values.get("CMAKE_CXX_COMPILER_VERSION")
    compiler_details = next(cache_path.parent.glob("CMakeFiles/*/CMakeCXXCompiler.cmake"), None)
    if compiler_details is not None:
        text = compiler_details.read_text(encoding="utf-8")
        compiler_id_match = re.search(r'set\(CMAKE_CXX_COMPILER_ID "([^"]+)"\)', text)
        compiler_version_match = re.search(r'set\(CMAKE_CXX_COMPILER_VERSION "([^"]+)"\)', text)
        compiler_id = compiler_id or (compiler_id_match.group(1) if compiler_id_match else None)
        compiler_version = compiler_version or (
            compiler_version_match.group(1) if compiler_version_match else None
        )
    highs_build = values.get("HIGHS_BINARY_DIR")
    highs_config = (
        Path(highs_build) / "highs-config.cmake"
        if highs_build
        else cache_path.parent / "_deps/csl_highs-build/highs-config.cmake"
    )
    qhull_source = values.get("FETCHCONTENT_SOURCE_DIR_CSL_QHULL") or str(
        cache_path.parent / "_deps/csl_qhull-src"
    )
    casadi_config = (
        Path(values["casadi_DIR"]) / "casadi-config-version.cmake"
        if values.get("casadi_DIR")
        else None
    )
    return {
        "source_root": "reviewed repository checkout",
        "build_type": values.get("CMAKE_BUILD_TYPE"),
        "generator": values.get("CMAKE_GENERATOR"),
        "cxx_compiler": Path(values["CMAKE_CXX_COMPILER"]).name
        if values.get("CMAKE_CXX_COMPILER")
        else None,
        "cxx_compiler_id": compiler_id,
        "cxx_compiler_version": compiler_version,
        "highs": values.get("CSL_ENABLE_HIGHS"),
        "highs_version": cmake_variable(highs_config, "HIGHS_VERSION"),
        "qhull": values.get("CSL_ENABLE_QHULL"),
        "qhull_version": cmake_variable(Path(qhull_source) / "CMakeLists.txt", "qhull_VERSION"),
        "casadi": values.get("CSL_ENABLE_CASADI"),
        "casadi_package_version": runtime_packages().get("casadi"),
        "casadi_cpp_package_version": cmake_variable(casadi_config, "PACKAGE_VERSION")
        if casadi_config
        else None,
    }


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def ensure_clean_source() -> None:
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status:
        raise ValueError("campaign freeze requires a clean source worktree")


def ensure_reviewed_source() -> None:
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main"],
            cwd=ROOT,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            "campaign freeze requires a source commit reachable from origin/main; "
            "fetch reviewed main before freezing"
        ) from error


def ensure_clean_tracked_source() -> None:
    for args in (["git", "diff", "--quiet", "HEAD"], ["git", "diff", "--cached", "--quiet"]):
        try:
            subprocess.check_call(args, cwd=ROOT)
        except subprocess.CalledProcessError as error:
            raise ValueError("campaign run requires unchanged tracked source files") from error


def task_name_by_id() -> dict[str, str]:
    return {load_task(name)["task_id"]: name for name in TASK_NAMES}


def catalogue_inventory() -> tuple[list[dict], list[dict], list[dict]]:
    """Return source manifests, unique admitted graphs and explicit candidate rows."""
    sources: list[dict] = []
    graphs_by_id: dict[str, dict] = {}
    candidates: list[dict] = []
    task_names = task_name_by_id()

    for path in MANIFEST_PATHS:
        manifest = validate_manifest(manifest_path=path)
        relative_path = str(path.relative_to(ROOT))
        source = {
            "path": relative_path,
            "manifest_id": manifest["manifest_id"],
            "sha256": sha256_file(path),
            "manifest_sha256": manifest_digest(manifest),
            "graph_count": len(manifest["graphs"]),
        }
        sources.append(source)
        for row in manifest["graphs"]:
            graph_id = row["graph_id"]
            existing = graphs_by_id.get(graph_id)
            if existing is not None:
                if existing["graph"] != row:
                    raise ValueError(f"catalogues disagree on graph definition {graph_id}")
                existing["catalogues"].append(relative_path)
                continue
            task_name = task_names.get(row["task_id"])
            if task_name is None:
                raise ValueError(f"graph has an unknown task identity: {row['task_id']}")
            graphs_by_id[graph_id] = {
                "graph": row,
                "task_name": task_name,
                "catalogue_path": relative_path,
                "catalogues": [relative_path],
            }

        for candidate in manifest.get("candidates", []):
            candidates.append({"catalogue_path": relative_path, **copy.deepcopy(candidate)})

    graphs = []
    catalogue_hashes = {source["path"]: source["manifest_sha256"] for source in sources}
    for graph_id, item in sorted(graphs_by_id.items()):
        graph = item["graph"]
        graphs.append(
            {
                "graph_id": graph_id,
                "graph_fingerprint": graph["graph_fingerprint"],
                "task_name": item["task_name"],
                "task_id": graph["task_id"],
                "task_sha256": graph["task_sha256"],
                "action_profile_id": graph["action_profile_id"],
                "admission": graph["admission"],
                "catalogue_path": item["catalogue_path"],
                "capability_manifest_sha256": catalogue_hashes[item["catalogue_path"]],
                "catalogues": item["catalogues"],
                "controller": graph["controller"],
                "execution": graph["execution"],
                "role_bindings": graph.get("role_bindings", {}),
                "inactive_roles": graph.get("inactive_roles", {}),
                "source_files": graph["source_files"],
            }
        )
    return sources, graphs, candidates


def build_freeze(
    bridge: Path,
    native_policy_bridge: Path,
    native_policy_cache: Path,
    wall_seconds: int,
    cpu_seconds: int,
) -> dict:
    if not bridge.is_file():
        raise ValueError(f"execution bridge does not exist: {bridge}")
    if not native_policy_bridge.is_file():
        raise ValueError(f"native policy bridge does not exist: {native_policy_bridge}")
    sources, graphs, candidates = catalogue_inventory()
    task_hashes = {name: manifest_sha256(load_task(name)) for name in TASK_NAMES}
    graph_counts_by_task = {
        name: sum(graph["task_name"] == name for graph in graphs) for name in TASK_NAMES
    }
    return {
        "schema": CAMPAIGN_SCHEMA,
        "source_commit": source_commit(),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "runtime_packages": runtime_packages(),
        },
        "bridge": {
            "name": bridge.name,
            "sha256": sha256_file(bridge),
        },
        "native_policy": {
            "name": native_policy_bridge.name,
            "sha256": sha256_file(native_policy_bridge),
            "build_cache_sha256": sha256_file(native_policy_cache),
            "build_profile": native_build_profile(native_policy_cache),
        },
        "resource_profile": {
            "profile_id": f"worker-wall-{wall_seconds}-cpu-{cpu_seconds}/1",
            "attempt_wall_seconds": wall_seconds,
            "attempt_cpu_seconds": cpu_seconds,
            "address_space_bytes": 8 * 1024**3,
            "address_space_enforcement": "POSIX RLIMIT_AS on worker process; inherited by child processes",
            "suite_worker_count": 1,
            "solver_threads": 1,
            "suite_memory_request_policy": (
                "min(2 GiB, 75% of available memory at attempt start); recorded by the runner"
            ),
            "suite_memory_allocation_bytes": None,
            "suite_memory_enforcement": (
                "no machine-wide suite limiter; per-process RLIMIT_AS only"
            ),
        },
        "claim_scope": (
            "One-pass correctness and outcome inventory. No timing winner is claimed; "
            "comparative timing needs five alternating Release repetitions and independent checks."
        ),
        "task_sha256": task_hashes,
        "catalogues": sources,
        "candidate_counts": {
            "catalogue_graph_references": sum(row["graph_count"] for row in sources),
            "duplicate_graph_references": sum(row["graph_count"] for row in sources) - len(graphs),
            "canonical_active_graphs": len(graphs),
            "admitted_graphs": len(graphs),
            "source_composition_candidates": len(candidates),
            "source_requestable_candidates": sum(
                row["status"] == "requestable" for row in candidates
            ),
            "source_incompatible_candidates": sum(
                row["status"] == "incompatible" for row in candidates
            ),
            "admitted_graphs_by_task": graph_counts_by_task,
        },
        "candidates": candidates,
        "graphs": graphs,
    }


def freeze(
    path: Path,
    bridge: Path,
    native_policy_bridge: Path,
    native_policy_cache: Path,
    wall_seconds: int,
    cpu_seconds: int,
) -> dict:
    ensure_clean_source()
    ensure_reviewed_source()
    sidecar_path = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or sidecar_path.exists():
        raise ValueError(f"freeze file already exists and is immutable: {path}")
    record = build_freeze(
        bridge, native_policy_bridge, native_policy_cache, wall_seconds, cpu_seconds
    )
    payload = json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()
    sidecar_path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return record


def read_freeze(
    path: Path,
    bridge: Path,
    native_policy_bridge: Path,
    native_policy_cache: Path,
) -> dict:
    payload = path.read_bytes()
    sidecar = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
    if hashlib.sha256(payload).hexdigest() != sidecar:
        raise ValueError("campaign freeze hash mismatch")
    record = json.loads(payload)
    if record.get("schema") != CAMPAIGN_SCHEMA:
        raise ValueError("unsupported campaign freeze schema")
    if source_commit() != record["source_commit"]:
        raise ValueError("current source commit differs from frozen campaign commit")
    ensure_reviewed_source()
    ensure_clean_tracked_source()
    if sha256_file(Path(__file__).resolve()) != record["runner_sha256"]:
        raise ValueError("campaign driver source differs from the frozen commit")
    for source in record["catalogues"]:
        if sha256_file(ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"frozen capability catalogue changed: {source['path']}")
    current_sources, current_graphs, current_candidates = catalogue_inventory()
    if (
        current_sources != record["catalogues"]
        or current_graphs != record["graphs"]
        or current_candidates != record["candidates"]
    ):
        raise ValueError("frozen candidate universe differs from the current source catalogues")
    if {name: manifest_sha256(load_task(name)) for name in TASK_NAMES} != record["task_sha256"]:
        raise ValueError("a frozen task contract has changed")
    if not bridge.is_file() or sha256_file(bridge) != record["bridge"]["sha256"]:
        raise ValueError("frozen execution bridge is unavailable or has changed")
    native_policy = record["native_policy"]
    if (
        not native_policy_bridge.is_file()
        or sha256_file(native_policy_bridge) != native_policy["sha256"]
    ):
        raise ValueError("frozen native policy bridge is unavailable or has changed")
    if (
        not native_policy_cache.is_file()
        or sha256_file(native_policy_cache) != native_policy["build_cache_sha256"]
        or native_build_profile(native_policy_cache) != native_policy["build_profile"]
    ):
        raise ValueError("frozen native policy build profile is unavailable or has changed")
    if runtime_packages() != record["environment"]["runtime_packages"]:
        raise ValueError("runtime Python provider versions differ from the frozen environment")
    return record


def campaign_binding(record: dict, item: dict, attempt_path: Path | None = None) -> dict:
    return {
        "schema": "csl.closed-loop-campaign-attempt/1",
        "source_commit": record["source_commit"],
        "task_name": item["task_name"],
        "task_sha256": item["task_sha256"],
        "graph_id": item["graph_id"],
        "graph_fingerprint": item["graph_fingerprint"],
        "capability_manifest_sha256": item["capability_manifest_sha256"],
        "bridge_sha256": record["bridge"]["sha256"],
        "resource_profile_id": record["resource_profile"]["profile_id"],
        "native_policy_bridge_sha256": record["native_policy"]["sha256"],
        "native_policy_build_cache_sha256": record["native_policy"]["build_cache_sha256"],
        "native_policy_build_profile": record["native_policy"]["build_profile"],
        "python_runtime_packages": record["environment"]["runtime_packages"],
        "attempt": str(attempt_path) if attempt_path else None,
    }


def write_json_atomically(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def campaign_journal_path(output_root: Path, item: dict) -> Path:
    identity = f"{item['task_name']}\0{item['graph_id']}".encode()
    return output_root / ".campaign-attempts" / f"{hashlib.sha256(identity).hexdigest()}.json"


def recover_started_attempts(output_root: Path, record: dict) -> None:
    """Recover a runner attempt created after its durable campaign intent."""
    journals = output_root / ".campaign-attempts"
    if not journals.is_dir():
        return
    planned = {(item["task_name"], item["graph_id"]): item for item in record["graphs"]}
    for journal_path in journals.glob("*.json"):
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if journal.get("state") != "started":
                continue
            item = planned[(journal["task_name"], journal["graph_id"])]
            candidates = []
            for request_path in (output_root / item["task_name"] / "attempts").glob(
                "*/request.json"
            ):
                request = json.loads(request_path.read_text(encoding="utf-8"))
                if (
                    request.get("source_commit") == record["source_commit"]
                    and request.get("requested", {}).get("graph_id") == item["graph_id"]
                    and request.get("requested", {}).get("resource_profile_id")
                    == record["resource_profile"]["profile_id"]
                    and not (request_path.parent / "campaign-runtime.json").exists()
                ):
                    candidates.append(request_path.parent)
            if len(candidates) == 1:
                attempt_path = candidates[0]
                binding = campaign_binding(record, item, attempt_path)
                attempt_data = attempt_path / "attempt.json"
                if attempt_data.is_file():
                    receipt = json.loads(attempt_data.read_text(encoding="utf-8"))
                    binding["executed_native_policy_bridge_sha256"] = (
                        receipt.get("preparation_receipt", {})
                        .get("adapter_receipt", {})
                        .get("executable_sha256")
                    )
                if (
                    binding.get("executed_native_policy_bridge_sha256") is not None
                    and binding["executed_native_policy_bridge_sha256"]
                    != record["native_policy"]["sha256"]
                ):
                    journal["state"] = "rejected_provider_mismatch"
                    write_json_atomically(journal_path, journal)
                    continue
                write_json_atomically(attempt_path / "campaign-runtime.json", binding)
                journal.update({"state": "recovered", "attempt": str(attempt_path)})
                write_json_atomically(journal_path, journal)
            elif not candidates:
                journal["state"] = "interrupted_before_runner_attempt"
                write_json_atomically(journal_path, journal)
        except (OSError, KeyError, json.JSONDecodeError):
            continue


def iter_verified_attempts(output_root: Path, record: dict):
    """Yield attempts whose runner outputs match a durable campaign sidecar."""
    recover_started_attempts(output_root, record)
    planned = {(graph["task_name"], graph["graph_id"]): graph for graph in record["graphs"]}
    for path in output_root.glob("*/attempts/*/request.json"):
        try:
            request = json.loads(path.read_text(encoding="utf-8"))
            requested = request["requested"]
            graph_id = requested.get("graph_id")
            task_name = path.parents[2].name
            key = (task_name, graph_id)
            item = planned.get(key)
            binding_path = path.parent / "campaign-runtime.json"
            if not binding_path.is_file():
                continue
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            if (
                item is None
                or request.get("source_commit") != record["source_commit"]
                or requested.get("resource_profile_id") != record["resource_profile"]["profile_id"]
                or any(
                    binding.get(name) != value
                    for name, value in campaign_binding(record, item, path.parent).items()
                )
            ):
                continue
            attempt_path = path.parent / "attempt.json"
            if not attempt_path.is_file():
                continue
            run_manifest_path = path.parent / "run-manifest.json"
            if run_manifest_path.is_file():
                run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
                if (
                    run_manifest.get("source_commit") != record["source_commit"]
                    or run_manifest.get("task_sha256") != item["task_sha256"]
                    or run_manifest.get("graph_id") != item["graph_id"]
                    or run_manifest.get("graph_fingerprint") != item["graph_fingerprint"]
                    or run_manifest.get("capability_manifest_sha256")
                    != item["capability_manifest_sha256"]
                    or run_manifest.get("bridge_sha256") != record["bridge"]["sha256"]
                    or run_manifest.get("resource_profile_id")
                    != record["resource_profile"]["profile_id"]
                ):
                    continue
            yield item, path, attempt_path
        except (OSError, KeyError, json.JSONDecodeError):
            continue


def attempted_graphs(output_root: Path, freeze_record: dict) -> set[tuple[str, str]]:
    return {
        (item["task_name"], item["graph_id"])
        for item, _, _ in iter_verified_attempts(output_root, freeze_record)
    }


def campaign_order(graphs: list[dict]) -> list[dict]:
    """Interleave tasks so bounded campaign batches cover every environment."""
    by_task = {task_name: [] for task_name in TASK_NAMES}
    for graph in graphs:
        task_name = graph["task_name"]
        if task_name not in by_task:
            raise ValueError(f"campaign graph has an unknown task: {task_name}")
        by_task[task_name].append(graph)

    return [
        by_task[task_name][index]
        for index in range(max(map(len, by_task.values()), default=0))
        for task_name in TASK_NAMES
        if index < len(by_task[task_name])
    ]


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def run_frozen_attempt(
    task_name: str,
    output_root: Path,
    bridge: Path,
    native_policy_bridge: Path,
    profile: dict,
    item: dict,
    manifest_path: Path,
) -> dict:
    variable = "CSL_NATIVE_POLICY_BRIDGE"
    previous = os.environ.get(variable)
    os.environ[variable] = str(native_policy_bridge.resolve(strict=True))
    try:
        return run_closed_loop.run_task(
            task_name,
            output_root,
            bridge,
            attempt_wall_seconds=profile["attempt_wall_seconds"],
            attempt_cpu_seconds=profile["attempt_cpu_seconds"],
            graph_id=item["graph_id"],
            capability_manifest_path=manifest_path,
        )
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous


def write_campaign_runtime_sidecar(attempt_path: Path, record: dict, item: dict) -> None:
    """Persist campaign provenance beside, without rewriting, common-runner evidence."""
    attempt_record_path = attempt_path / "attempt.json"
    attempt = json.loads(attempt_record_path.read_text(encoding="utf-8"))
    adapter_receipt = attempt.get("preparation_receipt", {}).get("adapter_receipt", {})
    actual_binary_sha256 = adapter_receipt.get("executable_sha256")
    frozen_binary_sha256 = record["native_policy"]["sha256"]
    if actual_binary_sha256 is not None and actual_binary_sha256 != frozen_binary_sha256:
        raise ValueError("attempt used a native policy bridge different from its campaign freeze")
    binding = campaign_binding(record, item, attempt_path)
    binding["executed_native_policy_bridge_sha256"] = actual_binary_sha256
    write_json_atomically(attempt_path / "campaign-runtime.json", binding)


def run_campaign(
    record: dict,
    output_root: Path,
    bridge: Path,
    native_policy_bridge: Path,
    max_attempts: int | None = None,
) -> dict:
    profile = record["resource_profile"]
    attempted = attempted_graphs(output_root, record)
    attempted_before_run = len(attempted)
    attempted_now = 0
    skipped = 0
    events_path = output_root / "campaign-events.jsonl"
    for item in campaign_order(record["graphs"]):
        key = (item["task_name"], item["graph_id"])
        if key in attempted:
            skipped += 1
            continue
        if max_attempts is not None and attempted_now >= max_attempts:
            continue
        manifest_path = ROOT / item["catalogue_path"]
        journal_path = campaign_journal_path(output_root, item)
        journal = campaign_binding(record, item)
        journal.update({"state": "started", "started_unix_ns": time.time_ns()})
        write_json_atomically(journal_path, journal)
        result = run_frozen_attempt(
            item["task_name"],
            output_root,
            bridge,
            native_policy_bridge,
            profile,
            item,
            manifest_path,
        )
        attempt_path = Path(result["attempt"]).resolve()
        write_campaign_runtime_sidecar(attempt_path, record, item)
        journal.update({"state": "completed", "attempt": str(attempt_path)})
        write_json_atomically(journal_path, journal)
        try:
            attempt_reference = str(attempt_path.relative_to(output_root.resolve()))
        except ValueError as error:
            raise ValueError(
                "common runner wrote an attempt outside the campaign output root"
            ) from error
        append_event(
            events_path,
            {
                "schema": "csl.closed-loop-campaign-event/1",
                "source_commit": record["source_commit"],
                "graph_id": item["graph_id"],
                "graph_fingerprint": item["graph_fingerprint"],
                "task_name": item["task_name"],
                "task_sha256": item["task_sha256"],
                "attempt": attempt_reference,
                "native_policy_bridge_sha256": record["native_policy"]["sha256"],
                "status": result.get("overall_status", result.get("status")),
                "algorithm_status": result.get("algorithm_status"),
                "postcheck_status": result.get("postcheck_status"),
                "render_status": result.get("render_status"),
                "completed_holds": result.get("completed_holds", 0),
            },
        )
        attempted.add(key)
        attempted_now += 1
    runner_coverage_path = run_closed_loop.write_coverage(output_root)
    coverage = build_campaign_coverage(record, output_root)
    coverage_path = output_root / (
        "campaign-coverage-"
        + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        + "-"
        + uuid.uuid4().hex[:8]
        + ".json"
    )
    coverage_path.write_text(json.dumps(coverage, sort_keys=True, indent=2) + "\n")
    coverage_digest = sha256_file(coverage_path)
    coverage_path.with_suffix(coverage_path.suffix + ".sha256").write_text(
        f"{coverage_digest}  {coverage_path.name}\n", encoding="utf-8"
    )
    return {
        "source_commit": record["source_commit"],
        "native_policy_bridge_sha256": record["native_policy"]["sha256"],
        "canonical_active_graphs": len(record["graphs"]),
        "attempted_before_run": attempted_before_run,
        "attempted_this_run": attempted_now,
        "skipped_existing_attempts": skipped,
        "remaining": len(record["graphs"]) - len(attempted),
        "coverage_record": str(coverage_path),
        "runner_coverage_record": str(runner_coverage_path),
        "event_ledger": str(events_path),
    }


def classify_attempt(record: dict, attempt_path: Path) -> tuple[str, str | None]:
    overall = record.get("overall_status", record.get("status", "incomplete"))
    algorithm = record.get("algorithm_status", record.get("status", "incomplete"))
    postcheck = record.get("postcheck_status", "not_run")
    support = record.get("mathematical_support_status", "not_evaluated")
    if overall == "complete":
        return "complete", None
    if overall in {"timed_out", "resource_limited", "cancelled", "unsupported"}:
        return overall, None
    if postcheck == "failed" or support == "incorrect":
        return "incorrect", None
    if support == "inconclusive":
        return "inconclusive", None
    refusal_path = attempt_path.parent / "resolution-refusal.json"
    if refusal_path.is_file():
        try:
            reason = json.loads(refusal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reason = {}
        message = str(reason.get("reason", ""))
        lowered = message.lower()
        if "backend" in lowered and any(
            word in lowered for word in ("unavailable", "missing", "not found")
        ):
            return "backend_unavailable", message
        if "unsupported" in lowered:
            return "unsupported", message
        if any(
            word in lowered
            for word in ("not implemented", "no registered", "factory is not registered")
        ):
            return "implementation_missing", message
        return "refused", message or None
    if algorithm == "failed" or overall == "failed":
        return "failed", None
    if overall == "incomplete" or algorithm == "incomplete":
        return "inconclusive", None
    return str(overall), None


def build_campaign_coverage(record: dict, output_root: Path) -> dict:
    attempts_by_graph: dict[tuple[str, str], list[dict]] = {}
    for item, _, attempt_path in iter_verified_attempts(output_root, record):
        try:
            try:
                attempt, _ = run_closed_loop.read_attempt(attempt_path)
                category, reason = classify_attempt(attempt, attempt_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                attempt = {"status": "invalid_record"}
                category, reason = "invalid_record", str(error)
            attempts_by_graph.setdefault((item["task_name"], item["graph_id"]), []).append(
                {
                    "attempt_id": attempt.get("attempt_id"),
                    "path": str(attempt_path.relative_to(output_root)),
                    "overall_status": attempt.get("overall_status", attempt.get("status")),
                    "algorithm_status": attempt.get("algorithm_status", attempt.get("status")),
                    "postcheck_status": attempt.get("postcheck_status", "not_run"),
                    "render_status": attempt.get("render_status", "not_run"),
                    "category": category,
                    "reason": reason,
                }
            )
        except (OSError, KeyError, json.JSONDecodeError):
            continue

    for attempts in attempts_by_graph.values():
        attempts.sort(key=lambda item: item["attempt_id"] or item["path"])

    cells = []
    outcome_counts: dict[str, int] = {}
    graph_outcome_counts: dict[str, int] = {}
    attempted_graphs_count = 0
    for item in record["graphs"]:
        attempts = attempts_by_graph.get((item["task_name"], item["graph_id"]), [])
        if attempts:
            attempted_graphs_count += 1
        for attempt in attempts:
            outcome_counts[attempt["category"]] = outcome_counts.get(attempt["category"], 0) + 1
        latest_category = attempts[-1]["category"] if attempts else "pending"
        graph_outcome_counts[latest_category] = graph_outcome_counts.get(latest_category, 0) + 1
        cells.append(
            {
                "task_name": item["task_name"],
                "task_sha256": item["task_sha256"],
                "graph_id": item["graph_id"],
                "graph_fingerprint": item["graph_fingerprint"],
                "catalogue_path": item["catalogue_path"],
                "status": "attempted" if attempts else "pending",
                "attempts": attempts,
            }
        )
    excluded = sum(candidate["status"] == "incompatible" for candidate in record["candidates"])
    return {
        "schema": "csl.closed-loop-composition-campaign-coverage/1",
        "source_commit": record["source_commit"],
        "candidate_counts": record["candidate_counts"],
        "catalogues": record["catalogues"],
        "resource_profile": record["resource_profile"],
        "outcomes": {
            "canonical_active_graphs": len(record["graphs"]),
            "admitted_graphs": len(record["graphs"]),
            "attempted_graphs": attempted_graphs_count,
            "pending_graphs": len(record["graphs"]) - attempted_graphs_count,
            "attempt_rows": sum(len(cell["attempts"]) for cell in cells),
            "incompatible_candidates": excluded,
            "by_graph_outcome": graph_outcome_counts,
            "by_attempt_category": outcome_counts,
            "excluded_candidates": [
                candidate
                for candidate in record["candidates"]
                if candidate["status"] == "incompatible"
            ],
        },
        "cells": cells,
    }


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_parser = commands.add_parser("freeze", help="validate and freeze all four catalogues")
    freeze_parser.add_argument("--bridge", type=Path, required=True)
    freeze_parser.add_argument("--native-policy-bridge", type=Path, required=True)
    freeze_parser.add_argument("--native-policy-cache", type=Path, required=True)
    freeze_parser.add_argument("--output", type=Path, required=True)
    freeze_parser.add_argument("--attempt-wall-seconds", type=positive_integer, default=300)
    freeze_parser.add_argument("--attempt-cpu-seconds", type=positive_integer, default=300)
    run_parser = commands.add_parser("run", help="run missing graph/task pairs from a freeze")
    run_parser.add_argument("--freeze", type=Path, required=True)
    run_parser.add_argument("--bridge", type=Path, required=True)
    run_parser.add_argument("--native-policy-bridge", type=Path, required=True)
    run_parser.add_argument("--native-policy-cache", type=Path, required=True)
    run_parser.add_argument("--output-root", type=Path, required=True)
    run_parser.add_argument("--max-attempts", type=positive_integer)
    args = parser.parse_args()

    try:
        if args.command == "freeze":
            record = freeze(
                args.output,
                args.bridge,
                args.native_policy_bridge,
                args.native_policy_cache,
                args.attempt_wall_seconds,
                args.attempt_cpu_seconds,
            )
            result = {
                "freeze": str(args.output.resolve()),
                "source_commit": record["source_commit"],
                "candidate_counts": record["candidate_counts"],
            }
        else:
            record = read_freeze(
                args.freeze, args.bridge, args.native_policy_bridge, args.native_policy_cache
            )
            result = run_campaign(
                record,
                args.output_root.resolve(),
                args.bridge.resolve(),
                args.native_policy_bridge.resolve(),
                args.max_attempts,
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
