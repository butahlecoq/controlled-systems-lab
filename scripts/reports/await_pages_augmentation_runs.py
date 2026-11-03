"""Wait for every single-route Pages deployment for one main source revision."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

WORKFLOWS = (
    "mpc01-per-attempt-pages-augmentation.yml",
    "b04-c-pages-augmentation.yml",
    "mpc06-tube-objective-pages-augmentation.yml",
)
REPORTS_WORKFLOW = "algorithm-reports.yml"


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_after_parent(runs: list[dict], *, head_sha: str, parent_created_at: str,
                     branch: str = "main") -> dict | None:
    parent_time = timestamp(parent_created_at)
    matches = [run for run in runs
               if run.get("head_sha") == head_sha
               and run.get("head_branch") == branch
               and run.get("event") == "workflow_run"
               and timestamp(run["created_at"]) > parent_time]
    return max(matches, key=lambda run: timestamp(run["created_at"])) if matches else None


def select_parent_run(runs: list[dict], *, head_sha: str, child_created_at: str,
                      branch: str = "main") -> dict | None:
    child_time = timestamp(child_created_at)
    matches = [run for run in runs
               if run.get("head_sha") == head_sha
               and run.get("head_branch") == branch
               and run.get("event") in {"push", "workflow_dispatch"}
               and run.get("status") == "completed"
               and run.get("conclusion") == "success"
               and timestamp(run["created_at"]) < child_time]
    return max(matches, key=lambda run: timestamp(run["created_at"])) if matches else None


def get_json(api_url: str, repository: str, token: str, path: str) -> dict:
    request = Request(f"{api_url}/repos/{repository}/{path}", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API request failed ({error.code}): {path}") from error


def workflow_runs(api_url: str, repository: str, token: str, workflow: str,
                  head_sha: str) -> list[dict]:
    payload = get_json(api_url, repository, token,
                       f"actions/workflows/{workflow}/runs?head_sha={head_sha}&per_page=100")
    return payload.get("workflow_runs", [])


def await_augmentations(api_url: str, repository: str, token: str, child_run_id: int,
                        timeout_seconds: int, poll_seconds: int) -> int:
    child = get_json(api_url, repository, token, f"actions/runs/{child_run_id}")
    if child.get("head_branch") != "main" or child.get("event") != "workflow_run":
        raise RuntimeError("Pages aggregation must be triggered by a main workflow_run")
    head_sha, child_created_at = child["head_sha"], child["created_at"]
    deadline = time.monotonic() + timeout_seconds
    outcomes: dict[str, dict | None] = {}

    while time.monotonic() < deadline:
        parent = select_parent_run(
            workflow_runs(api_url, repository, token, REPORTS_WORKFLOW, head_sha),
            head_sha=head_sha, child_created_at=child_created_at)
        if parent is None:
            time.sleep(poll_seconds)
            continue

        outcomes: dict[str, dict | None] = {}
        waiting = False
        for workflow in WORKFLOWS:
            run = run_after_parent(
                workflow_runs(api_url, repository, token, workflow, head_sha),
                head_sha=head_sha, parent_created_at=parent["created_at"])
            outcomes[workflow] = run
            if run is None or run.get("status") != "completed":
                waiting = True
            elif run.get("conclusion") != "success":
                raise RuntimeError(f"{workflow} did not complete successfully: {run.get('conclusion')}")

        if not waiting:
            artifacts = get_json(api_url, repository, token,
                                 f"actions/runs/{parent['id']}/artifacts?per_page=100").get("artifacts", [])
            pages = [artifact for artifact in artifacts
                     if artifact.get("name") == "github-pages" and not artifact.get("expired", True)]
            if len(pages) != 1:
                raise RuntimeError("successful report run must have one unexpired github-pages artifact")
            return int(parent["id"])

        time.sleep(poll_seconds)

    states = {name: (run or {}).get("status", "not-created") for name, run in outcomes.items()}
    raise TimeoutError(f"Pages augmentations did not all finish before timeout: {states}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path(os.environ["GITHUB_OUTPUT"]))
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        parser.error("timeout and poll intervals must be positive")
    token = os.environ["GH_TOKEN"]
    api_url = os.environ.get("API_URL", "https://api.github.com").rstrip("/")
    repository = os.environ["REPOSITORY"]
    child_run_id = int(os.environ["CHILD_RUN_ID"])
    upstream_id = await_augmentations(api_url, repository, token, child_run_id,
                                      args.timeout_seconds, args.poll_seconds)
    with args.output.open("a", encoding="utf-8") as output:
        output.write(f"upstream_run_id={upstream_id}\n")
    print(f"All Pages augmentations succeeded for the main source revision; base run {upstream_id} is ready.")


if __name__ == "__main__":
    main()
