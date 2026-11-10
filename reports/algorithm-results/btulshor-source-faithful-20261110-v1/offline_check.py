#!/usr/bin/env python3
"""Verify an extracted BTULSHOR bundle using only Python's standard library."""
import hashlib, json, re, sys, zipfile
from pathlib import Path, PurePosixPath

REPORT_ID = "btulshor-source-faithful-20261110-v1"
ROOT = Path(__file__).resolve().parent
def fail(message): raise SystemExit("BTULSHOR bundle check failed: " + message)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
try:
    manifest_path, sums_path = ROOT / "manifest.json", ROOT / "SHA256SUMS"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "csl.btulshor-source-faithful-bundle/1": fail("unknown manifest schema")
    if manifest.get("source_sha256") != "06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442": fail("source hash differs")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("capture_source_commit", "")): fail("invalid source commit")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files: fail("empty file inventory")
    sums = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match.group(2) in sums: fail("malformed checksums")
        sums[match.group(2)] = match.group(1)
    expected = set(files) | {"manifest.json"}
    if set(sums) != expected: fail("checksum inventory differs")
    for name, value in files.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts: fail("unsafe manifest path")
        candidate = ROOT.joinpath(*path.parts)
        if candidate.is_symlink() or not candidate.is_file() or digest(candidate) != value or sums[name] != value:
            fail("hash mismatch: " + name)
    if digest(manifest_path) != sums["manifest.json"]: fail("manifest hash mismatch")
    allowed = expected | {"SHA256SUMS", REPORT_ID + ".zip", "report-envelope.json", "publication-manifest.json"}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in ROOT.rglob("*")) or actual - allowed: fail("unlisted or unsafe bundle files")
    for required in ("index.html", "point-projections.svg", "offline_check.py", "raw/summary.json"):
        if required not in files: fail("missing required file: " + required)
    summary = json.loads((ROOT / "raw/summary.json").read_text(encoding="utf-8"))
    if summary.get("schema") != "csl.btulshor-summary/1": fail("unknown summary schema")
    for name in files:
        if name == "raw/oracle-differential.json":
            receipt = json.loads((ROOT / name).read_text(encoding="utf-8"))
            if receipt.get("source_sha256") != manifest.get("source_sha256") or receipt.get("driver_sha256") != summary.get("driver_sha256"):
                fail("oracle receipt source or driver identity differs")
            continue
        if not name.startswith("raw/") or not name.endswith(".json") or name == "raw/summary.json": continue
        document = json.loads((ROOT / name).read_text(encoding="utf-8"))
        if document.get("schema") != "csl.btulshor-comparison/1": fail("unknown raw comparison schema")
        for provider in document.get("providers", []):
            if not isinstance(provider.get("status"), str): fail("provider status missing")
            check = provider.get("exact_check")
            if check is not None and check.get("status") not in {"verified", "rejected", "inconclusive", "not_applicable"}:
                fail("unknown exact-check status")
    archive = ROOT / (REPORT_ID + ".zip")
    if archive.exists():
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if len(names) != len(set(names)): fail("duplicate archive entries")
            for name in names:
                if not name.startswith(REPORT_ID + "/"): fail("archive path outside report prefix")
                rel = name[len(REPORT_ID) + 1:]
                if rel not in expected | {"SHA256SUMS"}: fail("unexpected archive entry")
                if zf.read(name) != (ROOT / rel).read_bytes(): fail("archive bytes differ: " + rel)
except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
    fail(str(exc))
print("verified")
