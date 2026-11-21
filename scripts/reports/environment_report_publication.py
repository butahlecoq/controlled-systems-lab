"""Preserve byte-bound archive identities for saved environment reports."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import NamedTuple


class _ArchivedReport(NamedTuple):
    source_checksums: str
    stager_sha256: str
    zip_sha256: str


# These receipts were verified against the preserved Pages artifact.
_ARCHIVED_REPORTS = {
    "env717-dubins-car-pilot-v1": _ArchivedReport(
        "5975d77fb4615fb905500bea3c70de33c4df08b8bc784ecf04a5b2a17bff0a75",
        "b41b7a37d4b6d6e5564b7994f54456d8dbbcd245567a0d04a203e16976e0dc83",
        "d5a809ed13623630749c26ce357161d9c5449572e254c58592dfd6341fde6914",
    ),
    "env717-earth-orbit-pilot-v1": _ArchivedReport(
        "56483e79a760d67fc2115d3f4d6a18e2cb2315e4d0eadb00dd5508c6c88ab2fb",
        "d233ec942bda7ab7ef4f55d7dd968de20bc179b81ddbf1922f44799c25ff6c81",
        "54222e7c40271d5e32c2531bc0113ee086db4124d4c95592420c312127a1336c",
    ),
    "env717-pendulum-terminal-pilot-v1": _ArchivedReport(
        "b2ce22d853a7d076d7011cf7375b8e935033967646b5abb190e5319a0e05817a",
        "eef6a623eb4d9f963d0432f0c88b09daabb2f8a202dfa881b178c67e62ab718c",
        "618b8e349ce96988e101d64428a20ad5326a07778297b14c7556de120d56d92d",
    ),
    "env717-vanderpol-pilot-v1": _ArchivedReport(
        "e2e6077f11e5028aa57a5dfbe9d527472ef73e94a47c5ca02374c3a735ff4a81",
        "a35ac20618ba2b983eda9ec4526f1e37d1199df7c75688176d0f45f13b0205b9",
        "6c0841f15482a4a93c557553558bc25657866617bf5713ffcf73e4336657bda3",
    ),
}


def archive_identity(
    source_name: str, verified_checksums: bytes, stager: Path
) -> tuple[dict[str, str], str | None]:
    """Bind the publisher source and, for an exact archived input, require its ZIP hash."""
    archived = _ARCHIVED_REPORTS.get(source_name)
    if (
        archived is not None
        and hashlib.sha256(verified_checksums).hexdigest() == archived.source_checksums
    ):
        return {"stager_sha256": archived.stager_sha256}, archived.zip_sha256
    return {
        "stager_sha256": hashlib.sha256(stager.read_bytes()).hexdigest(),
        "publication_helper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, None


def offline_zip(
    report_id: str, landing: bytes, files: dict[str, bytes], *, expected_sha256: str | None
) -> bytes:
    """Build the offline archive and verify its historical hash before staging."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        entries = [("index.html", landing)] + [
            (f"{report_id}/{name}", content) for name, content in sorted(files.items())
        ]
        for name, content in entries:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    output = buffer.getvalue()
    if expected_sha256 is not None and hashlib.sha256(output).hexdigest() != expected_sha256:
        raise ValueError(f"historical environment report archive hash differs: {report_id}")
    return output
