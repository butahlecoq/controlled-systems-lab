"""Route complete Git diffs through conservative native/report validation gates."""

from __future__ import annotations

import json
import os
import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRESENTATION_FILES = {
    "docs/examples/examples.css",
    "docs/examples/continuous-policy-2d.html",
    "docs/examples/fixed-plan-minimax-2d.html",
    "docs/examples/fuel-b06-viz03.html",
    "docs/examples/fuel-b06-viz06.html",
    "docs/examples/adaptive-ode-replay.html",
    "examples/nominal_quadratic_history_2d.html",
    "examples/nominal_quadratic_history_2d.svg",
    "examples/nominal_quadratic_history_2d.csv",
    "examples/nominal_quadratic_history_2d-output.txt",
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
    "scripts/reports/stage_nominal_quadratic_history.py",
    "scripts/reports/visual-route-inventory.json",
    "scripts/reports/mpc01/b04_projection_example.py",
    "tests/reporting/test_visual_examples.py",
    "tests/reporting/test_visual_route_inventory.py",
    "tests/reporting/test_render_adaptive_ode_example.py",
    "tests/reporting/test_fuel_reachability_layers.py",
    "tests/reporting/test_viz10_plot_companions.py",
    "tests/reporting/test_landing.py",
}
PAGES_PUBLICATION_FILES = {
    "docs/catalogue/learning-book-v1.json",
    "docs/examples/learning/chapters/native-substitution-matrix.html",
    "scripts/reports/learning_book.py",
    "scripts/reports/learning_model_tracks.py",
    "scripts/reports/render_full_profile_campaign.py",
    "scripts/reports/augment_pages_bundle.py",
    "scripts/reports/audit_published_route_preservation.py",
    "scripts/reports/preserve_published_routes.py",
    "scripts/reports/pages_route_retirement.py",
    "scripts/reports/audit_visual_routes.py",
    "tests/reporting/test_published_route_audit_policy.py",
    "tests/reporting/test_preserve_published_routes.py",
    "tests/reporting/test_pages_route_retirement.py",
    "tests/reporting/test_pages_augmentation_aggregation.py",
}
PYTHON_QUALITY_FILES = {".github/workflows/python-quality.yml", "pyproject.toml"}
SAVED_EPISODE_PUBLICATION_FILES = {
    "scripts/reports/history_warm_gap_report.py",
    "scripts/reports/stage_history_functional.py",
    "scripts/reports/package_history_functional.py",
    "scripts/reports/render_history_functional.py",
    "scripts/reports/recorded_closed_loop_figures.py",
    "scripts/reports/native_parallelotope_functional.py",
    "tests/reporting/test_history_functional_bundle.py",
    "tests/reporting/test_history_warm_gap_publication.py",
    "tests/reporting/test_recorded_closed_loop_figures.py",
    "tests/reporting/test_native_parallelotope_functional.py",
}
SAVED_PUBLICATION_ROOTS = (
    "reports/published-route-preservation/",
    "reports/closed-loop-history-functional/",
)
SAVED_REPORTS = "reports/algorithm-results/"
EXECUTABLE_REPORT_TOOLS = SAVED_REPORTS + "tooling/"
SCOPED_VALIDATION_WORKFLOWS = (
    "python-quality.yml",
    "research-sdk.yml",
    "cpp-core-quality.yml",
)
ROUTING_FILES = {
    ".github/workflows/validation-routing.yml",
    "scripts/ci/route_changes.py",
    "tests/ci/test_route_changes.py",
}


def classify(paths):
    """Unknown paths require both gates; an empty diff proves no exemption."""
    native = not paths
    reports = not paths
    for path in paths:
        if path.startswith("docs/examples/closed-loop/campaign-2026-11-18/"):
            reports = True
        elif path in (
            PRESENTATION_FILES
            | PAGES_PUBLICATION_FILES
            | PYTHON_QUALITY_FILES
            | SAVED_EPISODE_PUBLICATION_FILES
        ):
            reports = True
        elif path.startswith(SAVED_PUBLICATION_ROOTS):
            reports = True
        elif path.startswith(SAVED_REPORTS) and not path.startswith(EXECUTABLE_REPORT_TOOLS):
            reports = True
        elif path.endswith(".md"):
            continue
        else:
            native = reports = True
    return native, reports


def workflow_path_patterns(workflow_name):
    """Use the main-branch push filter as the canonical path scope."""
    text = (ROOT / ".github/workflows" / workflow_name).read_text(encoding="utf-8")
    event_match = re.search(
        r"(?ms)^  push:\n(?P<section>.*?)(?=^  [A-Za-z_][^:\n]*:|\Z)", text
    )
    if not event_match:
        raise ValueError(f"{workflow_name} has no push filter")
    paths_match = re.search(
        r"(?ms)^    paths:\n(?P<paths>.*?)(?=^    [A-Za-z_][^:\n]*:|\Z)",
        event_match.group("section"),
    )
    if not paths_match:
        raise ValueError(f"{workflow_name} has no push.paths filter")
    patterns = [
        quoted or plain
        for quoted, plain in re.findall(
            r"^      - (?:['\"]([^'\"]+)['\"]|([^#\s]+))$",
            paths_match.group("paths"),
            re.MULTILINE,
        )
    ]
    if not patterns:
        raise ValueError(f"{workflow_name} has an empty push path filter")
    if any(pattern.startswith("!") for pattern in patterns):
        raise ValueError(f"{workflow_name} uses unsupported negated path filters")
    return patterns


def workflow_scope_matches(paths, workflow_name):
    """Conservatively match GitHub path filters against the full changed-path list."""
    if not paths:
        return True
    workflow_path = f".github/workflows/{workflow_name}"
    if workflow_path in paths or ROUTING_FILES.intersection(paths):
        return True
    patterns = workflow_path_patterns(workflow_name)
    return any(fnmatchcase(path, pattern) for path in paths for pattern in patterns)


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
        scoped = {
            workflow_name: workflow_scope_matches(paths, workflow_name)
            for workflow_name in SCOPED_VALIDATION_WORKFLOWS
        }
        reason = f"classified {len(paths)} changed paths from the complete Git diff"
    except (KeyError, OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        native = reports = True
        scoped = {workflow_name: True for workflow_name in SCOPED_VALIDATION_WORKFLOWS}
        reason = f"conservative fallback ({type(error).__name__})"
    scoped_outputs = "".join(
        f"{workflow_name.removesuffix('.yml').replace('-', '_')}={str(required).lower()}\n"
        for workflow_name, required in scoped.items()
    )
    output = (
        f"native={str(native).lower()}\nreports={str(reports).lower()}\n" + scoped_outputs
    )
    print(output + reason)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(output)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(
                f"Native matrix: **{native}**; reporting: **{reports}**; "
                + "; ".join(
                    f"{name}: **{required}**" for name, required in scoped.items()
                )
                + f". {reason}.\n"
            )


if __name__ == "__main__":
    main()
