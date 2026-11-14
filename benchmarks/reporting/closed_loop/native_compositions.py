"""Enumerate source-bound backward graph requests without changing default profiles."""

from __future__ import annotations

import copy
import hashlib
import json

from capabilities import MODULE_INVENTORY, _catalogue_sources, build_native_manifest
from contracts import ROOT, canonical_sha256, load_task


def build_manifest() -> dict:
    inventory = json.loads(MODULE_INVENTORY.read_text())
    registered = [m for m in inventory["modules"] if m["kind"] == "registered_provider"]
    hulls = [
        m for m in registered
        if m["identity"].get("id", "").startswith("csl.hull.")
        and not m["identity"]["id"].startswith("csl.hull.source.")
    ]
    source_hulls = [
        m for m in registered
        if m["identity"].get("id", "").startswith("csl.hull.source.")
    ]
    lps = [m for m in registered if m["role"] == "vertex_lp_provider"]
    hashes: dict[str, str] = {}

    def source_hash(path: str) -> str:
        if path not in hashes:
            hashes[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        return hashes[path]

    candidates = []
    graphs = []
    defaults = build_native_manifest()["graphs"]
    for base in defaults:
        if base["controller"]["control_semantics"] != "backward-graph":
            continue
        task_name = (
            base["task_id"].split("/")[0]
            if base["task_id"].startswith("syn-") else "earth-orbit"
        )
        dimension = len(load_task(task_name)["model"]["states"])
        default_options = base["controller"]["factory_options"]
        for hull in hulls + source_hulls:
            source_index = hull in source_hulls
            for lp in ([None] if source_index else lps):
                options = copy.deepcopy(default_options)
                options["reachable_set_method"] = {
                    "id": "csl.geometry.affine-sum.source-index" if source_index
                    else "csl.geometry.affine-sum",
                    "version": "1.0.0",
                }
                options["hull_provider"] = hull["identity"]
                options["vertex_lp_provider"] = "not_used" if lp is None else lp["identity"]
                if lp is not None and lp["identity"]["id"] == "phase-one-priority-tie":
                    options["vertex_lp_priority_policy"] = "structural-column-index/v1"
                candidate = {
                    "task_id": base["task_id"],
                    "task_sha256": base["task_sha256"],
                    "controller_id": base["controller"]["id"],
                    "dimension": dimension,
                    "factory_options": options,
                }
                candidate["candidate_id"] = "native-composition/" + canonical_sha256(candidate)
                if source_index and dimension != 2:
                    candidate.update({
                        "status": "incompatible",
                        "canonical_graph_id": None,
                        "reason": {
                            "field": "points.dimension",
                            "source": hull["source"]["path"],
                            "detail": "The source-index hull accepts 2D operands; no projection is inserted.",
                        },
                    })
                    candidates.append(candidate)
                    continue
                if options == default_options:
                    graph = copy.deepcopy(base)
                    candidate["canonicalization"] = "existing-default-graph"
                else:
                    graph = copy.deepcopy(base)
                    graph.pop("graph_id")
                    graph.pop("graph_fingerprint")
                    graph["controller"]["factory_options"] = options
                    roles = graph["role_bindings"]
                    roles["reachable_set_method"] = options["reachable_set_method"]
                    roles["hull_provider"] = options["hull_provider"]
                    roles["set_reducer"] = options["hull_provider"]
                    roles["vertex_lp"] = options["vertex_lp_provider"]
                    if source_index:
                        roles["geometry_checker"] = {
                            "status": "bounded exact represented-binary64 all-input hull check",
                            "budget": options["checker_budget"],
                        }
                    previous = set(_catalogue_sources(default_options))
                    selected = set(_catalogue_sources(options))
                    controller_paths = (
                        set(graph["controller"]["source_files"]) - previous
                    ) | selected
                    controller_paths.add(
                        "benchmarks/reporting/closed_loop/native_compositions.py"
                    )
                    graph["controller"]["source_files"] = sorted(controller_paths)
                    paths = controller_paths | set(graph["execution"]["source_files"])
                    graph["source_files"] = [
                        {"path": path, "sha256": source_hash(path)} for path in sorted(paths)
                    ]
                    graph["admission"]["basis"] = (
                        "Source-bound request through the existing native graph factory; "
                        "actual provider preparation and query outcomes are retained per attempt."
                    )
                    graph["graph_fingerprint"] = canonical_sha256(graph)
                    graph["graph_id"] = (
                        f"closed-loop/{task_name}/native-composition/1/"
                        f"cfg-{graph['graph_fingerprint'][:16]}"
                    )
                    candidate["canonicalization"] = "distinct-active-provider-tuple"
                candidate.update({
                    "status": "requestable",
                    "canonical_graph_id": graph["graph_id"],
                    "runtime_preparation": "required_per_attempt",
                })
                candidates.append(candidate)
                graphs.append(graph)
    return {
        "schema": "csl.closed-loop-capability-manifest/2",
        "manifest_id": "source-bound-native-backward-compositions/1",
        "registration_status": "source-frozen; runtime preparation required",
        "catalogue_parent": inventory["schema"],
        "scope": (
            "Native finite-action backward graph provider combinations only. "
            "This is one campaign segment, not the complete four-group universe."
        ),
        "claim_scope": (
            "Source requestability is not a successful native preparation, execution, "
            "correctness certificate or performance comparison."
        ),
        "source_files": [
            {"path": path, "sha256": source_hash(path)} for path in (
                str(MODULE_INVENTORY.relative_to(ROOT)),
                "benchmarks/reporting/closed_loop/native_compositions.py",
                "benchmarks/reporting/closed_loop/capabilities.py",
                "benchmarks/reporting/closed_loop/run_closed_loop.py",
            )
        ],
        "candidates": candidates,
        "graphs": graphs,
    }
