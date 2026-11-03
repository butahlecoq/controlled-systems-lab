"""Wait for the three Pages augmentations belonging to one report run."""
from __future__ import annotations

import argparse
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import tarfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import zipfile

WORKFLOWS = (
    "mpc01-per-attempt-pages-augmentation.yml",
    "b04-c-pages-augmentation.yml",
    "mpc06-tube-objective-pages-augmentation.yml",
)
REPORTS_WORKFLOW = "algorithm-reports.yml"
SOURCE_MARKER = "pages-augmentation-source.json"
MARKER_SCHEMA = "csl.pages-augmentation-source/1"
MAX_MARKER_BYTES = 4096


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_json(api_url: str, repository: str, token: str, path: str) -> dict:
    request = Request(f"{api_url}/repos/{repository}/{path}", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Cache-Control": "no-cache",
    })
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"GitHub API request failed ({error.code}): {path}") from error


def get_artifact_zip(api_url: str, repository: str, token: str, artifact_id: int) -> bytes:
    url = f"{api_url}/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Cache-Control": "no-cache",
    })

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, new_url):
            return None

    try:
        with build_opener(NoRedirect).open(request, timeout=30) as response:
            return response.read()
    except HTTPError as error:
        if error.code not in {301, 302, 303, 307, 308}:
            raise RuntimeError(f"GitHub artifact download failed ({error.code})") from error
        location = error.headers.get("Location")
        if not location:
            raise RuntimeError("GitHub artifact download redirect has no location") from error
        with urlopen(Request(location), timeout=60) as response:
            return response.read()


