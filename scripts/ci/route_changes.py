"""Route complete Git diffs through conservative native/report validation gates."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


# Ownership map: educational output only; neither file is a named CTest input
# or imported by a native smoke checker/collector. Add files only after reviewing
# their consumers; the stylesheet is copied into the educational site.
PRESENTATION_FILES = {
    "scripts/reports/visual_examples.py",
    "scripts/reports/visual_examples.css",
    "tests/reporting/test_visual_examples.py",
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
    if any(len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha)
           or sha == "0" * 40 for sha in (base, head)):
        raise ValueError("event has no usable source object IDs")
    result = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames",
                             comparison, "--"], check=True, capture_output=True)
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
