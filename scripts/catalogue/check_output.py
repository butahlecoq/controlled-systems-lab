#!/usr/bin/env python3
"""Exercise the native four-group inventory and compiled hull-provider receipt CLI."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    executable = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    completed = subprocess.run(
        [str(executable), "--inventory", str(root / "docs/catalogue/module-composition-inventory-v1.json")],
        check=True, capture_output=True, text=True,
    )
    output = json.loads(completed.stdout)
    assert output["schema"] == "csl.module-composition-output/1"
    assert set(group["id"] for group in output["inventory"]["groups"]) == {
        "vertex_lp_simplex", "reachable_set_representation", "controller", "supporting_operations"
    }
    rows = output["candidates"]
    expected_rows = 10 * (2 if output["compiled_backends"]["highs"] else 1)
    assert len(rows) == expected_rows, f"candidate universe mismatch: {len(rows)} != {expected_rows}"
    assert all(row["status"] == "admitted" for row in rows)
    assert len({row["graph_id"] for row in rows}) == len(rows)
    for row in rows:
        active = row["active_roles"]
        providers = row["prepared_providers"]
        assert active["terminal_optimizer"] == "not_used"
        assert {provider["actual"] for provider in providers} == {
            active["vertex_reducer"]["id"], active["vertex_lp_provider"]["id"]
        }
        assert all(provider["actual"] == provider["requested"] for provider in providers)
        assert row["attempt"] == "completed", row
        assert row["retained"] == [0, 1, 2, 3], row
        if active["vertex_reducer"]["id"] == "csl.hull.lp-membership":
            assert row["outer_lp_runner_queries"], "LP membership fixture produced no calls"
        for query in row["outer_lp_runner_queries"]:
            assert query["status"] == "completed", query
            assert query["actual"] == active["vertex_lp_provider"]["id"], query
            assert query["version"] == active["vertex_lp_provider"]["version"], query
    controller_rows = output["controller_candidates"]
    assert len(controller_rows) == 1
    controller = controller_rows[0]
    assert controller["strategy"] == "csl.synthesis.ts01-analytic"
    assert controller["status"] == "admitted"
    assert controller["reprepare"] == "admitted"
    assert controller["prepared_providers"][0]["actual"] == controller["strategy"]
    print(f"native composition catalogue passed: {len(rows)} admitted concrete graphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
