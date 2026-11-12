#!/usr/bin/env python3
"""Check the immutable T-S03 Strategy A/B bundle and its reproducible render."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1"
GENERATED = (
    "strategy-ab-ts03-summary.html",
    "strategy-ab-ts03-summary.txt",
    "strategy-ab-ts03-control-plane.svg",
)


def validate(bundle: Path) -> None:
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("Strategy A/B bundle directory is missing or unsafe")
    bundle = bundle.resolve()
    manifest = bundle / "SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Strategy A/B checksum manifest is missing")
    names: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts or name in names:
            raise ValueError("unsafe or duplicate Strategy A/B manifest path: " + name)
        path = bundle / name
        if (path.is_symlink() or not path.is_file() or
                not path.resolve().is_relative_to(bundle) or
                hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError("Strategy A/B checksum mismatch: " + name)
        names.add(name)
    actual = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*")
              if path.is_file() and path.name != "SHA256SUMS"}
    if actual != names or any(path.is_symlink() for path in bundle.rglob("*")):
        raise ValueError("Strategy A/B bundle inventory differs from its manifest")
    if not set(GENERATED).issubset(names):
        raise ValueError("Strategy A/B bundle omits generated report artifacts")

    renderer = ROOT / "scripts/reports/mpc01/summarize_strategy_ab_ts03.py"
    with tempfile.TemporaryDirectory(prefix="mpc01-ts03-render-check-") as temporary:
        copy = Path(temporary) / "bundle"
        shutil.copytree(bundle, copy, symlinks=False)
        subprocess.run([sys.executable, str(renderer), str(copy)], cwd=ROOT, check=True)
        for name in GENERATED:
            if (bundle / name).read_bytes() != (copy / name).read_bytes():
                raise ValueError("rendered Strategy A/B artifact differs from saved bytes: " + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    args = parser.parse_args()
    validate(args.bundle)
    print("Validated immutable MPC-01 T-S03 Strategy A/B bundle and render")
