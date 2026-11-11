"""Restore reviewed MPC11 source-version routes from their pinned Git inputs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/research/evidence/pages-mpc11-source-variants.json"
ROUTE_SET = {
    "mpc11-controller-comparison-5d94c9106e1cf07e4a2e",
    "mpc11-mesh-timing-dcb9e6e302ed2fabeb71",
    "mpc11-controller-comparison-967db980c95590a5150b",
    "mpc11-mesh-timing-e1d5ebe497051adfdfad",
}
SOURCE_RUNS = {
    "ed2dda1ef049ac4fbe259a800d3314e446ceee28": 42902971467,
    "73463ec9bc1c2b82e654e61afed1aa07b56f0e53": 43001924975,
}
ARTIFACT_RUNS = {
    "ed2dda1ef049ac4fbe259a800d3314e446ceee28": 42909649474,
    "73463ec9bc1c2b82e654e61afed1aa07b56f0e53": 43007286598,
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _policy() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("schema") != "csl.pages-mpc11-source-variants/1":
        raise ValueError("unsupported MPC11 route variant policy")
    variants = policy.get("variants")
    if not isinstance(variants, list) or {item.get("route") for item in variants} != ROUTE_SET:
        raise ValueError("MPC11 route policy does not enumerate the four reviewed variants")
    source_runs = policy.get("source_report_runs", {})
    artifact_runs = policy.get("complete_pages_artifact_runs", {})
    if source_runs != SOURCE_RUNS or artifact_runs != ARTIFACT_RUNS:
        raise ValueError("MPC11 route policy provenance differs from the reviewed publication runs")
    for variant in variants:
        commit = variant.get("source_commit")
        if variant.get("source_report_run_id") != source_runs.get(commit):
            raise ValueError("MPC11 route policy has inconsistent source-run provenance")
    return policy


def _regular_source(checkout: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("unsafe historical source path: " + relative)
    path = checkout.joinpath(*parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(checkout.resolve()):
        raise ValueError("historical source is not a regular checkout file: " + relative)
    return path


def _verify_source_checkout(checkout: Path, commit: str, variants: list[dict]) -> None:
    actual = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual != commit:
        raise ValueError("historical MPC11 worktree resolved to an unexpected commit")
    for variant in variants:
        for name, expected in variant["current_sources"].items():
            if digest(_regular_source(checkout, name).read_bytes()) != expected:
                raise ValueError("historical MPC11 source differs from reviewed route identity: " + name)
        if digest(_regular_source(checkout, variant["stager_path"]).read_bytes()) != variant["stager_sha256"]:
            raise ValueError("historical MPC11 publisher differs from reviewed route identity")


def _verify_staged_route(site: Path, variant: dict) -> None:
    route = variant["route"]
    report = site / route
    archive = site / (route + ".zip")
    manifest_path = report / "publication-manifest.json"
    if not report.is_dir() or report.is_symlink() or not archive.is_file() or archive.is_symlink():
        raise ValueError("historical MPC11 replay did not create its report and ZIP: " + route)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("historical MPC11 publication manifest is not a regular file: " + route)
    manifest_bytes = manifest_path.read_bytes()
    if digest(manifest_bytes) != variant["publication_manifest_sha256"]:
        raise ValueError("historical MPC11 replay changed the recorded publication manifest: " + route)
    manifest = json.loads(manifest_bytes)
    identity = manifest.get("identity", {})
    if identity.get("current_sources") != variant["current_sources"]:
        raise ValueError("historical MPC11 replay identity differs from its reviewed source map: " + route)
    if manifest.get("schema") != variant["publication_schema"]:
        raise ValueError("historical MPC11 replay has an unexpected publication schema: " + route)
    publisher_hash = (identity.get("stager_sha256") if variant["publication_schema"] == "csl.mpc11.publication/1"
                     else identity.get("current_sources", {}).get(variant["stager_path"]))
    if publisher_hash != variant["stager_sha256"]:
        raise ValueError("historical MPC11 replay publisher identity differs: " + route)
    if digest(archive.read_bytes()) != variant["zip_sha256"]:
        raise ValueError("historical MPC11 replay ZIP differs from the reviewed publication: " + route)
    published = manifest.get("published_files")
    if not isinstance(published, dict):
        raise ValueError("historical MPC11 publication has no file hash inventory: " + route)
    for name, expected in published.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("unsafe path in historical MPC11 publication: " + name)
        path = report.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError("historical MPC11 report file differs from its published hash: " + name)
    checksummed_files = dict(published)
    checksummed_files["publication-manifest.json"] = digest(manifest_bytes)
    expected_sums = "".join(f"{checksummed_files[name]}  {name}\n" for name in sorted(checksummed_files)).encode()
    sums_path = report / "SHA256SUMS"
    if sums_path.is_symlink() or not sums_path.is_file() or sums_path.read_bytes() != expected_sums:
        raise ValueError("historical MPC11 report checksum list differs: " + route)
    paths = list(report.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("historical MPC11 report contains an unreviewed symlink: " + route)
    actual_files = {path.relative_to(report).as_posix() for path in paths if path.is_file()}
    if actual_files != set(checksummed_files) | {"SHA256SUMS"}:
        raise ValueError("historical MPC11 report has missing or unreviewed files: " + route)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None:
            raise ValueError("historical MPC11 ZIP fails its CRC check: " + route)


def _stage_in_isolated_site(checkout: Path, variant: dict, parent: Path) -> Path:
    site = parent / (variant["route"] + "-site")
    cache_root = parent / (variant["route"] + "-process-cache")
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    temporary_root = cache_root / "tmp"
    for path in (matplotlib_cache, xdg_cache, temporary_root):
        path.mkdir(parents=True)
    (site / "examples").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    (site / "examples/index.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
    command = [sys.executable, "-B", variant["stager_path"], "--site", str(site)]
    environment = os.environ.copy()
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLCONFIGDIR": str(matplotlib_cache),
        "XDG_CACHE_HOME": str(xdg_cache),
        "TMPDIR": str(temporary_root),
        "TMP": str(temporary_root),
        "TEMP": str(temporary_root),
    })
    process = subprocess.run(command, cwd=checkout, env=environment, capture_output=True, text=True)
    if process.returncode:
        detail = (process.stderr + "\n" + process.stdout)[-5000:]
        raise RuntimeError("historical MPC11 publisher failed for " + variant["route"] + ":\n" + detail)
    if variant["route"] not in process.stdout.splitlines():
        raise RuntimeError("historical MPC11 publisher returned an unexpected route: " + variant["route"])
    _verify_staged_route(site, variant)
    return site


def _install_variant(site: Path, staged: Path, variant: dict) -> None:
    route = variant["route"]
    source_report = staged / route
    source_zip = staged / (route + ".zip")
    target_report = site / route
    target_zip = site / (route + ".zip")
    if target_report.is_symlink() or target_zip.is_symlink():
        raise ValueError("MPC11 retained variant destination must not be a symlink: " + route)
    if target_report.exists() or target_zip.exists():
        if not target_report.is_dir() or not target_zip.is_file():
            raise ValueError("partial existing MPC11 retained variant refuses replacement: " + route)
        _verify_staged_route(site, variant)
        return
    shutil.copytree(source_report, target_report)
    shutil.copyfile(source_zip, target_zip)
    _verify_staged_route(site, variant)


def _remove_clean_worktree(worktree: Path) -> None:
    if not worktree.exists():
        return
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all", "--ignored=matching"],
        capture_output=True, text=True,
    )
    if status.returncode:
        raise RuntimeError("cannot inspect historical checkout; preserved at " + str(worktree))
    if status.stdout.strip():
        raise RuntimeError("historical checkout has unaccounted files; preserved at " + str(worktree)
                           + "\n" + status.stdout.strip())
    removed = subprocess.run(
        ["git", "-C", str(ROOT), "worktree", "remove", str(worktree)],
        capture_output=True, text=True,
    )
    if removed.returncode:
        detail = (removed.stderr + "\n" + removed.stdout).strip()
        raise RuntimeError("clean historical checkout could not be removed; preserved at "
                           + str(worktree) + "\n" + detail)


def preserve(site: Path) -> dict[str, str]:
    """Ensure all four reviewed publication identities exist byte-for-byte."""
    site = Path(site)
    if site.is_symlink() or not site.is_dir():
        raise ValueError("composed Pages site must be a regular directory")
    policy = _policy()
    variants = policy["variants"]
    groups: dict[str, list[dict]] = {}
    for variant in variants:
        groups.setdefault(variant["source_commit"], []).append(variant)

    pending: dict[str, list[dict]] = {}
    for commit, records in groups.items():
        for variant in records:
            report = site / variant["route"]
            archive = site / (variant["route"] + ".zip")
            if report.exists() or archive.exists():
                _verify_staged_route(site, variant)
            else:
                pending.setdefault(commit, []).append(variant)

    if pending:
        scratch_root = Path(tempfile.mkdtemp(prefix="pages-mpc11-history-"))
        worktrees: list[Path] = []
        failure: BaseException | None = None
        try:
            for commit, records in pending.items():
                checkout = scratch_root / ("source-" + commit[:12])
                worktrees.append(checkout)
                subprocess.run(
                    ["git", "-C", str(ROOT), "worktree", "add", "--detach", str(checkout), commit],
                    check=True, capture_output=True, text=True,
                )
                _verify_source_checkout(checkout, commit, records)
                for variant in records:
                    staged = _stage_in_isolated_site(checkout, variant, scratch_root)
                    _install_variant(site, staged, variant)
        except BaseException as error:
            failure = error

        cleanup_errors = []
        for worktree in worktrees:
            try:
                _remove_clean_worktree(worktree)
            except Exception as error:
                cleanup_errors.append(str(error))
        remaining = [str(path) for path in worktrees if path.exists()]
        if not remaining and not cleanup_errors:
            shutil.rmtree(scratch_root)
        if cleanup_errors:
            detail = "\n".join(cleanup_errors)
            raise RuntimeError("historical replay cleanup refused; scratch preserved at "
                               + str(scratch_root) + "\n" + detail) from failure
        if failure is not None:
            raise failure
    return {variant["route"]: variant["zip_sha256"] for variant in variants}
