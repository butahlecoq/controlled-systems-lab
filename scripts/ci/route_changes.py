"""Route complete Git diffs through conservative native/report validation gates."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

# Ownership map: mutable Pages shells, report companions and their presentation
# tests. These Python renderers read saved inputs but never define native targets.
# Keep numerical collectors, validators and test drivers outside this list.
PRESENTATION_FILES = {
    "docs/examples/examples.css",
    "docs/examples/continuous-policy-2d.html",
    "docs/examples/fixed-plan-minimax-2d.html",
    "docs/examples/fuel-b06-viz03.html",
    "docs/examples/fuel-b06-viz06.html",
    "docs/examples/adaptive-ode-replay.html",
    "docs/examples/b04-reference-trajectory-projections.html",
    "docs/examples/viz04-replay-comparison.html",
    "docs/examples/viz10/index.html",
    "docs/examples/fuel-reachability-layers/index.html",
    "scripts/reports/site_design.py",
    "scripts/reports/landing.py",
    "scripts/reports/visual_examples.py",
    "scripts/reports/geometry_opt_companions.py",
    "scripts/reports/control_witness_companions.py",
    "scripts/reports/approx_extension_companions.py",
    "scripts/reports/viz10_plot_companions.py",
    "scripts/reports/fuel_reachability_layers.py",
    "scripts/reports/render_adaptive_ode_example.py",
    "scripts/reports/visual-route-inventory.json",
    "scripts/reports/mpc01/b04_projection_example.py",
    "tests/reporting/test_visual_examples.py",
    "tests/reporting/test_visual_route_inventory.py",
    "tests/reporting/test_render_adaptive_ode_example.py",
    "tests/reporting/test_fuel_reachability_layers.py",
    "tests/reporting/test_viz10_plot_companions.py",
    "tests/reporting/test_landing.py",
}
SAVED_REPORTS = "reports/algorithm-results/"
EXECUTABLE_REPORT_TOOLS = SAVED_REPORTS + "tooling/"


def classify(paths):
    """Unknown paths require both gates; an empty diff proves no exemption."""
    native = not paths
    reports = not paths
    for path in paths:
        if path in PRESENTATION_FILES:
            reports = True
        elif path.startswith(SAVED_REPORTS) and not path.startswith(EXECUTABLE_REPORT_TOOLS):
            reports = True
        elif path.endswith(".md"):
            continue
        else:
            native = reports = True
    return native, reports


def changed_paths(event_name, event):
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
        head = event["pull_request"]["head"]["sha"]
        comparison = f"{base}...{head}"
    elif event_name == "push":
        base, head = event["before"], event["after"]
        comparison = f"{base}..{head}"
    else:
        raise ValueError("manual or unknown event requires both gates")
    # Only object IDs from the event enter the revision expression, never refs
    # or shell text. Both sides of a rename count as changed paths.
    if any(
        len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha) or sha == "0" * 40
        for sha in (base, head)
    ):
        raise ValueError("event has no usable source object IDs")
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", "--no-renames", comparison, "--"],
        check=True,
        capture_output=True,
    )
    if not result.stdout:
        return []
    return result.stdout.decode("utf-8", errors="surrogateescape").rstrip("\0").split("\0")


def main():
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        paths = changed_paths(os.environ["GITHUB_EVENT_NAME"], event)
        native, reports = classify(paths)
        reason = f"classified {len(paths)} changed paths from the complete Git diff"
    except (KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        native = reports = True
        reason = f"conservative fallback ({type(error).__name__})"
    output = f"native={str(native).lower()}\nreports={str(reports).lower()}\n"
    print(output + reason)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(output)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(f"Native matrix: **{native}**; reporting: **{reports}**. {reason}.\n")


if __name__ == "__main__":
    main()
