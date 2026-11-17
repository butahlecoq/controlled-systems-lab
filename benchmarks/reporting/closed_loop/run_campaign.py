"""Freeze and resume the admitted closed-loop composition campaign."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.metadata
import itertools
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Literal, TypedDict

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
FIXED_TAIL_REPRESENTATIONS = ("box", "ellipsoid", "parallelotope", "polytope", "zonotope")


def fixed_tail_controller_id(representation: str) -> str:
    if representation not in FIXED_TAIL_REPRESENTATIONS:
        raise ValueError(f"unsupported fixed-tail representation: {representation}")
    return f"native-fixed-tail-{representation}-ipopt/1"


def fixed_tail_representation_pairs() -> list[tuple[str, str]]:
    return list(itertools.combinations(FIXED_TAIL_REPRESENTATIONS, 2))


class PairedScheduleRow(TypedDict):
    phase: Literal["warmup", "measured"]
    repetition: int
    order: list[Literal["A", "B"]]


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
                    and request_path.stat().st_mtime_ns >= journal.get("started_unix_ns", 0)
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
                or binding.get("executed_native_policy_bridge_sha256")
                not in (None, record["native_policy"]["sha256"])
                or any(
                    binding.get(name) != value
                    for name, value in campaign_binding(record, item, path.parent).items()
                )
            ):
                continue
            attempt_path = path.parent / "attempt.json"
            if not attempt_path.is_file():
                continue
            attempt_data = json.loads(attempt_path.read_text(encoding="utf-8"))
            executed_binary = (
                attempt_data.get("preparation_receipt", {})
                .get("adapter_receipt", {})
                .get("executable_sha256")
            )
            if executed_binary != binding.get("executed_native_policy_bridge_sha256"):
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
    measurement_claim: str = "one-off correctness pilot; clocks descriptive, no speed comparison",
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
            measurement_claim=measurement_claim,
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


def paired_method_schedule(repetitions: int) -> list[PairedScheduleRow]:
    """Return one excluded warm-up and alternating measured A/B attempts."""
    if repetitions < 1:
        raise ValueError("paired comparison requires at least one measured repetition")
    schedule: list[PairedScheduleRow] = [{"phase": "warmup", "repetition": 0, "order": ["A", "B"]}]
    for repetition in range(1, repetitions + 1):
        order: list[Literal["A", "B"]] = ["A", "B"] if repetition % 2 else ["B", "A"]
        schedule.append({"phase": "measured", "repetition": repetition, "order": order})
    return schedule


def select_paired_graphs(
    record: dict, controller_a: str, controller_b: str
) -> dict[str, dict[str, dict]]:
    if not controller_a or not controller_b or controller_a == controller_b:
        raise ValueError("paired timing requires two different controller identities")
    controllers = {"A": controller_a, "B": controller_b}
    graphs_by_task: dict[str, dict[str, dict]] = {task: {} for task in TASK_NAMES}
    for item in record["graphs"]:
        task = item["task_name"]
        controller = item.get("controller", {}).get("id")
        if task in graphs_by_task and controller in controllers.values():
            side = next(side for side, value in controllers.items() if value == controller)
            if side in graphs_by_task[task]:
                raise ValueError(f"frozen comparison has duplicate {side} graph for {task}")
            graphs_by_task[task][side] = item
    if any(set(sides) != {"A", "B"} for sides in graphs_by_task.values()):
        raise ValueError("frozen comparison must contain both matched methods for all three tasks")
    for task, sides in graphs_by_task.items():
        a, b = sides["A"], sides["B"]
        if (
            a["task_id"],
            a["task_sha256"],
            a["action_profile_id"],
            a["execution"],
            a["role_bindings"].get("control_optimizer"),
            a["controller"].get("solver"),
        ) != (
            b["task_id"],
            b["task_sha256"],
            b["action_profile_id"],
            b["execution"],
            b["role_bindings"].get("control_optimizer"),
            b["controller"].get("solver"),
        ):
            raise ValueError(
                f"comparison methods do not share task, action, execution and solver: {task}"
            )
    return graphs_by_task


def run_paired_timing(
    record: dict,
    freeze_path: Path,
    output_root: Path,
    bridge: Path,
    native_policy_bridge: Path,
    comparison_packer: Path,
    repetitions: int = 5,
    controller_a: str | None = None,
    controller_b: str | None = None,
) -> dict:
    controller_a = fixed_tail_controller_id("polytope") if controller_a is None else controller_a
    controller_b = fixed_tail_controller_id("zonotope") if controller_b is None else controller_b
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".paired-timing.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another paired timing invocation owns this output root") from error
        try:
            return _run_paired_timing_locked(
                record,
                freeze_path,
                output_root,
                bridge,
                native_policy_bridge,
                comparison_packer,
                repetitions,
                controller_a,
                controller_b,
            )
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _run_paired_timing_locked(
    record: dict,
    freeze_path: Path,
    output_root: Path,
    bridge: Path,
    native_policy_bridge: Path,
    comparison_packer: Path,
    repetitions: int,
    controller_a: str,
    controller_b: str,
) -> dict:
    """Measure two frozen controller profiles in paired alternating order."""
    if repetitions < 5:
        raise ValueError("comparison-program timing requires at least five measured repetitions")
    controllers = {"A": controller_a, "B": controller_b}
    tasks = ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")
    graphs_by_task = select_paired_graphs(record, controller_a, controller_b)

    events_path = output_root / "paired-timing-events.jsonl"
    freeze_sha256 = sha256_file(freeze_path)
    existing: dict[tuple[str, str, int, str, int], dict] = {}
    expected_identity = {
        "freeze_sha256": freeze_sha256,
        "source_commit": record["source_commit"],
        "bridge_sha256": record["bridge"]["sha256"],
        "native_policy_sha256": record["native_policy"]["sha256"],
        "resource_profile_id": record["resource_profile"]["profile_id"],
    }
    if events_path.exists():
        for line_number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1):
            event = json.loads(line)
            if event.get("schema") != "csl.closed-loop-paired-timing-event/2":
                raise ValueError(f"unknown paired timing event schema on line {line_number}")
            if any(event.get(field) != value for field, value in expected_identity.items()):
                raise ValueError(
                    f"paired timing event belongs to a different freeze on line {line_number}"
                )
            key = (
                event["task_name"],
                event["phase"],
                event["repetition"],
                event["side"],
                event["try_index"],
            )
            if key in existing:
                previous = existing[key]
                if previous.get("state") != "started" or event.get("state") not in {
                    "completed",
                    "interrupted",
                }:
                    raise ValueError(
                        f"invalid paired timing event transition on line {line_number}"
                    )
            existing[key] = event

    def event_graph(event: dict) -> dict:
        try:
            return graphs_by_task[event["task_name"]][event["side"]]
        except KeyError as error:
            raise ValueError("paired timing event names an unknown task or method side") from error

    def validate_completed_event(event: dict) -> None:
        graph = event_graph(event)
        expected = {
            "graph_id": graph["graph_id"],
            "graph_fingerprint": graph["graph_fingerprint"],
            "task_sha256": graph["task_sha256"],
            "controller_id": graph["controller"]["id"],
        }
        if any(event.get(field) != value for field, value in expected.items()):
            raise ValueError("paired timing event graph identity differs from its freeze")
        attempt_path = Path(event["attempt"]).resolve(strict=True)
        try:
            attempt_path.relative_to(output_root.resolve())
        except ValueError as error:
            raise ValueError("paired timing event points outside its output root") from error
        attempt_file = attempt_path / "attempt.json"
        if sha256_file(attempt_file) != event.get("attempt_sha256"):
            raise ValueError("paired timing attempt hash differs from its event")
        request = json.loads((attempt_path / "request.json").read_text(encoding="utf-8"))
        manifest_path = attempt_path / "run-manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        )
        runtime_path = attempt_path / "campaign-runtime.json"
        runtime_binding = (
            json.loads(runtime_path.read_text(encoding="utf-8")) if runtime_path.is_file() else {}
        )
        recorded_manifest_hash = event.get("run_manifest_sha256")
        if (manifest_path.is_file() != (recorded_manifest_hash is not None)) or (
            manifest_path.is_file() and sha256_file(manifest_path) != recorded_manifest_hash
        ):
            raise ValueError("paired timing run-manifest hash differs from its event")
        if not runtime_path.is_file() or sha256_file(runtime_path) != event.get(
            "campaign_runtime_sha256"
        ):
            raise ValueError("paired timing runtime binding is missing or changed")
        if (
            request.get("source_commit") != record["source_commit"]
            or request.get("requested", {}).get("graph_id") != graph["graph_id"]
            or request.get("requested", {}).get("resource_profile_id")
            != record["resource_profile"]["profile_id"]
            or request.get("requested", {}).get("task_name") != graph["task_name"]
            or (manifest and manifest.get("graph_fingerprint") != graph["graph_fingerprint"])
            or (manifest and manifest.get("bridge_sha256") != record["bridge"]["sha256"])
            or (manifest and manifest.get("source_commit") != record["source_commit"])
            or (manifest and manifest.get("task_sha256") != graph["task_sha256"])
            or (
                manifest
                and manifest.get("capability_manifest_sha256")
                != graph["capability_manifest_sha256"]
            )
            or (
                manifest
                and manifest.get("resource_profile_id") != record["resource_profile"]["profile_id"]
            )
            or (
                manifest
                and manifest.get("resolved_modules", {}).get("id") != graph["controller"]["id"]
            )
            or any(
                runtime_binding.get(field) != value
                for field, value in campaign_binding(record, graph, attempt_path).items()
            )
        ):
            raise ValueError("paired timing attempt receipt differs from its frozen graph")
        attempt_data = json.loads(attempt_file.read_text(encoding="utf-8"))
        if attempt_data.get("overall_status") != event.get("overall_status"):
            raise ValueError("paired timing event status differs from its attempt receipt")
        end_to_end = attempt_data.get("end_to_end", {})
        if event.get("end_to_end_wall_seconds") != end_to_end.get("wall_seconds") or event.get(
            "worker_wall_seconds"
        ) != end_to_end.get("worker_wall_seconds"):
            raise ValueError("paired timing event measurement differs from its attempt receipt")
        executed_binary = (
            attempt_data.get("preparation_receipt", {})
            .get("adapter_receipt", {})
            .get("executable_sha256")
        )
        if executed_binary not in (None, record["native_policy"]["sha256"]):
            raise ValueError("paired timing attempt used a different native policy binary")
        if runtime_binding.get("executed_native_policy_bridge_sha256") != executed_binary:
            raise ValueError("paired timing runtime binding differs from the executed binary")

    for _key, event in existing.items():
        graph = event_graph(event)
        if (
            event.get("graph_id") != graph["graph_id"]
            or event.get("graph_fingerprint") != graph["graph_fingerprint"]
            or event.get("task_sha256") != graph["task_sha256"]
            or event.get("controller_id") != graph["controller"]["id"]
        ):
            raise ValueError("paired timing event graph identity differs from its freeze")
        if event.get("state") == "completed":
            validate_completed_event(event)

    for key, event in list(existing.items()):
        if event.get("state") != "started":
            continue
        graph = event_graph(event)
        attempts = []
        for request_path in (output_root / graph["task_name"] / "attempts").glob("*/request.json"):
            try:
                request = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                request.get("source_commit") == record["source_commit"]
                and request.get("requested", {}).get("graph_id") == graph["graph_id"]
                and request.get("requested", {}).get("resource_profile_id")
                == record["resource_profile"]["profile_id"]
                and request_path.stat().st_mtime_ns >= event.get("started_unix_ns", 0)
            ):
                attempts.append(request_path.parent.resolve())
        if len(attempts) == 1:
            attempt_path = attempts[0]
            write_campaign_runtime_sidecar(attempt_path, record, graph)
            attempt_data = json.loads((attempt_path / "attempt.json").read_text(encoding="utf-8"))
            event.update(
                {
                    "state": "completed",
                    "attempt": str(attempt_path),
                    "attempt_sha256": sha256_file(attempt_path / "attempt.json"),
                    "run_manifest_sha256": sha256_file(attempt_path / "run-manifest.json")
                    if (attempt_path / "run-manifest.json").is_file()
                    else None,
                    "campaign_runtime_sha256": sha256_file(attempt_path / "campaign-runtime.json"),
                    "overall_status": attempt_data.get("overall_status", "incomplete"),
                    "algorithm_status": attempt_data.get("algorithm_status", "incomplete"),
                    "postcheck_status": attempt_data.get("postcheck_status", "not_run"),
                    "render_status": attempt_data.get("render_status", "not_run"),
                    "end_to_end_wall_seconds": attempt_data.get("end_to_end", {}).get(
                        "wall_seconds"
                    ),
                    "worker_wall_seconds": attempt_data.get("end_to_end", {}).get(
                        "worker_wall_seconds"
                    ),
                    "resumed_interrupted_attempt": True,
                    "completed_unix_ns": time.time_ns(),
                }
            )
        else:
            event.update(
                {
                    "state": "interrupted",
                    "interruption_reason": "no unique durable common-runner attempt matched the start event",
                    "candidate_attempt_count": len(attempts),
                    "completed_unix_ns": time.time_ns(),
                }
            )
        append_event(events_path, event)
        existing[key] = event
        if event["state"] == "completed":
            validate_completed_event(event)

    claim = f"paired timing; {repetitions} measured repetitions per method; alternating order"
    scheduled = 0
    for task in tasks:
        for scheduled_row in paired_method_schedule(repetitions):
            for side in scheduled_row["order"]:
                sample_key = (task, scheduled_row["phase"], scheduled_row["repetition"], side)
                prior = [key for key in existing if key[:4] == sample_key]
                completed = [
                    existing[key] for key in prior if existing[key].get("state") == "completed"
                ]
                if completed:
                    continue
                try_index = max((key[4] for key in prior), default=0) + 1
                key = (*sample_key, try_index)
                item = graphs_by_task[task][side]
                event = {
                    "schema": "csl.closed-loop-paired-timing-event/2",
                    **expected_identity,
                    "task_name": task,
                    "phase": scheduled_row["phase"],
                    "repetition": scheduled_row["repetition"],
                    "try_index": try_index,
                    "order_index": len(existing),
                    "side": side,
                    "graph_id": item["graph_id"],
                    "graph_fingerprint": item["graph_fingerprint"],
                    "task_sha256": item["task_sha256"],
                    "controller_id": controllers[side],
                    "started_unix_ns": time.time_ns(),
                    "state": "started",
                }
                append_event(events_path, event)
                result = run_frozen_attempt(
                    task,
                    output_root,
                    bridge,
                    native_policy_bridge,
                    record["resource_profile"],
                    item,
                    ROOT / item["catalogue_path"],
                    measurement_claim=claim,
                )
                attempt_path = Path(result["attempt"])
                write_campaign_runtime_sidecar(attempt_path, record, item)
                attempt_data = json.loads(
                    (attempt_path / "attempt.json").read_text(encoding="utf-8")
                )
                event.update(
                    {
                        "state": "completed",
                        "attempt": str(attempt_path),
                        "attempt_sha256": sha256_file(attempt_path / "attempt.json"),
                        "run_manifest_sha256": sha256_file(attempt_path / "run-manifest.json")
                        if (attempt_path / "run-manifest.json").is_file()
                        else None,
                        "campaign_runtime_sha256": sha256_file(
                            attempt_path / "campaign-runtime.json"
                        ),
                        "overall_status": attempt_data.get("overall_status"),
                        "algorithm_status": attempt_data.get("algorithm_status"),
                        "postcheck_status": attempt_data.get("postcheck_status"),
                        "render_status": attempt_data.get("render_status"),
                        "end_to_end_wall_seconds": attempt_data.get("end_to_end", {}).get(
                            "wall_seconds"
                        ),
                        "worker_wall_seconds": attempt_data.get("end_to_end", {}).get(
                            "worker_wall_seconds"
                        ),
                        "completed_unix_ns": time.time_ns(),
                    }
                )
                append_event(events_path, event)
                existing[key] = event
                scheduled += 1
                validate_completed_event(event)

    completed_samples: dict[tuple[str, str, int, str], dict] = {}
    for key, event in existing.items():
        if event.get("state") == "completed":
            completed_samples[key[:4]] = event

    summaries: dict[str, dict] = {}
    for task in tasks:
        summaries[task] = {}
        for side in ("A", "B"):
            rows = [
                event
                for (event_task, phase, _repetition, event_side), event in completed_samples.items()
                if event_task == task and phase == "measured" and event_side == side
            ]
            rows.sort(key=lambda event: event["repetition"])
            values = [
                row["end_to_end_wall_seconds"]
                for row in rows
                if row.get("overall_status") == "complete"
                and isinstance(row.get("end_to_end_wall_seconds"), (int, float))
            ]
            summaries[task][side] = {
                "method": controllers[side],
                "measured_attempts": len(rows),
                "successful_timed_attempts": len(values),
                "failures_or_incomplete": [
                    {
                        "repetition": row["repetition"],
                        "status": row.get("overall_status"),
                        "attempt": row.get("attempt"),
                    }
                    for row in rows
                    if row.get("overall_status") != "complete"
                ],
                "end_to_end_wall_seconds": {
                    "median": statistics.median(values) if values else None,
                    "range": [min(values), max(values)] if values else None,
                    "samples": values,
                },
                "attempts": [
                    {
                        "repetition": row["repetition"],
                        "attempt": row.get("attempt"),
                        "sha256": row.get("attempt_sha256"),
                        "status": row.get("overall_status"),
                        "wall_seconds": row.get("end_to_end_wall_seconds"),
                    }
                    for row in rows
                ],
            }
    comparison_records: dict[str, str] = {}
    for task in tasks:
        pack_request = build_comparison_pack_request(
            record,
            task,
            graphs_by_task[task],
            completed_samples,
            repetitions,
        )
        request_path = output_root / f"{task}-comparison-pack-request.json"
        write_json_atomically(request_path, pack_request)
        completed = subprocess.run(
            [str(comparison_packer.resolve(strict=True)), str(request_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        comparison_path = output_root / f"{task}-comparison-record.json"
        comparison_path.write_text(completed.stdout, encoding="utf-8")
        comparison_records[task] = str(comparison_path)

    summary = {
        "schema": "csl.closed-loop-paired-timing-summary/1",
        "source_commit": record["source_commit"],
        "freeze_sha256": freeze_sha256,
        "native_policy_sha256": record["native_policy"]["sha256"],
        "bridge_sha256": record["bridge"]["sha256"],
        "resource_profile": record["resource_profile"],
        "measured_repetitions_per_method": repetitions,
        "warmups_per_method": 1,
        "order": "AB for odd repetitions; BA for even repetitions; warmup AB per task",
        "controllers": controllers,
        "scope": "runner end-to-end wall time includes worker launch, execution, independent CSL replay, bounded checker processes, and rendering; worker wall is reported per attempt",
        "claim": "No ranking unless correctness and limiter evidence support it.",
        "limiter_profile": "not collected",
        "tasks": summaries,
        "comparison_records": comparison_records,
        "events": str(events_path),
        "attempts_executed_this_invocation": scheduled,
    }
    summary_path = output_root / "paired-timing-summary.json"
    write_json_atomically(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    return summary


def _representation_pair_differences(graph_a: dict, graph_b: dict) -> dict:
    role_a = graph_a.get("role_bindings", {})
    role_b = graph_b.get("role_bindings", {})
    controller_a = graph_a.get("controller", {})
    controller_b = graph_b.get("controller", {})
    return {
        "changed_role_bindings": {
            key: {"A": role_a.get(key), "B": role_b.get(key)}
            for key in sorted(set(role_a) | set(role_b))
            if role_a.get(key) != role_b.get(key)
        },
        "changed_controller_fields": sorted(
            key
            for key in set(controller_a) | set(controller_b)
            if controller_a.get(key) != controller_b.get(key)
        ),
    }


def run_fixed_tail_representation_matrix(
    record: dict,
    freeze_path: Path,
    output_root: Path,
    bridge: Path,
    native_policy_bridge: Path,
    comparison_packer: Path,
    repetitions: int = 5,
) -> dict:
    """Run every pair among the five admitted fixed-tail representations."""
    if repetitions < 5:
        raise ValueError("comparison-program timing requires at least five measured repetitions")
    output_root.mkdir(parents=True, exist_ok=True)
    pairs = fixed_tail_representation_pairs()
    expected_pairs = [f"{left}-vs-{right}" for left, right in pairs]
    graphs = {(item["task_name"], item["controller"]["id"]): item for item in record["graphs"]}
    comparisons = []
    summary_path = output_root / "representation-matrix-summary.json"
    summary = {
        "schema": "csl.closed-loop-fixed-tail-representation-matrix/1",
        "source_commit": record["source_commit"],
        "freeze_sha256": sha256_file(freeze_path),
        "native_policy_sha256": record["native_policy"]["sha256"],
        "bridge_sha256": record["bridge"]["sha256"],
        "resource_profile": record["resource_profile"],
        "representations": list(FIXED_TAIL_REPRESENTATIONS),
        "pair_count": len(pairs),
        "task_pair_count": len(pairs) * len(TASK_NAMES),
        "measured_repetitions_per_method": repetitions,
        "warmups_per_method": 1,
        "planned_measured_attempts": len(pairs) * len(TASK_NAMES) * 2 * repetitions,
        "planned_warmup_attempts": len(pairs) * len(TASK_NAMES) * 2,
        "pair_order": expected_pairs,
        "comparison_scope": (
            "Task, action, execution, control optimizer and solver are matched. Per-pair role and "
            "controller differences are retained, so timings compare full profiles rather than "
            "isolating a representation effect when associated geometry wiring also changes."
        ),
        "limiter_profile": "not collected",
        "claim": "paired descriptive timings; no ranking unless correctness and limiter evidence support it",
        "comparisons": comparisons,
    }
    write_json_atomically(summary_path, summary)

    for representation_a, representation_b in pairs:
        controller_a = fixed_tail_controller_id(representation_a)
        controller_b = fixed_tail_controller_id(representation_b)
        pair_id = f"{representation_a}-vs-{representation_b}"
        pair_output = output_root / "pairs" / pair_id
        per_task_differences = {}
        for task in TASK_NAMES:
            try:
                graph_a = graphs[(task, controller_a)]
                graph_b = graphs[(task, controller_b)]
            except KeyError as error:
                raise ValueError(
                    f"representation matrix is missing {error.args[0][0]} {error.args[0][1]}"
                ) from error
            per_task_differences[task] = _representation_pair_differences(graph_a, graph_b)

        pair_summary = run_paired_timing(
            record,
            freeze_path,
            pair_output,
            bridge,
            native_policy_bridge,
            comparison_packer,
            repetitions,
            controller_a,
            controller_b,
        )
        comparisons.append(
            {
                "pair_id": pair_id,
                "representation_a": representation_a,
                "representation_b": representation_b,
                "controller_a": controller_a,
                "controller_b": controller_b,
                "matched_fields": [
                    "task id and hash",
                    "action profile",
                    "execution profile",
                    "control optimizer",
                    "solver",
                ],
                "other_profile_field_differences_by_task": per_task_differences,
                "output_root": str(pair_output),
                "comparison_records": pair_summary["comparison_records"],
                "tasks": pair_summary["tasks"],
                "attempts_executed_this_invocation": pair_summary[
                    "attempts_executed_this_invocation"
                ],
            }
        )
        write_json_atomically(summary_path, summary)
    summary["summary_path"] = str(summary_path)
    return summary


def build_comparison_pack_request(
    record: dict,
    task_name: str,
    methods: dict[str, dict],
    events: dict[tuple[str, str, int, str], dict],
    repetitions: int,
) -> dict:
    """Build an OBS-04 pack request from validated paired attempts."""
    task = load_task(task_name)
    manifest_text = json.dumps(task, sort_keys=True, separators=(",", ":"), allow_nan=False)
    manifest_digest = hashlib.sha256(manifest_text.encode()).hexdigest()
    problem_id = f"csl.problem.v1.sha256:{manifest_digest}"
    request_descriptor = {
        "schema": "csl.closed-loop-paired-timing-request/1",
        "task_sha256": manifest_sha256(task),
        "source_commit": record["source_commit"],
        "resource_profile": record["resource_profile"],
        "warmups_per_method": 1,
        "measured_repetitions": repetitions,
        "order": "AB for odd repetitions; BA for even repetitions; warmup AB",
    }
    request_digest = hashlib.sha256(
        json.dumps(request_descriptor, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    method_rows = []
    for side in ("A", "B"):
        graph = methods[side]
        attempts = []
        graph_controller = graph["controller"]
        source_records = graph["source_files"]
        for repetition in range(1, repetitions + 1):
            event = events[(task_name, "measured", repetition, side)]
            attempt_path = Path(event["attempt"])
            attempt_data = json.loads((attempt_path / "attempt.json").read_text(encoding="utf-8"))
            runtime_binary = (
                attempt_data.get("preparation_receipt", {})
                .get("adapter_receipt", {})
                .get("executable_sha256")
            )
            if not runtime_binary:
                runtime_binary = record["native_policy"]["sha256"]
            build_profile = record["native_policy"]["build_profile"]
            runtime = {
                "language": "C++ and Python",
                "implementation": "CSL closed-loop native fixed-tail policy",
                "version": graph_controller["version"],
                "executable_sha256": runtime_binary,
                "os": platform.system(),
                "architecture": platform.machine(),
                "compiler": build_profile["cxx_compiler_id"],
                "compiler_version": build_profile["cxx_compiler_version"],
                "build_type": build_profile["build_type"],
            }
            status = attempt_data.get("overall_status", "incomplete")
            if status == "complete":
                status = "completed"
            attempts.append(
                {
                    "run_id": attempt_data["attempt_id"],
                    "runtime": runtime,
                    "status": status,
                    "result": attempt_data,
                    "measurement": {
                        "schema": "csl.closed-loop-paired-timing-event/1",
                        "status": "passed" if status == "completed" else status,
                        "strategy": graph_controller["id"],
                        "instrumentation": "disabled",
                        "repetition": repetition,
                        "warmup": False,
                        "order_index": event["order_index"],
                        "end_to_end_wall_seconds": event.get("end_to_end_wall_seconds"),
                        "worker_wall_seconds": event.get("worker_wall_seconds"),
                    },
                }
            )
        method_rows.append(
            {
                "id": graph_controller["id"],
                "version": graph_controller["version"],
                "configuration_id": "csl.config.v1.sha256:" + graph["graph_fingerprint"],
                "sources": source_records,
                "deviations_sha256": None,
                "attempts": attempts,
            }
        )
    arms = [
        {
            "configuration_id": method["configuration_id"],
            "strategy": method["id"],
            "instrumentation": "disabled",
        }
        for method in method_rows
    ]
    comparison_spec = {
        "schema": "csl.comparison-spec/2",
        "problem_id": problem_id,
        "request_digest": request_digest,
        "repetitions": repetitions,
        "input_manifest_hash": manifest_digest,
        "input_manifest_source": "resolved-problem-canonical-bytes",
        "arms": arms,
    }
    return {
        "schema": "csl.comparison-pack-request/1",
        "manifest": manifest_text,
        "input_manifest_schema": "resolved-problem-canonical-bytes",
        "request_digest": request_digest,
        "comparison_spec": comparison_spec,
        "methods": method_rows,
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
    paired_parser = commands.add_parser(
        "paired-timing", help="run alternating repetitions for a frozen controller pair"
    )
    paired_parser.add_argument("--freeze", type=Path, required=True)
    paired_parser.add_argument("--bridge", type=Path, required=True)
    paired_parser.add_argument("--native-policy-bridge", type=Path, required=True)
    paired_parser.add_argument("--native-policy-cache", type=Path, required=True)
    paired_parser.add_argument("--output-root", type=Path, required=True)
    paired_parser.add_argument("--comparison-packer", type=Path, required=True)
    paired_parser.add_argument("--repetitions", type=positive_integer, default=5)
    paired_parser.add_argument("--controller-a", default=fixed_tail_controller_id("polytope"))
    paired_parser.add_argument("--controller-b", default=fixed_tail_controller_id("zonotope"))
    matrix_parser = commands.add_parser(
        "representation-matrix",
        help="run all pairwise fixed-tail representation timings on the three tasks",
    )
    matrix_parser.add_argument("--freeze", type=Path, required=True)
    matrix_parser.add_argument("--bridge", type=Path, required=True)
    matrix_parser.add_argument("--native-policy-bridge", type=Path, required=True)
    matrix_parser.add_argument("--native-policy-cache", type=Path, required=True)
    matrix_parser.add_argument("--output-root", type=Path, required=True)
    matrix_parser.add_argument("--comparison-packer", type=Path, required=True)
    matrix_parser.add_argument("--repetitions", type=positive_integer, default=5)
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
        elif args.command == "run":
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
        elif args.command == "paired-timing":
            record = read_freeze(
                args.freeze, args.bridge, args.native_policy_bridge, args.native_policy_cache
            )
            result = run_paired_timing(
                record,
                args.freeze.resolve(),
                args.output_root.resolve(),
                args.bridge.resolve(),
                args.native_policy_bridge.resolve(),
                args.comparison_packer.resolve(),
                args.repetitions,
                args.controller_a,
                args.controller_b,
            )
        else:
            record = read_freeze(
                args.freeze, args.bridge, args.native_policy_bridge, args.native_policy_cache
            )
            result = run_fixed_tail_representation_matrix(
                record,
                args.freeze.resolve(strict=True),
                args.output_root.resolve(),
                args.bridge.resolve(strict=True),
                args.native_policy_bridge.resolve(strict=True),
                args.comparison_packer.resolve(strict=True),
                args.repetitions,
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
