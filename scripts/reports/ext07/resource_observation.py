"""Package and verify saved, process-scoped EXT-07 resource observations."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import statistics
import subprocess
import zipfile


PREFIX = "ext07-resource-observation-"
CAPTURE_FILES = (
    "CMakeCXXCompiler.raw.cmake", "host.json", "measure.resource.jsonl",
    "postrun.json", "prebuild.json", "resource-observation.json", "smoke.jsonl",
)
PROFILE_LAYOUT = {
    "one-step-r4": {
        "key": "one_step", "driver": "benchmarks/reporting/ext07/driver.cpp",
        "executable": "build/csl_ext07_hybrid_report", "horizon": 1,
        "modes": 2, "edges": 1, "paths": 1, "free_controls": 1,
        "joint_variables": 4, "relation_rows": 7,
        "relation_matrix_elements": 28,
        "verifier": "csl.hybrid.one-step-scalar-interval",
    },
    "two-param-r1": {
        "key": "two_parameter", "driver": "benchmarks/reporting/ext07/two_parameter_driver.cpp",
        "executable": "build/csl_ext07_two_parameter_report", "horizon": 2,
        "modes": 3, "edges": 3, "paths": 2, "free_controls": 2,
        "joint_variables": 7, "relation_rows": 20,
        "relation_matrix_elements": 140,
        "verifier": "csl.hybrid.exact-linear-h",
    },
}


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def resource_limits_match(resource: dict) -> bool:
    requested = resource.get("requested_limits", {})
    enforced = resource.get("enforced_limits", {})
    return (requested.get("runtime_max_seconds") == 300 and
            requested.get("memory_max_bytes") == 1_610_612_736 and
            requested.get("memory_swap_max_bytes") == 0 and
            requested.get("cpu_quota_percent") == 100 and
            enforced.get("runtime_max_usec") == 300_000_000 and
            enforced.get("memory_max_bytes") == 1_610_612_736 and
            enforced.get("memory_swap_max_bytes") == 0 and
            enforced.get("cpu_quota_per_second_usec") == 1_000_000)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "Expected JSON object: " + str(path))
    return value


def jsonl(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    require(all(isinstance(row, dict) for row in rows), "Invalid JSONL: " + str(path))
    return rows


def collect_profile(capture: Path, source: Path, layout: dict) -> dict:
    capture = capture.resolve(strict=True)
    source = source.resolve(strict=True)
    pre = read_json(capture / "prebuild.json")
    post = read_json(capture / "postrun.json")
    host = read_json(capture / "host.json")
    resource = read_json(capture / "resource-observation.json")
    commit = pre.get("commit")
    tree = pre.get("tree")
    require(pre.get("phase") == "prebuild" and post.get("phase") == "postrun" and
            pre.get("status") == post.get("status") == [] and
            post.get("commit") == commit == host.get("source_commit") ==
            resource.get("source_commit") and
            post.get("tree") == tree == host.get("source_tree") == resource.get("source_tree"),
            "Source receipts disagree")
    require(host.get("configuration") == "Release" and host.get("cxx_standard") == 20 and
            host.get("native_threads_requested") == 1 and
            host.get("outer_workers_requested") == 1 and
            host.get("absolute_tolerance") == host.get("relative_tolerance") == 1e-8,
            "Compiler, worker, or numerical profile differs")
    cache = (capture / "CMakeCache.raw.txt").read_bytes()
    cache_values = {}
    for line in cache.decode("utf-8", errors="replace").splitlines():
        if ":" in line and "=" in line and not line.startswith("//") and not line.startswith("#"):
            name, value = line.split("=", 1)
            key = name.split(":", 1)[0]
            if key in {"CMAKE_BUILD_TYPE", "CMAKE_GENERATOR", "BUILD_TESTING",
                       "CSL_ENABLE_HIGHS", "CSL_ENABLE_QHULL", "CSL_BUILD_EXT07_REPORT"}:
                cache_values[key] = value
    require(b"CMAKE_BUILD_TYPE:STRING=Release" in cache and
            b"CSL_ENABLE_HIGHS:BOOL=ON" in cache and
            b"CSL_BUILD_EXT07_REPORT:BOOL=ON" in cache and
            b"CSL_ENABLE_QHULL:BOOL=OFF" in cache,
            "CMake configuration differs")
    measured = capture / "measure.resource.jsonl"
    smoke = jsonl(capture / "smoke.jsonl")
    rows = jsonl(measured)
    require(len(smoke) == 1 and len(rows) == 8 and
            rows[0].get("phase") == "warmup" and rows[0].get("calls") == 10 and
            rows[0].get("failures") == 0 and rows[0].get("status") == "passed",
            "Smoke or warmup record differs")
    trials = rows[1:]
    for repetition, row in enumerate(trials):
        require(row.get("phase") == "trial" and row.get("repetition") == repetition and
                row.get("calls") == 20 and row.get("failures") == 0 and
                row.get("status") == "passed" and row.get("paths", row.get("path_count")) == layout["paths"] and
                row.get("relation_rows") == layout["relation_rows"] and
                row.get("relation_matrix_elements") == layout["relation_matrix_elements"] and
                row.get("verifier") == layout["verifier"] and
                row.get("feasibility") == row.get("optimality") == row.get("coverage") == "established",
                "Measured algorithm outcome differs")
        fields = (("setup_total_ns", "assembly_total_ns", "solve_total_ns",
                   "verify_total_ns", "end_to_end_total_ns")
                  if layout["key"] == "one_step" else ("end_to_end_total_ns",))
        for field in fields:
            require(isinstance(row.get(field), int) and row[field] > 0,
                    "Missing measured phase: " + field)
        if layout["key"] == "two_parameter":
            durations = row.get("call_durations_ns")
            require(isinstance(durations, list) and len(durations) == row["calls"] and
                    all(isinstance(value, int) and value > 0 for value in durations) and
                    sum(durations) == row["end_to_end_total_ns"],
                    "Two-parameter call durations differ from batch total")
    executable = capture / layout["executable"]
    executable_hash = sha(executable.read_bytes())
    require(executable_hash == post.get("executable_sha256") ==
            resource.get("executable_sha256"), "Executable hash receipt differs")
    require(sha(measured.read_bytes()) == resource.get("output_sha256"),
            "Resource receipt is not bound to the saved measurement output")
    enforced = resource.get("enforced_limits", {})
    observed = resource.get("observed", {})
    require(resource.get("phase") == "measure" and resource.get("scope") and
            resource_limits_match(resource) and
            enforced.get("result") == "success" and enforced.get("exit_status") == 0 and
            observed.get("memory_peak_bytes", -1) >= 0 and
            observed.get("swap_peak_bytes", -1) == 0 and
            observed.get("cpu_time_ns", -1) >= 0,
            "Enforced or observed process limits differ")
    driver = subprocess.check_output(
        ["git", "show", commit + ":" + layout["driver"]], cwd=source)
    require(sha(driver) == post.get("driver_sha256", sha(driver)),
            "Measured driver source receipt differs")
    build_configuration = {
        "schema": "csl.ext07-build-configuration/1",
        "generator": cache_values.get("CMAKE_GENERATOR"),
        "build_type": cache_values.get("CMAKE_BUILD_TYPE"),
        "build_testing": cache_values.get("BUILD_TESTING"),
        "highs_enabled": cache_values.get("CSL_ENABLE_HIGHS"),
        "qhull_enabled": cache_values.get("CSL_ENABLE_QHULL"),
        "report_enabled": cache_values.get("CSL_BUILD_EXT07_REPORT"),
        "compiler_id": host.get("compiler_id"),
        "compiler_version": host.get("compiler_version"),
        "cxx_standard": host.get("cxx_standard"),
        "cmake_version": host.get("cmake"),
        "raw_cache_sha256": sha(cache),
        "configure_log_sha256": host.get("raw_configure_log_sha256"),
        "build_log_sha256": host.get("raw_build_log_sha256"),
    }
    return {
        "profile": layout["key"], "source_commit": commit, "source_tree": tree,
        "driver_path": layout["driver"], "driver_sha256": sha(driver),
        "host": host, "build_configuration": build_configuration,
        "resource_observation": resource,
        "smoke": smoke[0], "warmup": rows[0], "trials": trials,
        "provider": rows[1].get("provider"),
        "scenario_counts": {key: layout[key] for key in
                             ("horizon", "modes", "edges", "paths", "free_controls",
                              "joint_variables", "relation_rows", "relation_matrix_elements")},
        "median_batch_end_to_end_ns": int(statistics.median(
            row["end_to_end_total_ns"] for row in trials)),
        "min_batch_end_to_end_ns": min(row["end_to_end_total_ns"] for row in trials),
        "max_batch_end_to_end_ns": max(row["end_to_end_total_ns"] for row in trials),
        "measured_calls": sum(row["calls"] for row in trials),
        "failures": sum(row["failures"] for row in trials),
        "files": {name: sha((capture / name).read_bytes()) for name in CAPTURE_FILES},
        "executable_sha256": executable_hash,
        "captured_source": driver,
    }


def svg(record: dict) -> bytes:
    items = [record["profiles"][key] for key in ("one_step", "two_parameter")]
    rows = []
    for pos, item in enumerate(items):
        peak = item["resource_observation"]["observed"]["memory_peak_bytes"]
        cap = item["resource_observation"]["enforced_limits"]["memory_max_bytes"]
        y = 105 + pos * 100
        width = max(1, int(500 * peak / cap))
        rows.append(f'<text x="35" y="{y}">{html.escape(item["profile"].replace("_", " "))}</text>'
                    f'<rect x="150" y="{y-24}" width="500" height="25" fill="#393552"/>'
                    f'<rect x="150" y="{y-24}" width="{width}" height="25" fill="#9ccfd8"/>'
                    f'<text x="155" y="{y-6}">{peak:,} B observed / {cap:,} B cap</text>')
    return ('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 310" role="img" aria-labelledby="t d">
<title id="t">Whole-process peak memory and enforced cap</title>
<desc id="d">The bars compare each whole-process-tree memory peak against the same 1.5 GiB enforced cap. They are not per-transition measurements.</desc>
<rect width="720" height="310" fill="#16161e"/><g fill="#e0def4" font-family="system-ui,sans-serif" font-size="14">''' +
        "".join(rows) + '''<text x="35" y="280">Scope: one measurement invocation including wrapper and counter-read tail</text>
</g></svg>\n''').encode()


def page(record: dict) -> bytes:
    profiles = [record["profiles"][key] for key in ("one_step", "two_parameter")]
    rows = []
    for item in profiles:
        resource = item["resource_observation"]
        observed = resource["observed"]
        limits = resource["enforced_limits"]
        timing = (f"{item['median_batch_end_to_end_ns']:,} ns "
                  f"({item['min_batch_end_to_end_ns']:,}–{item['max_batch_end_to_end_ns']:,})")
        counts = item["scenario_counts"]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
            item["profile"], counts["horizon"], counts["modes"], counts["edges"],
            counts["paths"], counts["free_controls"], counts["joint_variables"],
            item["measured_calls"], timing, f"{observed['memory_peak_bytes']:,} B",
            f"{observed['cpu_time_ns']:,} ns", "0 B", f"{limits['memory_max_bytes']:,} B",
            f"{limits['runtime_max_usec'] // 1_000_000} s",
            f"{limits['cpu_quota_per_second_usec'] / 10_000:.0f}%")) + "</tr>")
    build_hosts = sorted({item["build_configuration"]["compiler_id"] + " " +
                          item["build_configuration"]["compiler_version"] + " / " +
                          item["build_configuration"]["generator"] + " / " +
                          item["host"]["os"] for item in profiles})
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>EXT-07 resource observations</title>
<style>body{background:#16161e;color:#e0def4;font:16px/1.55 system-ui,sans-serif;margin:0}main,header,footer{max-width:1100px;margin:auto;padding:1.2rem}a{color:#9ccfd8}section{background:#23212c;border:1px solid #524f67;border-radius:12px;padding:1rem;margin:1rem 0}table{border-collapse:collapse;display:block;overflow-x:auto}td,th{border:1px solid #524f67;padding:.45rem;text-align:left;white-space:nowrap}img{width:100%;height:auto}code{overflow-wrap:anywhere}</style></head><body>
<header><p>Controlled Systems Lab · EXT-07</p><h1>Hybrid profile resource observations</h1>
<p>Two bounded Release captures of the public one-step and two-parameter hybrid verification routes. This report adds whole-invocation resource observations to their existing analytic and complete-family evidence.</p></header><main>
<section><h2>Capability and observed resources</h2><p>Both invocations requested and enforced a 300-second watchdog, 1.5 GiB memory cap, zero swap, and one CPU quota. Resource counters cover the executable process tree, including a shell wrapper and a short idle tail for reading live cgroup counters; they do not attribute cost to individual transitions. Build, smoke, and rendering are excluded.</p>
<img src="resource-scope.svg" alt="Whole-process peak memory compared with the enforced memory cap"><table><thead><tr><th>Profile</th><th>Horizon</th><th>Modes</th><th>Edges</th><th>Paths</th><th>Free controls</th><th>Joint variables</th><th>Measured calls</th><th>Batch time median (range)</th><th>Peak memory</th><th>CPU cgroup time</th><th>Swap peak</th><th>Memory cap</th><th>Wall cap</th><th>CPU quota</th></tr></thead><tbody>''' +
        "".join(rows) + '''</tbody></table><p>The end-to-end rows are descriptive single-fixture timings, not cross-profile comparisons or evidence of a solver ranking. The two profiles differ in horizon, path count and relation size.</p></section>
<section><h2>Numerical evidence</h2><p>All seven measured batches per profile completed with zero failures (140 calls each). Both used <code>''' + html.escape(profiles[0]["provider"]) + '''</code>. The one-step verifier established feasibility, optimality and complete scalar-family coverage. The two-parameter capture used the exact-linear-H verifier and established those properties on both tied edge paths. These are numerical binary64 checks, not validated arithmetic.</p>
<p>The companion result reports are <code>ext07-hybrid-51d9ee2e89d240eb</code> (one-step) and <code>ext07-hybrid-two-parameter-8ad871b5ea29fc7b</code> (two-parameter); this record focuses on their separate Linux resource captures.</p></section>
<section><h2>Reproducibility and limits</h2><p>The measured build used ''' + "; ".join(
        html.escape(host) for host in build_hosts) + '''. Each source commit, source tree, measured driver, compiler receipt, redacted build configuration, saved smoke and resource-limited measurement rows, systemd limits, and cgroup observations are included. The build-configuration file records the SHA-256 of the original cache, while local paths from that cache and the build logs are omitted. Exact source commits are <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/''' + html.escape(profiles[0]["source_commit"]) + '''">one-step</a> and <a href="https://github.com/butahlecoq/controlled-systems-lab/commit/''' + html.escape(profiles[1]["source_commit"]) + '''">two-parameter</a>. The captures make no general scalability, performance comparison or per-transition resource claim.</p>
<ul><li><a href="records.json">Combined resource and capability records</a></li><li><a href="manifest.json">File hash manifest</a></li><li><a href="resource-observations.zip">Offline bundle</a></li></ul></section></main>
<footer>EXT-07 resource profile · ''' + html.escape(record["report_id"]) + "</footer></body></html>\n").encode()


def zip_bytes(files: dict[str, bytes]) -> bytes:
    from io import BytesIO
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, content)
    return output.getvalue()


def collect(capture_root: Path, source: Path, output_root: Path) -> Path:
    profiles = {}
    captures = {"one_step": "one-step-r4", "two_parameter": "two-param-r1"}
    for key, directory in captures.items():
        profile = collect_profile(capture_root / directory, source, PROFILE_LAYOUT[directory])
        for name in CAPTURE_FILES:
            profile[name] = (capture_root / directory / name).read_bytes()
        profiles[key] = profile
    unsigned = {"schema": "csl.ext07-resource-observation/1",
                "profiles": {key: {name: value for name, value in item.items()
                                   if not isinstance(value, bytes)}
                             for key, item in profiles.items()},
                "evidence_limits": [
                    "Whole-process-tree counters include a shell wrapper and idle counter-read tail.",
                    "CPU and memory are not attributed to individual hybrid transitions.",
                    "The profiles differ in horizon, path count, and relation size; no scaling comparison is claimed.",
                    "Numerical assurance is binary64 and fixture-specific."]}
    report_id = PREFIX + sha(encoded(unsigned))[:16]
    record = {**unsigned, "report_id": report_id}
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    bundle = output_root / report_id
    require(not bundle.exists(), "Resource report bundle already exists")
    bundle.mkdir()
    for key, item in profiles.items():
        folder = bundle / key
        folder.mkdir()
        for name in CAPTURE_FILES:
            (folder / name).write_bytes(item[name])
        (folder / "build-configuration.json").write_bytes(
            encoded(item["build_configuration"]))
        (folder / "measured-driver.cpp").write_bytes(item["captured_source"])
    (bundle / "records.json").write_bytes(encoded(record))
    render(bundle)
    return bundle


def render(bundle: Path, check: bool = False) -> dict:
    bundle = bundle.resolve(strict=True)
    record = read_json(bundle / "records.json")
    unsigned = {key: value for key, value in record.items() if key != "report_id"}
    require(record.get("schema") == "csl.ext07-resource-observation/1" and
            bundle.name == PREFIX + sha(encoded(unsigned))[:16], "Resource report identity differs")
    require(set(record.get("profiles", {})) == {"one_step", "two_parameter"},
            "Resource report profile inventory differs")
    files = {"records.json": (bundle / "records.json").read_bytes(),
             "index.html": page(record), "resource-scope.svg": svg(record)}
    for key, item in record["profiles"].items():
        folder = bundle / key
        require(item.get("profile") == key and item.get("failures") == 0 and
                item.get("measured_calls") == 140 and
                item.get("source_commit") == item["resource_observation"].get("source_commit") and
                item.get("source_tree") == item["resource_observation"].get("source_tree") and
                item["host"].get("source_commit") == item["source_commit"] and
                item["host"].get("source_tree") == item["source_tree"],
                "Resource report source or attempt totals differ: " + key)
        pre = read_json(folder / "prebuild.json")
        post = read_json(folder / "postrun.json")
        host = read_json(folder / "host.json")
        receipt = read_json(folder / "resource-observation.json")
        trials_file = folder / "measure.resource.jsonl"
        trials = jsonl(trials_file)
        smoke = jsonl(folder / "smoke.jsonl")
        require(len(smoke) == 1 and len(trials) == 8 and
                pre["commit"] == post["commit"] == item["source_commit"] and
                pre["tree"] == post["tree"] == item["source_tree"] and
                pre["status"] == post["status"] == [] and host == item["host"] and
                receipt == item["resource_observation"] and resource_limits_match(receipt) and
                smoke == [item["smoke"]] and trials[0] == item["warmup"] and
                trials[1:] == item["trials"] and
                sha(trials_file.read_bytes()) == receipt["output_sha256"] and
                sha((folder / "build-configuration.json").read_bytes()) ==
                sha(encoded(item["build_configuration"])),
                "Saved resource report no longer matches its raw capture: " + key)
        require(item.get("executable_sha256") == post.get("executable_sha256") ==
                receipt.get("executable_sha256") and
                item["median_batch_end_to_end_ns"] == int(statistics.median(
                    row["end_to_end_total_ns"] for row in trials[1:])) and
                item["min_batch_end_to_end_ns"] == min(
                    row["end_to_end_total_ns"] for row in trials[1:]) and
                item["max_batch_end_to_end_ns"] == max(
                    row["end_to_end_total_ns"] for row in trials[1:]) and
                item["measured_calls"] == sum(row["calls"] for row in trials[1:]) and
                item["failures"] == sum(row["failures"] for row in trials[1:]),
                "Resource or timing summaries do not derive from the retained attempts: " + key)
        layout = next(value for value in PROFILE_LAYOUT.values() if value["key"] == key)
        counts = {name: layout[name] for name in
                  ("horizon", "modes", "edges", "paths", "free_controls",
                   "joint_variables", "relation_rows", "relation_matrix_elements")}
        require(item.get("scenario_counts") == counts, "Capability counts differ: " + key)
        for repetition, row in enumerate(trials[1:]):
            require(row.get("phase") == "trial" and row.get("repetition") == repetition and
                    row.get("calls") == 20 and row.get("failures") == 0 and
                    row.get("status") == "passed" and
                    row.get("verifier") == layout["verifier"] and
                    row.get("provider") == item.get("provider") and
                    row.get("relation_rows") == layout["relation_rows"] and
                    row.get("relation_matrix_elements") == layout["relation_matrix_elements"] and
                    row.get("feasibility") == row.get("optimality") ==
                    row.get("coverage") == "established",
                    "A saved algorithm attempt is incomplete: " + key)
        for name, digest in item["files"].items():
            path = folder / name
            require(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == digest,
                    "Capture file hash differs: " + key + "/" + name)
            files[key + "/" + name] = path.read_bytes()
        driver = folder / "measured-driver.cpp"
        require(driver.is_file() and sha(driver.read_bytes()) == item["driver_sha256"],
                "Measured driver hash differs: " + key)
        files[key + "/measured-driver.cpp"] = driver.read_bytes()
        build_config = folder / "build-configuration.json"
        require(build_config.is_file() and
                build_config.read_bytes() == encoded(item["build_configuration"]),
                "Redacted build configuration differs: " + key)
        files[key + "/build-configuration.json"] = build_config.read_bytes()
    manifest = {"schema": "csl.ext07-resource-observation-manifest/1",
                "report_id": bundle.name,
                "files": {name: sha(content) for name, content in
                          sorted({**files, "resource-scope.svg": files["resource-scope.svg"],
                                  "index.html": files["index.html"]}.items())}}
    files["manifest.json"] = encoded(manifest)
    files["resource-observations.zip"] = zip_bytes(files)
    expected_paths = set(files)
    actual_paths = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*")
                    if path.is_file() and not path.is_symlink()}
    require((actual_paths == expected_paths) if check else actual_paths <= expected_paths,
            "Resource report inventory differs")
    for name, content in files.items():
        path = bundle / name
        if "/" in name:
            continue
        if check:
            require(path.is_file() and path.read_bytes() == content,
                    "Rendered resource report differs: " + name)
        else:
            path.write_bytes(content)
    return {"report_id": bundle.name, "source_commits":
            [item["source_commit"] for item in record["profiles"].values()],
            "manifest_sha256": sha(files["manifest.json"]),
            "zip_sha256": sha(files["resource-observations.zip"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.bundle is not None and args.check and args.capture_root is None:
        print(json.dumps(render(args.bundle, check=True), sort_keys=True, indent=2))
    elif args.capture_root is not None and args.source is not None and args.out is not None and args.bundle is None:
        print(collect(args.capture_root, args.source, args.out))
    else:
        parser.error("Use --bundle BUNDLE --check, or --capture-root ROOT --source REPO --out DIR")
