"""Exercise the Pages waiter's artifact and CLI boundaries."""

import json
import sys
import tarfile
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from scripts.reports import await_pages_augmentation_runs as waiter


class PagesAugmentationWaiterTests(unittest.TestCase):
    def test_boolean_report_run_id_is_rejected(self) -> None:
        marker = json.dumps(
            {"schema": waiter.MARKER_SCHEMA, "report_run_id": True, "head_sha": "a" * 40}
        ).encode()
        tar = BytesIO()
        with tarfile.open(fileobj=tar, mode="w:") as archive:
            entry = tarfile.TarInfo(waiter.SOURCE_MARKER)
            entry.size = len(marker)
            archive.addfile(entry, BytesIO(marker))

        zipped = BytesIO()
        with zipfile.ZipFile(zipped, mode="w") as archive:
            archive.writestr("artifact.tar", tar.getvalue())

        with self.assertRaisesRegex(ValueError, "Pages source marker identity is invalid"):
            waiter.source_marker(zipped.getvalue())

    def test_output_can_be_explicit_or_provided_by_actions(self) -> None:
        for explicit in (True, False):
            with self.subTest(explicit=explicit), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                args = ["await_pages_augmentation_runs.py"]
                environment = {
                    "GH_TOKEN": "test-token",
                    "REPOSITORY": "owner/project",
                    "CHILD_RUN_ID": "8",
                }
                if explicit:
                    args.extend(("--output", str(output)))
                else:
                    environment["GITHUB_OUTPUT"] = str(output)
                with (
                    mock.patch.object(sys, "argv", args),
                    mock.patch.dict(waiter.os.environ, environment, clear=True),
                    mock.patch.object(waiter, "await_augmentations", return_value=(5, "b" * 40)),
                ):
                    waiter.main()
                self.assertEqual(
                    output.read_text(encoding="utf-8"),
                    "upstream_run_id=5\nupstream_sha=" + "b" * 40 + "\n",
                )
