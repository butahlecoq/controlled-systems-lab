"""Read-only local archive identity gate for the active A29/A30 closure."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from port import SOURCE_SHA256

EXPECTED = {
    "A29": ("Scientific Research/QLPHULL.m", 1619, SOURCE_SHA256["A29"]),
    "A30": ("Scientific Research/Modified_SM.m", 1150, SOURCE_SHA256["A30"]),
}


def verify(register_path: Path, archive_override: Path | None = None) -> list[dict]:
    register = json.loads(register_path.read_text(encoding="utf-8"))
    root = archive_override if archive_override is not None else Path(register["archive_root"])
    selected = {item["id"]: item for item in register["selected_sources"]}
    result = []
    for identity, (relative, expected_bytes, expected_digest) in EXPECTED.items():
        entry = selected[identity]
        if (entry["path"] != relative or entry["bytes"] != expected_bytes
                or entry["sha256"] != expected_digest):
            raise ValueError(f"{identity}: selected-source register differs from port pin")
        data = (root / relative).read_bytes()
        actual_digest = hashlib.sha256(data).hexdigest()
        if len(data) != expected_bytes or actual_digest != expected_digest:
            raise ValueError(f"{identity}: archive bytes or SHA-256 mismatch")
        result.append({"source": identity, "relative_path": relative,
                       "bytes": len(data), "sha256": actual_digest})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify A29/A30 originals without copying them")
    parser.add_argument("--register", type=Path,
                        default=Path(__file__).resolve().parents[3] / "docs/research/archive-selected-sources.json")
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.register, args.archive_root), indent=2))


if __name__ == "__main__":
    main()