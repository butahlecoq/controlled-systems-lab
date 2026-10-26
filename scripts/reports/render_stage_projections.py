"""Render a source-bound saved stage batch without executing a task or geometry."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reports.stage_projection_data import read_stage_projection_batch
from scripts.reports.stage_projection_figures import render_batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="saved csl.stage-projection-batch/1 JSON")
    parser.add_argument("--out", type=Path, required=True, help="new output directory")
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-problem-id", required=True)
    parser.add_argument("--expected-request-id", required=True)
    parser.add_argument("--expected-route-id", required=True)
    parser.add_argument("--expected-record-schema", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--style", type=Path,
                        default=ROOT / "scripts/reports/styles/control-v1.json")
    args = parser.parse_args()
    expected = {
        "expected_run_id": args.expected_run_id,
        "expected_problem_id": args.expected_problem_id,
        "expected_request_id": args.expected_request_id,
        "expected_route_id": args.expected_route_id,
        "expected_record_schema": args.expected_record_schema,
        "expected_source_sha256": args.expected_source_sha256,
    }
    batch = read_stage_projection_batch(args.input, **expected)
    paths = render_batch(batch, args.out.resolve(), style_path=args.style.resolve(strict=True))
    output = args.out.resolve(strict=True)
    print(f"index: {output / 'index.html'}")
    print(f"manifest: {output / 'render-manifest.json'}")
    for item in paths:
        print(f"{item['title']}: {output / item['svg']} | {output / item['png']}")


if __name__ == "__main__":
    main()
