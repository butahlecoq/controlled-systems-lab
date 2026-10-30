"""Render the saved public adaptive-ODE example as a deterministic SVG."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def load(path: Path) -> tuple[dict[str, str], list[dict[str, float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    metadata = dict(line[2:].split("=", 1) for line in lines if line.startswith("# "))
    rows = [{name: float(value) for name, value in row.items()}
            for row in csv.DictReader(line for line in lines if not line.startswith("# "))]
    if metadata.get("schema") != "csl.example.adaptive-ode-replay/1" or \
            metadata.get("method") != "adaptive_rk4_step_doubling" or len(rows) < 3:
        raise ValueError("unsupported or incomplete adaptive ODE replay record")
    if any(rows[i + 1]["time"] <= rows[i]["time"] for i in range(len(rows) - 1)):
        raise ValueError("replay times are not strictly increasing")
    error = max(math.hypot(row["x"] - row["reference_x"], row["y"] - row["reference_y"])
                for row in rows)
    if error > 2e-8:
        raise ValueError(f"adaptive replay exceeds the independent analytic comparison: {error}")
    return metadata, rows


def render(metadata: dict[str, str], rows: list[dict[str, float]]) -> str:
    left, right, top, bottom = 115.0, 685.0, 75.0, 535.0
    low, high = -1.2, 1.2

    def point(x: float, y: float) -> tuple[float, float]:
        return (left + (x-low)*(right-left)/(high-low),
                bottom - (y-low)*(bottom-top)/(high-low))

    def path(x_field: str, y_field: str) -> str:
        values = " ".join(f"{px:.3f},{py:.3f}" for px, py in
                          (point(row[x_field], row[y_field]) for row in rows))
        return values

    grid = []
    for value in (-1.0, -0.5, 0.0, 0.5, 1.0):
        x, y = point(value, value)
        grid.append(f'<line x1="{x:.3f}" y1="{top}" x2="{x:.3f}" y2="{bottom}" class="grid"/>')
        grid.append(f'<line x1="{left}" y1="{y:.3f}" x2="{right}" y2="{y:.3f}" class="grid"/>')
        grid.append(f'<text x="{x:.3f}" y="{bottom+24}" text-anchor="middle">{value:g}</text>')
        grid.append(f'<text x="{left-12}" y="{y+4:.3f}" text-anchor="end">{value:g}</text>')
    samples = []
    for row in rows[::8]:
        x, y = point(row["x"], row["y"])
        samples.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="4" class="sample"/>')
    final = rows[-1]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 650" role="img" '
            'aria-labelledby="title desc"><title id="title">Adaptive RK4 replay of a harmonic oscillator</title>'
            '<desc id="desc">The C++ adaptive RK4 trajectory follows the independent analytic unit circle in the x-y phase plane.</desc>'
            '<style>text{font:14px system-ui,sans-serif;fill:#d1d9cc}.grid{stroke:#647064;stroke-width:1;opacity:.55}'
            '.axis{stroke:#d1d9cc;stroke-width:1.5}.reference{fill:none;stroke:#d9ad68;stroke-width:3;stroke-dasharray:9 7}'
            '.replay{fill:none;stroke:#80b2d4;stroke-width:3}.sample{fill:#80b2d4;stroke:#172019;stroke-width:1.5}</style>'
            '<rect width="800" height="650" fill="#172019"/><text x="400" y="34" text-anchor="middle" font-size="20">Adaptive RK4 replay · phase plane</text>'
            + ''.join(grid) +
            f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" class="axis"/>'
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" class="axis"/>'
            f'<polyline points="{path("reference_x", "reference_y")}" class="reference"/>'
            f'<polyline points="{path("x", "y")}" class="replay"/>'
            + ''.join(samples) +
            '<text x="400" y="590" text-anchor="middle">x</text>'
            '<text x="35" y="305" text-anchor="middle" transform="rotate(-90 35 305)">y</text>'
            '<line x1="178" y1="625" x2="214" y2="625" class="replay"/><text x="222" y="630">CSL replay with accepted-step samples</text>'
            '<line x1="492" y1="625" x2="528" y2="625" class="reference"/><text x="536" y="630">analytic reference</text>'
            f'<text x="400" y="562" text-anchor="middle">x′=y, y′=−x; x(0)=1, y(0)=0; {metadata["interval_count"]} control intervals; '
            f'final error {float(metadata["final_state_error"]):.2e}</text></svg>')


def raw_record(metadata: dict[str, str], rows: list[dict[str, float]]) -> dict:
    return {
        "schema": "csl.visual-example/adaptive-ode-replay/1",
        "inputs": {"dynamics": ["x'=y", "y'=-x"], "initial_state": [1.0, 0.0],
                   "interval_count": int(metadata["interval_count"]),
                   "absolute_tolerance": float(metadata["absolute_tolerance"]),
                   "relative_tolerance": float(metadata["relative_tolerance"]),
                   "max_attempts_per_interval": int(metadata["max_attempts_per_interval"])},
        "answer": {"final_state": [rows[-1]["x"], rows[-1]["y"]],
                   "analytic_final_state": [rows[-1]["reference_x"], rows[-1]["reference_y"]],
                   "final_state_error": float(metadata["final_state_error"]),
                   "accepted_steps": int(metadata["accepted_steps"]),
                   "rejected_steps": int(metadata["rejected_steps"]),
                   "max_local_error_estimate": [float(metadata["max_local_error_estimate_x"]),
                                                float(metadata["max_local_error_estimate_y"])],
                   "error_scope": "Observed local step-doubling estimate; not a certified global error bound."},
        "trajectory": rows,
        "reproduction_command": "cmake -S examples -B build/examples -DCMAKE_PREFIX_PATH=<CSL-install-prefix> && cmake --build build/examples --target adaptive_ode_replay && build/examples/adaptive_ode_replay > docs/examples/adaptive-ode-replay.csv && python3 scripts/reports/render_adaptive_ode_example.py --record docs/examples/adaptive-ode-replay.csv --output docs/examples/adaptive-ode-replay.svg",
        "source_path": "examples/adaptive_ode_replay.cpp",
        "evidence": "Generated by the public CSL simulation replay client and checked against (cos(t),-sin(t)); this verifies a numerical trajectory only, not a control optimum.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metadata, rows = load(args.record)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(metadata, rows) + "\n", encoding="utf-8")
    record_path = args.output.with_suffix(".json")
    record_path.write_text(json.dumps(raw_record(metadata, rows), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
