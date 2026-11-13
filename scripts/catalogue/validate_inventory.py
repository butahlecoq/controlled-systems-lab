#!/usr/bin/env python3
"""Check catalogue identity provenance and the independently expected inventory."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

EXPECTED_HULL_IDS = {
    "csl.hull.lp-membership",
    "csl.hull.phase-one-basis-bulk",
    "csl.hull.ordered-membership",
    "csl.hull.grouped-membership",
    "csl.hull.recursive-split-merge",
    "csl.hull.itis17.a43-certified-basis-reuse",
    "csl.hull.itis17.a43-artificial-basis",
    "csl.hull.itis17.a43-largest-norm-tie",
    "csl.hull.itis17.a44-incremental-lp",
    "csl.hull.itis17.a44-paper-farthest-incremental-lp",
}
EXPECTED_LEGACY_SYMBOLS = {
    "csl::geometry::legacy_btulshor::modif",
    "csl::geometry::legacy_btulshor::kpabep",
    "csl::geometry::legacy_btulshor::reach",
}
EXPECTED_SOURCE_INDEX_IDS = {
    "csl.hull.source.quickhull-2d",
    "csl.hull.source.btulshor-kpabep",
}
EXPECTED_GROUPS = {
    "vertex_lp_simplex",
    "reachable_set_representation",
    "controller",
    "supporting_operations",
}


def check_candidate_source(root: Path, row: dict) -> None:
    source = row["source"]
    if source.startswith("https://"):
        assert re.fullmatch(
            r"https://github\.com/butahlecoq/controlled-systems-lab/blob/[0-9a-f]{40}/docs/[a-zA-Z0-9_./-]+\.md",
            source,
        ), f"candidate rationale must use a pinned repository source: {source}"
        assert re.fullmatch(r"[0-9a-f]{64}", row.get("source_sha256", "")), (
            f"historical candidate rationale needs a byte hash: {source}"
        )
    else:
        source_path = root / source
        assert source_path.is_file(), f"missing candidate rationale source: {source_path}"


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    path = root / "docs/catalogue/module-composition-inventory-v1.json"
    data = json.loads(path.read_text())
    assert data["schema"] == "csl.module-composition-inventory/1"
    assert set(group["id"] for group in data["groups"]) == EXPECTED_GROUPS
    records = data["modules"]
    assert len(records) >= 30, f"inventory unexpectedly short: {len(records)}"
    hull_ids = {
        row["identity"]["id"]
        for row in records
        if row["group"] == "vertex_lp_simplex"
        and row["kind"] == "registered_provider"
        and row["identity"]["id"].startswith("csl.hull.")
        and not row["identity"]["id"].startswith("csl.hull.source.")
    }
    assert hull_ids == EXPECTED_HULL_IDS, f"hull registry mismatch: {hull_ids ^ EXPECTED_HULL_IDS}"
    source_index_ids = {
        row["identity"]["id"]
        for row in records
        if row["group"] == "vertex_lp_simplex"
        and row["kind"] == "registered_provider"
        and row["identity"]["id"].startswith("csl.hull.source.")
    }
    assert source_index_ids == EXPECTED_SOURCE_INDEX_IDS, (
        f"source-index registry mismatch: {source_index_ids ^ EXPECTED_SOURCE_INDEX_IDS}"
    )
    legacy_symbols = {
        row["identity"]["symbol"] for row in records if row.get("route", "").startswith("faithful_")
    }
    assert legacy_symbols == EXPECTED_LEGACY_SYMBOLS
    assert {
        "admitted",
        "incompatible",
        "implementation_missing",
        "backend_unavailable",
        "excluded",
    } == set(data["canonicalization"]["required_statuses"])
    assert {row["status"] for row in data["known_candidate_classifications"]} == {
        "incompatible",
        "implementation_missing",
        "excluded",
    }

    for row in records:
        for field in ("group", "kind", "identity", "role", "source", "build"):
            assert field in row, f"missing {field} in inventory row {row.get('identity')}"
        source = row["source"]
        source_path = root / source["path"]
        assert source_path.is_file(), f"missing source provenance: {source_path}"
        content = source_path.read_text(errors="replace")
        if "implementation_path" in source:
            implementation_path = root / source["implementation_path"]
            assert implementation_path.is_file(), (
                f"missing implementation source: {implementation_path}"
            )
            content += implementation_path.read_text(errors="replace")
        identity = row["identity"]
        if row["kind"] == "registered_provider":
            assert identity["id"] in content, (
                f"unverified provider ID {identity['id']} in {source_path}"
            )
            assert identity["version"] in content, (
                f"unverified version {identity['version']} in {source_path}"
            )
        elif row["kind"] == "external_program_route":
            assert source["path"] == identity["symbol"]
        else:
            symbol = identity["symbol"].split("::")[-1]
            assert symbol in content, (
                f"unverified public symbol {identity['symbol']} in {source_path}"
            )
        if "version" in identity and row["kind"] != "registered_provider":
            raise AssertionError(f"public route has invented module version: {identity}")

    for row in data["known_candidate_classifications"]:
        check_candidate_source(root, row)
        assert row["first_unmet"]["field"] and row["first_unmet"]["reason"]

    optimizer_roles = [row for row in records if row.get("role") == "terminal_optimizer"]
    vertex_roles = [row for row in records if row.get("role") == "vertex_lp_provider"]
    assert optimizer_roles and vertex_roles
    assert all(row["source"]["path"] != "src/geometry/hull_reducer.cpp" for row in optimizer_roles)
    print(
        f"inventory source check passed: {len(records)} records, {len(hull_ids)} HullReducerPort IDs, "
        f"{len(source_index_ids)} source-index IDs, "
        f"{len(legacy_symbols)} faithful BTULSHOR symbols"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
