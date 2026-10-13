#!/usr/bin/env python3
"""Render an existing SYN-02 records.json without rebuilding or running a solver."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from collect import render_html, svg


def render(records: Path, out_dir: Path) -> None:
    payload = json.loads(records.read_text(encoding="utf-8"))
    if payload.get("schema") != "csl.syn02-terminal-report/1":
        raise ValueError("unsupported saved report schema")
    if not isinstance(payload.get("summary"), list) or len(payload["summary"]) != 5:
        raise ValueError("saved report must contain the five validated fixture summaries")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "latency.svg").write_text(svg(payload["summary"]), encoding="utf-8")
    (out_dir / "index.html").write_text(render_html(payload), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    render(args.records, args.out_dir)


if __name__ == "__main__":
    main()
