"""Check the warm-gap reading layer against immutable attempt/2 archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path, PurePosixPath


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _reject_constant(value: str):
    raise ValueError("Nonfinite JSON constant: " + value)


def _finite_float(value: str) -> float:
    result = float(value)
    _require(math.isfinite(result), "Nonfinite JSON number")
    return result


def _json(data: bytes):
    return json.loads(data, parse_constant=_reject_constant, parse_float=_finite_float)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(root: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    _require(
        not name.is_absolute()
        and bool(name.parts)
        and all(part not in {".", ".."} for part in name.parts),
        "Unsafe saved-wave path",
    )
    path = root.joinpath(*name.parts)
    _require(
        path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root),
        "Missing or unsafe saved-wave file",
    )
    return path


def _equal_cost(actual, reported) -> bool:
    if not isinstance(actual, dict) or not isinstance(reported, dict):
        return False
    for component in ("terminal", "running", "total"):
        left, right = actual.get(component), reported.get(component)
        if (
            type(left) not in (int, float)
            or type(right) not in (int, float)
            or not math.isfinite(left)
            or not math.isfinite(right)
            or not math.isclose(left, right, abs_tol=1e-12, rel_tol=1e-12)
        ):
            return False
    return True


def validate(bundle: Path) -> dict:
    """Verify delivery metadata without executing a model, controller or renderer."""
    _require(not bundle.is_symlink(), "Unsafe saved-wave directory")
    bundle = bundle.resolve(strict=True)
    expected_files = {}
    for line in _path(bundle, "files.sha256").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        _require(relative not in expected_files, "Duplicate saved-wave checksum entry")
        path = _path(bundle, relative)
        _require(_sha(path.read_bytes()) == digest, "Saved-wave file digest differs: " + relative)
        expected_files[relative] = digest
    actual_files = {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()}
    _require(
        actual_files == set(expected_files) | {"files.sha256"}, "Saved-wave file inventory differs"
    )
    index = _json(_path(bundle, "records.json").read_bytes())
    build = _json(_path(bundle, "source-build-receipt.json").read_bytes())
    _require(index["schema"] == "csl.closed-loop.saved-wave-index/1", "Unknown wave index")
    _require(
        index["source_commit"] == build["source_commit"]
        and index["sdk_source_commit"] == build["sdk_producer_commit"],
        "Saved-wave source/SDK identity differs",
    )
    records = index["records"]
    _require(len(records) == index["attempt_count"] == 16, "Saved-wave attempt count differs")
    _require(
        len({(r["task"], r["controller_id"]) for r in records})
        == index["unique_selected_profiles"]
        == 15,
        "Saved-wave profile universe differs",
    )
    completed = 0
    for record in records:
        directory = "records/" + record["id"] + "/"
        receipt = _json(_path(bundle, directory + "receipt.json").read_bytes())
        _require(
            record == {k: v for k, v in receipt.items() if k != "archive_members"},
            "Reading index differs from archive receipt",
        )
        archive_path = _path(bundle, directory + "raw.zip")
        _require(
            _sha(archive_path.read_bytes()) == record["archive_sha256"],
            "Saved-wave archive digest differs",
        )
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.namelist()
            _require(
                len(set(members)) == len(members)
                and set(members) == set(receipt["archive_members"]),
                "Archive inventory differs",
            )
            for name, expected in receipt["archive_members"].items():
                safe = PurePosixPath(name)
                _require(not safe.is_absolute() and ".." not in safe.parts, "Unsafe archive member")
                data = archive.read(name)
                _require(
                    len(data) == expected["bytes"]
                    and _sha(data) == expected["sha256"]
                    and f"{archive.getinfo(name).CRC:08x}" == expected["crc32"],
                    "Archive member differs",
                )
            attempt = _json(archive.read("attempt/attempt.json"))
            run = _json(archive.read("attempt/run-manifest.json"))
            graph = _json(archive.read("attempt/resolved-graph.json"))
        _require(attempt["schema"] == "csl.closed-loop.attempt/2", "Unknown raw attempt schema")
        for key in ("task_id", "task_sha256", "controller_id", "original_intervals"):
            _require(record[key] == attempt[key], "Raw attempt identity differs: " + key)
        _require(
            record["source_commit"] == run["source_commit"] == index["source_commit"]
            and record["sdk_source_commit"] == index["sdk_source_commit"]
            and record["task_sha256"] == build["tasks"][record["task"]]["task_sha256"]
            and record["completed_holds"] == attempt.get("completed_holds", 0),
            "Task, horizon or source binding differs",
        )
        task = build["tasks"][record["task"]]
        _require(
            attempt["original_intervals"] == task["episode"]["intervals"]
            and attempt["action_profile_id"]
            == graph["action_profile_id"]
            == task["continuous_control"]["problem_id"],
            "Original horizon or continuous action identity differs",
        )
        _require(
            record["native_sha256"]
            == build["bridge_binaries"]["history_policy"]
            == attempt["preparation_receipt"]["adapter_receipt"]["executable_sha256"]
            and record["physical_bridge_sha256"]
            == build["bridge_binaries"]["nonlinear_replay"]
            == run["bridge_sha256"],
            "Fresh installed bridge identity differs",
        )
        graph_body = {k: v for k, v in graph.items() if k not in {"graph_id", "graph_fingerprint"}}
        fingerprint = _sha(json.dumps(graph_body, sort_keys=True, separators=(",", ":")).encode())
        _require(
            fingerprint
            == record["graph_fingerprint"]
            == graph["graph_fingerprint"]
            == run["graph_fingerprint"]
            and record["graph_id"] == graph["graph_id"],
            "Raw graph fingerprint differs",
        )
        full = attempt.get("overall_status") == "complete"
        _require(record["full_episode"] is full, "Episode completion qualification differs")
        if full:
            completed += 1
            audit = record["audit"]
            _require(
                attempt["completed_holds"] == attempt["original_intervals"]
                and all(
                    attempt.get(k) == "complete"
                    for k in ("algorithm_status", "postcheck_status", "render_status")
                )
                and audit["full_episode"]
                and not audit["errors"]
                and audit["accepted_queries_checked"] == attempt["completed_holds"]
                and audit["warm_queries_checked"] == attempt["completed_holds"],
                "Incomplete episode presented as complete",
            )
            _require(
                _equal_cost(attempt["physical_objective"], record["physical_objective"])
                and _equal_cost(attempt["physical_objective"], audit["applied_original_objective"]),
                "Published score differs from raw physical objective",
            )
        else:
            _require(
                record["physical_objective"] is None and record["outcome"] != "complete",
                "Failed/prefix attempt advertises a complete score",
            )
    _require(completed == index["complete_profiles"] == 8, "Completed-profile count differs")
    figures = _json(_path(bundle, "figure-receipt.json").read_bytes())["figures"]
    _require(
        len(figures) == 32
        and {(f["record_id"], f["variant"]) for f in figures}
        == {(r["id"], variant) for r in records for variant in ("screen", "print")},
        "Missing or duplicate figure variant",
    )
    for figure in figures:
        _require(not figure["projection_failures"], "Unreported projection failure")
        for kind in ("svg", "png"):
            _require(
                _sha(_path(bundle, figure[kind]).read_bytes()) == figure[kind + "_sha256"],
                "Derived figure digest differs",
            )
    return {
        "attempts": len(records),
        "profiles": 15,
        "complete": completed,
        "accepted_queries": sum(
            (r["audit"] or {}).get("accepted_queries_checked", 0) for r in records
        ),
        "figures": len(figures),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    print(json.dumps(validate(parser.parse_args().bundle), sort_keys=True))
