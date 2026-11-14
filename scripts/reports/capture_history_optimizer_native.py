"""Capture one successful native 2D whole-history run with exact provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import stage_history_optimizer_native as report


_LOCAL_PATH = re.compile(r"(?<!:)(?<!/)/(?:[^/\s;<>\"']+/)*[^/\s;<>\"']+")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _public_text(data: bytes) -> bytes:
    text = data.decode("utf-8", errors="replace")
    urls = []

    def preserve_url(match: re.Match[str]) -> str:
        urls.append(match.group(0))
        return f"\x00URL{len(urls) - 1}\x00"

    text = re.sub(r"https?://[^\s<>\"']+", preserve_url, text)
    text = _LOCAL_PATH.sub("<local-path>", text)
    for index, url in enumerate(urls):
        text = text.replace(f"\x00URL{index}\x00", url)
    return text.encode("utf-8")


def _run(binary: Path, output: Path) -> tuple[bytes, bytes]:
    with tempfile.TemporaryDirectory(prefix="csl-history-optimizer-run-") as temporary:
        result_dir = Path(temporary) / "native-result"
        completed = subprocess.run(
            [str(binary.resolve()), str(result_dir)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "native example exited with "
                + str(completed.returncode)
                + ": "
                + completed.stderr.decode("utf-8", errors="replace")
            )
        output.mkdir(parents=True, exist_ok=True)
        for name in ("history.csv", "history.svg", "index.html"):
            source = result_dir / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("native example did not write " + name)
            target = (
                output / "records/native-output.html" if name == "index.html" else output / name
            )
            shutil.copyfile(source, target)
        return completed.stdout, completed.stderr


def capture(source_root: Path, build_root: Path, output_root: Path, build_log: Path) -> dict:
    source_root = source_root.resolve(strict=True)
    build_root = build_root.resolve(strict=True)
    binary = build_root / "history_optimizer_2d_example"
    cache = build_root / "CMakeCache.txt"
    for path in (binary, cache, build_log):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("missing or symlinked native provenance input: " + str(path))
    output_root = Path(output_root).resolve()
    try:
        output_relative = output_root.relative_to(source_root).as_posix()
    except ValueError as error:
        raise RuntimeError("native capture output must stay inside the source checkout") from error
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    unexpected = [
        line
        for line in status.splitlines()
        if not (
            line.startswith("?? ")
            and (line[3:] == output_relative or line[3:].startswith(output_relative + "/"))
        )
    ]
    if unexpected:
        raise RuntimeError("native capture requires a committed and clean source tree")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", source) is None:
        raise RuntimeError("git did not return a pinned source commit")
    source_files = {}
    for relative in report.SOURCE_PATHS:
        committed = subprocess.run(
            ["git", "show", f"{source}:{relative}"],
            cwd=source_root,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        working = (source_root / relative).read_bytes()
        if committed != working:
            raise RuntimeError("working source differs from committed Git bytes: " + relative)
        source_files[relative] = _sha256(committed)
    records = output_root / "records"
    if output_root.exists() and any(output_root.iterdir()):
        raise RuntimeError("refusing to overwrite existing native history evidence")
    records.mkdir(parents=True, exist_ok=True)
    stdout, stderr = _run(binary, output_root)
    stdout_path = records / "stdout.txt"
    stdout_path.write_bytes(stdout)
    if stderr:
        (records / "stderr.txt").write_bytes(stderr)
        raise RuntimeError("native example wrote stderr; inspect preserved capture")
    (records / "build.log").write_bytes(_public_text(build_log.read_bytes()))
    (records / "CMakeCache.txt").write_bytes(_public_text(cache.read_bytes()))
    line = stdout.decode("utf-8").strip()
    match = re.search(
        r"provider=([^;]+); source J=([^;]+); u0=([^;]+); u1=([^;]+); "
        r"max H violation=([^;]+); start=cold; start policy=([^;]+); "
        r"readback unavailable=([^;]+); (.+)$",
        line,
    )
    if match is None or match.group(1) != "csl.conic.superscs.history-cost@1":
        raise RuntimeError(
            "native example stdout does not match the expected provider/result contract"
        )
    source_j, u0, u1, violation = map(float, match.group(2, 3, 4, 5))
    if (
        abs(source_j - 1.0) > 1e-6
        or abs(u0 - 1.0) > 1e-5
        or abs(u1 - 1.0) > 1e-5
        or violation > 1e-7
    ):
        raise RuntimeError("native example did not meet its analytic 2D answer and full-H check")
    receipt = {
        "schema": report.SCHEMA,
        "source_commit": source,
        "source_tree": "controlled-systems-lab",
        "source_files": source_files,
        "binary_sha256": _sha256(binary.read_bytes()),
        "provider": match.group(1),
        "source_objective": "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "initialization": {
            "start_mode": "cold_start",
            "backend_identity": match.group(1),
            "start_policy": match.group(6),
            "readback_unavailable_reason": match.group(7),
        },
        "result": {
            "source_J": source_j,
            "u0": u0,
            "u1": u1,
            "maximum_history_violation": violation,
            "diagnostics": match.group(8),
        },
        "reproduction_command": "\n".join(
            (
                "cmake -S . -B build/history-optimizer-native-2d -DCSL_ENABLE_CASADI=ON -DCMAKE_BUILD_TYPE=Release",
                "cmake --build build/history-optimizer-native-2d --target history_optimizer_2d_example -j1",
                "build/history-optimizer-native-2d/history_optimizer_2d_example build/history-optimizer-native-2d/output",
            )
        ),
        "artifacts": {
            "csv_sha256": _sha256((output_root / "history.csv").read_bytes()),
            "figure_sha256": _sha256((output_root / "history.svg").read_bytes()),
            "native_html_sha256": _sha256((output_root / "native-output.html").read_bytes()),
            "stdout_sha256": _sha256(stdout),
            "stderr_sha256": _sha256(stderr),
            "build_log_sha256": _sha256((records / "build.log").read_bytes()),
            "cmake_cache_sha256": _sha256((records / "CMakeCache.txt").read_bytes()),
        },
    }
    (records / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report.finalize_capture(output_root)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--build-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture(args.source, args.build, args.output, args.build_log)


if __name__ == "__main__":
    main()
