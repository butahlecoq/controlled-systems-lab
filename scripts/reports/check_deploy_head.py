"""Allow a Pages deployment only while its run still targets current main."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SHA = re.compile(r"[0-9a-f]{40}\Z")
SOURCE_MARKER = "pages-augmentation-source.json"


def source_report(payload: dict) -> tuple[int, str] | None:
    """Return the exact report run that caused a workflow_run augmentation."""
    upstream = payload.get("workflow_run")
    if not isinstance(upstream, dict):
        return None
    if (upstream.get("name") != "Algorithm report records and site"
            or upstream.get("head_branch") != "main"
            or upstream.get("status") != "completed"
            or upstream.get("conclusion") != "success"):
        raise ValueError("workflow_run event is not a successful main report run")
    run_id, source_sha = upstream.get("id"), upstream.get("head_sha")
    if not isinstance(run_id, int) or run_id <= 0 or not isinstance(source_sha, str) or not SHA.fullmatch(source_sha):
        raise ValueError("workflow_run report identity is invalid")
    return run_id, source_sha


def latest_report_run(api: str, repository: str, token: str, source_sha: str) -> int:
    owner, name = repository.split("/")
    query = urlencode({"head_sha": source_sha, "branch": "main", "per_page": 100})
    url = (f"{api}/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
           f"/actions/workflows/algorithm-reports.yml/runs?{query}")
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "Cache-Control": "no-cache",
    })
    with urlopen(request, timeout=10) as response:
        runs = json.load(response).get("workflow_runs", [])
    matches = [run for run in runs
               if run.get("head_sha") == source_sha
               and run.get("head_branch") == "main"
               and run.get("event") in {"push", "workflow_dispatch"}
               and run.get("status") == "completed"
               and run.get("conclusion") == "success"]
    if not matches:
        raise ValueError("no successful main report run exists for the Pages source")
    return max(matches, key=lambda run: run["updated_at"])["id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true",
                        help="check freshness without writing the Pages source marker")
    args = parser.parse_args()
    repository = os.environ["GITHUB_REPOSITORY"]
    expected = os.environ["GITHUB_SHA"]
    token = os.environ["GITHUB_TOKEN"]
    output = Path(os.environ["GITHUB_OUTPUT"])
    if not SHA.fullmatch(expected):
        raise ValueError("GITHUB_SHA must be a full Git commit ID")
    owner, name = repository.split("/")
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    url = f"{api}/repos/{quote(owner, safe='')}/{quote(name, safe='')}/branches/main"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=10) as response:
        current = json.load(response)["commit"]["sha"]
    if not isinstance(current, str) or not SHA.fullmatch(current):
        raise ValueError("GitHub returned an invalid main commit ID")
    explicit_source = os.environ.get("PAGES_SOURCE_RUN_ID")
    if explicit_source is not None:
        if not explicit_source.isdecimal() or int(explicit_source) <= 0:
            raise ValueError("PAGES_SOURCE_RUN_ID must be a positive integer")
        source_run, source_sha = int(explicit_source), expected
    else:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        payload = json.loads(Path(event_path).read_text(encoding="utf-8")) if event_path else {}
        source = source_report(payload)
        source_run, source_sha = source if source is not None else (None, None)

    is_current = current == expected
    if is_current and source_run is not None:
        if source_sha != expected:
            raise ValueError("source report SHA differs from the Pages artifact")
        is_current = latest_report_run(api, repository, token, expected) == source_run

    with output.open("a", encoding="utf-8") as stream:
        stream.write(f"current={'true' if is_current else 'false'}\n")
    if is_current and source_run is not None and not args.check_only:
        site = Path(os.environ.get("PAGES_SITE_DIR", "build/report-site"))
        if site.is_symlink() or not site.is_dir():
            raise ValueError("current Pages site is missing while recording its report source")
        marker_path = site / SOURCE_MARKER
        if marker_path.is_symlink() or marker_path.exists():
            raise ValueError("Pages source marker already exists or is unsafe")
        marker = {"schema": "csl.pages-augmentation-source/1",
                  "report_run_id": source_run, "head_sha": source_sha}
        marker_path.write_text(
            json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8")
        with output.open("a", encoding="utf-8") as stream:
            stream.write(f"source_run_id={source_run}\n")
    print("Deploying current main" if is_current else "Skipping stale Pages artifact")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"Cannot establish current main commit: {error}", file=sys.stderr)
        sys.exit(1)