def source_marker(artifact_zip: bytes) -> dict | None:
    """Read only the small source marker from the Pages tar inside its zip."""
    try:
        with zipfile.ZipFile(BytesIO(artifact_zip)) as zipped:
            if zipped.namelist() != ["artifact.tar"]:
                raise ValueError("Pages artifact zip must contain exactly artifact.tar")
            tar_bytes = zipped.read("artifact.tar")
        with tarfile.open(fileobj=BytesIO(tar_bytes), mode="r:") as archive:
            members = [member for member in archive.getmembers()
                       if PurePosixPath(member.name).parts == (".", SOURCE_MARKER)
                       or PurePosixPath(member.name).parts == (SOURCE_MARKER,)]
            if not members:
                return None
            if len(members) != 1 or not members[0].isfile() or members[0].size > MAX_MARKER_BYTES:
                raise ValueError("Pages source marker must be one small regular file")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ValueError("Pages source marker cannot be read")
            marker = json.loads(stream.read(MAX_MARKER_BYTES + 1))
    except (tarfile.TarError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("Pages artifact does not contain a valid safe archive") from error
    if (not isinstance(marker, dict)
            or marker.get("schema") != MARKER_SCHEMA
            or not isinstance(marker.get("report_run_id"), int)
            or marker["report_run_id"] <= 0
            or not isinstance(marker.get("head_sha"), str)
            or len(marker["head_sha"]) != 40
            or any(char not in "0123456789abcdef" for char in marker["head_sha"])):
        raise ValueError("Pages source marker identity is invalid")
    return marker


def pages_artifact(api_url: str, repository: str, token: str, run_id: int) -> dict | None:
    artifacts = get_json(api_url, repository, token,
                         f"actions/runs/{run_id}/artifacts?per_page=100").get("artifacts", [])
    matches = [artifact for artifact in artifacts
               if artifact.get("name") == "github-pages" and not artifact.get("expired", True)]
    if len(matches) > 1:
        raise RuntimeError(f"run {run_id} has multiple unexpired github-pages artifacts")
    return matches[0] if matches else None


def run_marker(api_url: str, repository: str, token: str, run_id: int) -> dict | None:
    artifact = pages_artifact(api_url, repository, token, run_id)
    if artifact is None:
        return None
    marker = source_marker(get_artifact_zip(api_url, repository, token, int(artifact["id"])))
    if marker is None:
        raise RuntimeError(f"Pages artifact for run {run_id} has no report-source marker")
    return marker


def workflow_runs(api_url: str, repository: str, token: str, workflow: str,
                  head_sha: str) -> list[dict]:
    query = urlencode({"head_sha": head_sha, "branch": "main", "per_page": 100})
    payload = get_json(api_url, repository, token,
                       f"actions/workflows/{workflow}/runs?{query}")
    return payload.get("workflow_runs", [])


def latest_report_run(runs: list[dict], *, head_sha: str) -> dict | None:
    matches = [run for run in runs
               if run.get("head_sha") == head_sha
               and run.get("head_branch") == "main"
               and run.get("event") in {"push", "workflow_dispatch"}
               and run.get("status") == "completed"
               and run.get("conclusion") == "success"]
    return max(matches, key=lambda run: timestamp(run["updated_at"])) if matches else None


def matching_augmentation(api_url: str, repository: str, token: str, workflow: str,
                          parent: dict, timeout_seconds: int, poll_seconds: int) -> dict | None:
    head_sha, parent_id = parent["head_sha"], int(parent["id"])
    deadline = time.monotonic() + timeout_seconds
    observed: dict[int, tuple[int, dict | None]] = {}
    while time.monotonic() < deadline:
        runs = workflow_runs(api_url, repository, token, workflow, head_sha)
        candidates = [run for run in runs
                      if run.get("head_sha") == head_sha
                      and run.get("head_branch") == "main"
                      and run.get("event") == "workflow_run"
                      and timestamp(run["created_at"]) >= timestamp(parent["created_at"])]
        candidates.sort(key=lambda run: timestamp(run["created_at"]), reverse=True)
        for run in candidates:
            if run.get("status") not in {"completed", "in_progress"}:
                continue
            artifact = pages_artifact(api_url, repository, token, int(run["id"]))
            if artifact is None:
                continue
            artifact_id = int(artifact["id"])
            cached = observed.get(int(run["id"]))
            if cached is not None and cached[0] == artifact_id:
                marker = cached[1]
            else:
                marker = source_marker(get_artifact_zip(api_url, repository, token, artifact_id))
                observed[int(run["id"])] = (artifact_id, marker)
            if marker is None:
                raise RuntimeError(f"Pages artifact for run {run['id']} has no report-source marker")
            if marker["head_sha"] != head_sha or marker["report_run_id"] != parent_id:
                continue
            if run.get("status") == "completed":
                if run.get("conclusion") != "success":
                    raise RuntimeError(f"{workflow} run {run['id']} failed after publishing its artifact")
                return run
        time.sleep(poll_seconds)
    raise TimeoutError(f"no successful {workflow} augmentation matched report run {parent_id}")


def await_augmentations(api_url: str, repository: str, token: str, child_run_id: int,
                        timeout_seconds: int, poll_seconds: int) -> int | None:
    child = get_json(api_url, repository, token, f"actions/runs/{child_run_id}")
    if (child.get("head_branch") != "main" or child.get("event") != "workflow_run"
            or child.get("conclusion") != "success"):
        raise RuntimeError("Pages aggregation must be triggered by a successful main workflow_run")
    marker = run_marker(api_url, repository, token, child_run_id)
    if marker is None:
        print("The triggering workflow has no Pages artifact; cumulative deployment is skipped.")
        return None
    head_sha = child["head_sha"]
    if marker["head_sha"] != head_sha:
        raise RuntimeError("triggering Pages artifact source marker disagrees with its run SHA")

    parent = get_json(api_url, repository, token, f"actions/runs/{marker['report_run_id']}")
    if (parent.get("head_sha") != head_sha
            or parent.get("head_branch") != "main"
            or parent.get("name") != "Algorithm report records and site"
            or parent.get("event") not in {"push", "workflow_dispatch"}
            or parent.get("status") != "completed"
            or parent.get("conclusion") != "success"):
        raise RuntimeError("Pages source marker does not identify a successful main report run")

    reports = workflow_runs(api_url, repository, token, REPORTS_WORKFLOW, head_sha)
    latest = latest_report_run(reports, head_sha=head_sha)
    if latest is None or int(latest["id"]) != int(parent["id"]):
        print("A newer successful report run supersedes this Pages source; deployment is skipped.")
        return None

    deadline = time.monotonic() + timeout_seconds
    for workflow in WORKFLOWS:
        if workflow == "mpc06-tube-objective-pages-augmentation.yml":
            if child.get("conclusion") != "success":
                raise RuntimeError("triggering MPC-06 augmentation did not succeed")
            continue
        remaining = max(1, int(deadline - time.monotonic()))
        matching_augmentation(api_url, repository, token, workflow, parent,
                              remaining, poll_seconds)
    return int(parent["id"])


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
        if upstream_id is not None:
            output.write(f"upstream_run_id={upstream_id}\n")
    if upstream_id is not None:
        print(f"All Pages augmentations succeeded for report run {upstream_id}; its base artifact is ready.")


if __name__ == "__main__":
    main()
