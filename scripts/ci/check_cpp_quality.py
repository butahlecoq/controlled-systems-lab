"""Check retained native sources against real, source-owned CMake profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
LLVM = "23.1.3"
NATIVE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx", ".inl", ".ipp", ".tpp"}
TRANSLATION_UNITS = {".c", ".cc", ".cpp", ".cxx"}
PROFILE_OPTIONS = {
    "core": (False, False, False),
    "highs": (True, True, False),
    "casadi": (False, False, True),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_value(value: object, label: str) -> dict[str, object]:
    require(isinstance(value, dict), f"{label} must be an object")
    result: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        require(isinstance(key, str), f"{label} has a non-string key")
        result[cast(str, key)] = item
    return result


def string_value(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(value), f"{label} must be a nonempty string")
    return cast(str, value)


def list_value(value: object, label: str) -> list[object]:
    require(isinstance(value, list), f"{label} must be a list")
    return cast(list[object], value)


def read_object(path: Path) -> dict[str, object]:
    return object_value(json.loads(path.read_bytes()), str(path))


def run(arguments: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(arguments, cwd=cwd, text=True, capture_output=True, check=False)
    require(
        result.returncode == 0,
        f"Command failed: {shlex.join(arguments[:6])}\n{result.stdout}{result.stderr}",
    )
    return result.stdout


def versioned_tool(name: str) -> str:
    tool = shutil.which(name)
    require(tool is not None, f"Install requirements-cpp-quality.txt: missing {name}")
    executable = cast(str, tool)
    require(
        re.search(r"(?<![0-9.])" + re.escape(LLVM) + r"(?![0-9.])", run([executable, "--version"]))
        is not None,
        f"{name} must be LLVM {LLVM}; install requirements-cpp-quality.txt",
    )
    return executable


@dataclass(frozen=True)
class Corpus:
    root: Path
    hashes: dict[str, str]
    failures: frozenset[str]
    frozen: frozenset[str]
    roots: tuple[str, ...]

    def owns(self, path: str) -> bool:
        return any(path == root or path.startswith(root + "/") for root in self.roots)

    @property
    def public_headers(self) -> set[str]:
        return {
            p
            for p in self.hashes
            if p.startswith("include/") and Path(p).suffix in {".h", ".hpp", ".hxx"}
        }

    @property
    def sources(self) -> set[str]:
        return {p for p in self.hashes if Path(p).suffix in TRANSLATION_UNITS} - self.failures

    @property
    def dependency_headers(self) -> set[str]:
        return {
            p for p in self.hashes if Path(p).suffix not in TRANSLATION_UNITS
        } - self.public_headers


def corpus(root: Path) -> Corpus:
    root = root.resolve()
    policy = read_object(root / "scripts/ci/cpp-quality-policy.json")
    require(policy.get("schema") == "csl.cpp-quality-policy/1", "Unsupported native quality policy")
    roots = [string_value(p, "scope root") for p in list_value(policy.get("roots"), "roots")]
    require(
        bool(roots) and all(not Path(p).is_absolute() and ".." not in Path(p).parts for p in roots),
        "Native source roots must be nonempty relative paths",
    )
    paths = run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *roots],
        cwd=root,
    ).split("\0")
    selected = {p for p in paths if Path(p).suffix in NATIVE_SUFFIXES}
    frozen: set[str] = set()
    for value in list_value(policy.get("frozen"), "frozen inputs"):
        entry = object_value(value, "frozen input")
        path = string_value(entry.get("path"), "frozen path")
        owner = root / string_value(entry.get("owner"), "frozen owner")
        require(digest(owner) == entry.get("owner_sha256"), f"Captured owner changed: {owner}")
        record = read_object(owner)
        require(
            record.get(string_value(entry.get("member_key"), "member key")) == entry.get("member"),
            f"Captured source member changed: {path}",
        )
        require(
            digest(root / path) == record.get(string_value(entry.get("digest_key"), "digest key")),
            f"Captured native input changed: {path}",
        )
        require(path in selected, f"Frozen native path disappeared: {path}")
        frozen.add(path)
    failures = frozenset(
        string_value(p, "compile-refusal path")
        for p in list_value(policy.get("expected_compile_failures"), "expected failures")
    )
    require(failures <= selected - frozen, "Compile-refusal source is outside the retained scope")
    hashes = {}
    for path in sorted(selected - frozen):
        require(not (root / path).is_symlink(), f"Native source must not be a symlink: {path}")
        hashes[path] = digest(root / path)
    require(bool(hashes), "No retained native sources discovered")
    return Corpus(root, hashes, failures, frozenset(frozen), tuple(roots))


def cache_values(build: Path) -> dict[str, str]:
    result = {}
    for line in (build / "CMakeCache.txt").read_text().splitlines():
        if not line.startswith(("#", "//")) and ":" in line and "=" in line:
            key, value = line.split("=", 1)
            result[key.split(":", 1)[0]] = value
    return result


def enabled(value: str) -> bool:
    require(
        value.upper() in {"ON", "OFF", "TRUE", "FALSE", "1", "0"}, f"Invalid CMake boolean: {value}"
    )
    return value.upper() in {"ON", "TRUE", "1"}


def configuration_inputs(source: Corpus) -> set[str]:
    result = set(source.hashes) | set(source.frozen)
    for directory in ("cmake", *source.roots):
        for pattern in ("*CMakeLists.txt", "*.cmake"):
            result.update(
                p.relative_to(source.root).as_posix()
                for p in (source.root / directory).rglob(pattern)
            )
    result.update(
        {
            "CMakeLists.txt",
            "CMakePresets.json",
            "requirements-cpp-quality.txt",
            "scripts/ci/check_cpp_quality.py",
            "scripts/ci/cpp-quality-policy.json",
            ".clang-format",
            ".clang-tidy",
        }
    )
    return result


def profile_manifest(build: Path, source: Corpus) -> tuple[str, dict[str, str]]:
    manifest = read_object(build / "cpp-quality-profile.json")
    require(
        manifest.get("schema") == "csl.cpp-quality-profile/1", "Unsupported native context manifest"
    )
    require(
        Path(string_value(manifest.get("source_root"), "source_root")).resolve() == source.root,
        "Native profile belongs to another source tree; configure this checkout",
    )
    require(
        Path(string_value(manifest.get("binary_root"), "binary_root")).resolve() == build,
        "Native profile belongs to another build tree",
    )
    name = string_value(manifest.get("profile"), "profile")
    require(name in PROFILE_OPTIONS, f"Unknown native profile: {name}")
    cache = cache_values(build)
    require(
        Path(string_value(cache.get("CMAKE_HOME_DIRECTORY"), "configured source owner")).resolve()
        == source.root,
        "Compilation database belongs to another source tree",
    )
    require(
        cache.get("CSL_CPP_QUALITY_PROFILE") == name and enabled(cache.get("CSL_CPP_QUALITY", "")),
        "Quality profile was not configured with its declared owner",
    )
    require(
        cache.get("CMAKE_GENERATOR") == manifest.get("generator") == "Ninja",
        "Native quality requires actual Ninja dependency records",
    )
    options = tuple(enabled(string_value(manifest.get(k), k)) for k in ("highs", "qhull", "casadi"))
    require(options == PROFILE_OPTIONS[name], f"{name} has incorrect native adapter options")
    for field, variable in [
        ("highs", "CSL_ENABLE_HIGHS"),
        ("qhull", "CSL_ENABLE_QHULL"),
        ("casadi", "CSL_ENABLE_CASADI"),
        ("testing", "BUILD_TESTING"),
    ]:
        require(
            enabled(string_value(manifest.get(field), field)) == enabled(cache.get(variable, "")),
            f"Profile/cache mismatch: {variable}",
        )
    require(
        enabled(cache.get("BUILD_TESTING", "")), "Native quality needs the actual unit-test targets"
    )
    inputs = object_value(manifest.get("inputs_sha256"), "configured source inputs")
    require(
        set(source.hashes) <= inputs.keys(),
        "New native files lack configured ownership; reconfigure the profile",
    )
    require(
        set(inputs) == configuration_inputs(source),
        "Configured native/configuration input membership changed; reconfigure",
    )
    for path, expected in inputs.items():
        require(
            digest(source.root / path) == expected,
            f"Stale native profile input {path}; reconfigure and build",
        )
    headers = {
        str(Path(p).resolve()): string_value(h, "public header")
        for p, h in object_value(
            manifest.get("public_header_contexts"), "public header contexts"
        ).items()
    }
    require(
        set(headers.values()) == source.public_headers,
        "Public standalone-header coverage differs from the retained source tree",
    )
    return name, headers


def target_sources(build: Path) -> dict[Path, set[str]]:
    reply = build / ".cmake/api/v1/reply"
    indexes = sorted(reply.glob("index-*.json"))
    require(bool(indexes), f"Missing CMake File API evidence: {build}")
    index = read_object(indexes[-1])
    models = [
        object_value(v, "File API object")
        for v in list_value(index.get("objects"), "File API objects")
    ]
    names = [v for v in models if v.get("kind") == "codemodel"]
    require(len(names) == 1, "No unique CMake codemodel")
    model = read_object(reply / string_value(names[0].get("jsonFile"), "codemodel file"))
    model_paths = object_value(model.get("paths"), "codemodel paths")
    source_root = Path(string_value(model_paths.get("source"), "codemodel source"))
    configurations = list_value(model.get("configurations"), "configurations")
    require(len(configurations) == 1, "Quality profiles must use one actual Ninja configuration")
    result: dict[Path, set[str]] = {}
    configuration = object_value(configurations[0], "configuration")
    for value in list_value(configuration.get("targets"), "targets"):
        entry = object_value(value, "target entry")
        target = read_object(reply / string_value(entry.get("jsonFile"), "target file"))
        for value in list_value(target.get("sources", []), "target sources"):
            item = object_value(value, "target source")
            if "compileGroupIndex" not in item:
                continue
            path = Path(string_value(item.get("path"), "target source path"))
            absolute = (path if path.is_absolute() else source_root / path).resolve()
            result.setdefault(absolute, set()).add(string_value(entry.get("name"), "target name"))
    return result


def ninja_dependencies(build: Path) -> dict[Path, set[Path]]:
    executable = cache_values(build).get("CMAKE_MAKE_PROGRAM", "")
    require(
        Path(executable).name in {"ninja", "ninja.exe"},
        "Expected the actual configured Ninja executable",
    )
    planned = run([executable, "-C", str(build), "-j1", "-n", "-v"])
    pending = [
        line
        for line in planned.splitlines()
        if line and not line.startswith(("ninja: Entering directory", "ninja: no work to do"))
    ]
    require(not pending, f"Native profile is not fully built: {build}\n" + "\n".join(pending[:5]))
    result: dict[Path, set[Path]] = {}
    current: set[Path] | None = None
    for line in run([executable, "-C", str(build), "-j1", "-t", "deps"]).splitlines():
        match = re.match(r"^(.*): #deps [0-9]+, deps mtime [0-9]+ \((VALID|STALE)\)$", line)
        if match:
            current = set() if match[2] == "VALID" else None
            if current is not None:
                result[(build / match[1]).resolve()] = current
        elif line.startswith("    ") and current is not None:
            path = Path(line.strip())
            current.add((path if path.is_absolute() else build / path).resolve())
    require(bool(result), f"No real compiled dependency evidence in {build}")
    return result


def object_output(command: dict[str, object]) -> Path:
    directory = Path(string_value(command.get("directory"), "command directory"))
    value = command.get("output")
    if value is None:
        arguments = command.get("arguments")
        words = (
            [string_value(v, "argument") for v in list_value(arguments, "arguments")]
            if arguments is not None
            else shlex.split(string_value(command.get("command"), "compiler command"))
        )
        require(
            "-o" in words and words.index("-o") + 1 < len(words),
            "Compiler command has no actual object output",
        )
        value = words[words.index("-o") + 1]
    path = Path(string_value(value, "object output"))
    return (path if path.is_absolute() else directory / path).resolve()


def copied_origin(path: Path, source: Corpus) -> str | None:
    named = {p: expected for p, expected in source.hashes.items() if Path(p).name == path.name}
    if not named:
        return None
    actual = digest(path)
    candidates = [p for p, expected in named.items() if expected == actual]
    require(bool(candidates), f"Installed consumer differs from current source: {path}")
    require(len(candidates) == 1, f"Ambiguous staged source identity: {path}")
    return candidates[0]


def origin(
    path: Path, source: Corpus, build: Path, copies: list[Path], prefixes: list[Path]
) -> str | None:
    if path.is_relative_to(build / "_deps"):
        return None
    if path.is_relative_to(source.root):
        relative = path.relative_to(source.root).as_posix()
        if source.owns(relative):
            require(
                relative in source.hashes or relative in source.frozen,
                f"Unregistered first-party compiler input: {relative}",
            )
        return relative if relative in source.hashes else None
    for prefix in prefixes:
        headers = prefix / "include"
        if path.is_relative_to(headers):
            relative = "include/" + path.relative_to(headers).as_posix()
            if relative in source.hashes:
                require(
                    digest(path) == source.hashes[relative],
                    f"Installed header differs from current source: {relative}",
                )
                return relative
    if any(path.is_relative_to(copy) for copy in copies):
        return copied_origin(path, source)
    require(
        not path.is_relative_to(build)
        or path.suffix not in TRANSLATION_UNITS
        or "header-checks" in path.parts
        or "cpp-quality-headers" in path.parts,
        f"Unregistered generated native source: {path}",
    )
    return None


def analyze(build: Path, source: Corpus) -> dict[str, object]:
    build = build.resolve()
    name, headers = profile_manifest(build, source)
    tool = versioned_tool("clang-tidy")
    builds = [build]
    children = [
        build / "installed-consumer/build",
        build / "installed-consumer/examples-build",
        build / "casadi-consumer/build",
    ]
    builds.extend(p for p in children if (p / "CMakeCache.txt").is_file())
    required_children = children[:2] if name in {"core", "highs"} else children[2:]
    require(
        all((p / "CMakeCache.txt").is_file() for p in required_children),
        f"Build the real {name} installed consumers before analysis",
    )
    copies = [
        build / "installed-consumer/source",
        build / "installed-consumer/examples-source",
        build / "casadi-consumer/source",
    ]
    prefixes: list[Path] = []
    for child in builds[1:]:
        expected_source = child.parent / (
            "examples-source" if child.name == "examples-build" else "source"
        )
        child_cache = cache_values(child)
        require(
            Path(child_cache.get("CMAKE_HOME_DIRECTORY", "")).resolve()
            == expected_source.resolve(),
            f"Installed profile belongs to another source tree: {child}",
        )
        for value in child_cache.get("CMAKE_PREFIX_PATH", "").split(";"):
            prefix = Path(value).resolve()
            require(
                prefix.is_relative_to(build),
                f"Installed quality prefix belongs to another build: {prefix}",
            )
            prefixes.append(prefix)
    installed_headers: set[str] = set()
    for line in (build / "install_manifest.txt").read_text().splitlines():
        path = Path(line).resolve()
        for prefix in prefixes:
            if path.is_relative_to(prefix / "include/csl"):
                installed_headers.add("include/" + path.relative_to(prefix / "include").as_posix())
    require(
        bool(installed_headers) and installed_headers <= source.public_headers,
        "Installed public-header receipt differs from the current source scope",
    )
    checked_sources: set[str] = set()
    checked_headers: set[str] = set()
    standalone: set[str] = set()
    installed_standalone: set[str] = set()
    contexts: list[dict[str, object]] = []
    for current in builds:
        current_headers = headers if current == build else {}
        if current in {children[0], children[2]}:
            current_headers = {
                str(Path(p).resolve()): string_value(h, "installed standalone header")
                for p, h in read_object(current / "cpp-quality-installed-headers.json").items()
            }
            require(
                set(current_headers.values()) == installed_headers,
                "Installed standalone-header coverage differs from the actual install manifest",
            )
        targets = target_sources(current)
        dependencies = ninja_dependencies(current)
        commands = list_value(
            json.loads((current / "compile_commands.json").read_bytes()), "compilation commands"
        )
        jobs: set[Path] = set()
        for value in commands:
            command = object_value(value, "compilation command")
            path = Path(string_value(command.get("file"), "command source"))
            directory = Path(string_value(command.get("directory"), "command directory"))
            path = (path if path.is_absolute() else directory / path).resolve()
            require(
                directory.resolve().is_relative_to(build),
                f"Compiler command belongs to another build: {directory}",
            )
            if path.is_relative_to(source.root):
                relative = path.relative_to(source.root).as_posix()
                if source.owns(relative):
                    require(
                        relative in source.hashes or relative in source.frozen,
                        f"Unknown compiled native source type: {relative}",
                    )
            selected = origin(path, source, build, copies, prefixes)
            generated = path.is_relative_to(current) and (
                "header-checks" in path.parts or str(path) in current_headers
            )
            if selected is None and not generated:
                continue
            require(path in targets, f"Source has no actual CMake target: {path}")
            output = object_output(command)
            require(output in dependencies, f"Missing built dependency evidence: {output}")
            observed: set[str] = set()
            for dependency in dependencies[output]:
                require(
                    current == build or not dependency.is_relative_to(source.root),
                    f"Installed consumer leaked a repository dependency: {dependency}",
                )
                owned = origin(dependency, source, build, copies, prefixes)
                if owned is not None and Path(owned).suffix not in TRANSLATION_UNITS:
                    observed.add(owned)
            checked_headers.update(observed)
            if str(path) in current_headers:
                require(
                    current_headers[str(path)] in observed,
                    f"Standalone context did not compile its owned header: {path}",
                )
                destination = standalone if current == build else installed_standalone
                destination.add(current_headers[str(path)])
            if selected is not None:
                require(
                    selected not in source.failures,
                    f"Expected-refusal probe unexpectedly has a normal build command: {selected}",
                )
                checked_sources.add(selected)
            else:
                require(
                    bool(observed & source.public_headers),
                    f"Generated context has no real public-header dependency: {path}",
                )
            contexts.append(
                {
                    "source": selected,
                    "actual_file": str(path),
                    "targets": sorted(targets[path]),
                    "build": str(current),
                    "object": str(output),
                    "compile_command": command,
                    "owned_headers": sorted(observed),
                }
            )
            jobs.add(path)
        header_roots = [
            *(source.root / p for p in source.roots),
            *(p / "include" for p in prefixes),
            *copies,
        ]
        expression = "^(" + "|".join(re.escape(str(p)) + "/" for p in header_roots) + ")"
        for path in sorted(jobs):
            print(f"clang-tidy {name}: {path}", flush=True)
            run(
                [
                    tool,
                    "-p=" + str(current),
                    "--config-file=" + str(source.root / ".clang-tidy"),
                    "--header-filter=" + expression,
                    "--quiet",
                    str(path),
                ]
            )
    require(bool(checked_sources), "No maintained translation units were analyzed")
    require(
        standalone == source.public_headers, "Profile is missing compiled standalone public headers"
    )
    require(
        installed_standalone == installed_headers,
        "Profile is missing compiled installed standalone public headers",
    )
    failures: set[str] = set()
    negative_receipt = build / "installed-consumer/build/cpp-quality-negative-compiles.json"
    if negative_receipt.is_file():
        for filename, value in read_object(negative_receipt).items():
            entry = object_value(value, "negative compilation")
            path = "tests/installed/" + filename
            require(
                path in source.failures
                and entry.get("refused") is True
                and entry.get("sha256") == source.hashes[path],
                f"Stale or unknown negative compilation: {path}",
            )
            failures.add(path)
    require(corpus(source.root).hashes == source.hashes, "Native source changed during analysis")
    recorded_inputs = object_value(
        read_object(build / "cpp-quality-profile.json").get("inputs_sha256"), "profile inputs"
    )
    require(
        all(digest(source.root / p) == expected for p, expected in recorded_inputs.items()),
        "Quality/configuration inputs changed during analysis",
    )
    return {
        "schema": "csl.cpp-quality-receipt/1",
        "profile": name,
        "llvm": LLVM,
        "source_hashes": source.hashes,
        "quality_inputs_sha256": read_object(build / "cpp-quality-profile.json").get(
            "inputs_sha256"
        ),
        "configuration_sha256": digest(build / "cpp-quality-profile.json"),
        "compiler": {
            k: read_object(build / "cpp-quality-profile.json").get(k)
            for k in ("compiler", "compiler_id", "compiler_version")
        },
        "checked_sources": sorted(checked_sources),
        "checked_headers": sorted(checked_headers),
        "standalone_headers": sorted(standalone),
        "installed_standalone_headers": sorted(installed_standalone),
        "expected_failures": sorted(failures),
        "contexts": contexts,
        "scope": "Retained include/src/tests/examples; broader source-owned queues remain unadopted",
        "status": "passed",
    }


def coverage(receipts: list[dict[str, object]], source: Corpus) -> dict[str, object]:
    profiles: set[str] = set()
    current_inputs = {p: digest(source.root / p) for p in configuration_inputs(source)}
    fields: dict[str, set[str]] = {
        k: set()
        for k in (
            "checked_sources",
            "checked_headers",
            "standalone_headers",
            "installed_standalone_headers",
            "expected_failures",
        )
    }
    for receipt in receipts:
        require(
            receipt.get("schema") == "csl.cpp-quality-receipt/1"
            and receipt.get("status") == "passed"
            and receipt.get("llvm") == LLVM,
            "Unqualified native profile receipt",
        )
        require(
            receipt.get("source_hashes") == source.hashes,
            "Native profile receipt belongs to stale or different source bytes",
        )
        require(
            receipt.get("quality_inputs_sha256") == current_inputs,
            "Native profile receipt has stale quality/configuration inputs",
        )
        name = string_value(receipt.get("profile"), "receipt profile")
        require(name not in profiles, f"Duplicate native profile: {name}")
        profiles.add(name)
        for field, values in fields.items():
            values.update(string_value(v, field) for v in list_value(receipt.get(field), field))
    require(
        profiles == set(PROFILE_OPTIONS),
        "Native coverage requires core, HiGHS+Qhull, and CasADi profile receipts",
    )
    for label, required, field in [
        ("translation unit", source.sources, "checked_sources"),
        ("public standalone header", source.public_headers, "standalone_headers"),
        ("installed standalone header", source.public_headers, "installed_standalone_headers"),
        ("private/test/example header", source.dependency_headers, "checked_headers"),
        ("expected compiler refusal", set(source.failures), "expected_failures"),
    ]:
        missing = required - fields[field]
        require(not missing, f"Uncovered {label}: " + ", ".join(sorted(missing)))
    return {
        "status": "passed",
        "scope": "include/src/tests/examples",
        "retained_paths": len(source.hashes),
        "frozen_inputs": sorted(source.frozen),
        "profiles": sorted(profiles),
        "public_headers": len(source.public_headers),
        "dependency_headers": len(source.dependency_headers),
        "expected_failures": len(source.failures),
        "broader_native_adoption_complete": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("format", help="check every retained native source, including future files")
    analysis = sub.add_parser(
        "analyze", help="check one actual configured/built profile and installed consumers"
    )
    analysis.add_argument("--build", required=True, type=Path)
    analysis.add_argument("--receipt", required=True, type=Path)
    union = sub.add_parser(
        "coverage", help="require the complete retained-source union of three qualified profiles"
    )
    union.add_argument("--receipt", action="append", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = corpus(ROOT)
        if args.mode == "format":
            run(
                [
                    versioned_tool("clang-format"),
                    "--style=file",
                    "--dry-run",
                    "--Werror",
                    *[str(source.root / p) for p in source.hashes],
                ]
            )
            print(
                f"Verified formatting of {len(source.hashes)} retained native paths; {len(source.frozen)} exact captured inputs preserved"
            )
        elif args.mode == "analyze":
            receipt = analyze(args.build, source)
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        else:
            print(
                json.dumps(
                    coverage([read_object(p) for p in args.receipt], source),
                    indent=2,
                    sort_keys=True,
                )
            )
        return 0
    except (OSError, ValueError) as error:
        print(f"Native quality: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
