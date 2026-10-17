"""Read-only local archive identity gate for the A33 active source closure."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from port import SOURCE_SHA256

CONSTRAINED_HELPER = Path("Публикации/Минимакс/Constrained/Modified_SM.m")
CONSTRAINED_HELPER_BYTES = 1168


def verify(register_path: Path, archive_override: Path | None = None) -> list[dict]:
    register = json.loads(register_path.read_text(encoding="utf-8"))
    root = archive_override if archive_override is not None else Path(register["archive_root"])
    selected = {item["id"]: item for item in register["selected_sources"]}
    entries = [(key, Path(selected[key]["path"]), selected[key]["bytes"])
               for key in ("A33", "A16")]
    entries.append(("constrained_Modified_SM", CONSTRAINED_HELPER,
                    CONSTRAINED_HELPER_BYTES))
    result = []
    for identity, relative, expected_bytes in entries:
        source = root / relative
        data = source.read_bytes()
        actual_digest = hashlib.sha256(data).hexdigest()
        expected_digest = SOURCE_SHA256[identity]
        if len(data) != expected_bytes or actual_digest != expected_digest:
            raise ValueError(f"{identity}: archive bytes or SHA-256 mismatch at {source}")
        if identity in selected and selected[identity]["sha256"] != expected_digest:
            raise ValueError(f"{identity}: source register digest mismatch")
        result.append({"source": identity, "relative_path": relative.as_posix(),
                       "bytes": len(data), "sha256": actual_digest})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify A33 source identities without copying originals")
    parser.add_argument("--register", type=Path,
                        default=Path(__file__).resolve().parents[3] / "docs/research/archive-selected-sources.json")
    parser.add_argument("--archive-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.register, args.archive_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
