from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
import zipfile
from pathlib import Path

from benchmarks.reporting.mpc07 import source_inventory as inventory

ROOT = Path(__file__).resolve().parents[2]
NATIVE_REVISION = "b3978a98a8bfb30e21841466244ed7f78e987886"


def saved_capture(folder: str, prefix: str):
    archive_path = ROOT / "benchmarks/reporting/mpc07/evidence" / folder / "offline.zip"
    with zipfile.ZipFile(archive_path) as archive:
        raw_prefix = prefix + "/RAW/"
        raw = {
            name[len(raw_prefix) :]: archive.read(name)
            for name in archive.namelist()
            if name.startswith(raw_prefix)
        }
    environment = json.loads(raw["environment.json"])
    sources = {
        name.removeprefix("source/"): data
        for name, data in raw.items()
        if name.startswith("source/")
    }
    return environment, sources


class Mpc07SourceInventoryTests(unittest.TestCase):
    def test_bounded_and_joint_profiles_select_their_own_readme_and_plan(self):
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        fixed = inventory.locations_for(inventory.FIXED_SCHEMA)
        joint = inventory.locations_for(inventory.JOINT_SCHEMA)

        fixed_readme, fixed_readme_bytes = inventory.available_location(
            ROOT, revision, fixed["README.md"]
        )
        joint_readme, joint_readme_bytes = inventory.available_location(
            ROOT, revision, joint["README.md"]
        )
        fixed_plan, fixed_plan_bytes = inventory.available_location(
            ROOT, revision, fixed["PLAN.md"]
        )
        joint_plan, joint_plan_bytes = inventory.available_location(
            ROOT, revision, joint["PLAN.md"]
        )

        self.assertEqual(
            (fixed_readme.path, fixed_readme.member),
            (
                "benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip",
                "mpc07-report/RAW/source/README.md",
            ),
        )
        self.assertEqual(
            (joint_readme.path, joint_readme.member),
            (
                "benchmarks/reporting/mpc07/evidence/joint-filter-04369201/offline.zip",
                "mpc07-joint-report/RAW/source/README.md",
            ),
        )
        self.assertEqual(
            hashlib.sha256(fixed_readme_bytes).hexdigest(),
            "631c84d73f1b228bd6797a0e2ccf5e4d409fafcf6ef9a3cf820be69f89cd40cb",
        )
        self.assertEqual(fixed_readme_bytes, joint_readme_bytes)
        self.assertEqual(
            hashlib.sha256(fixed_plan_bytes).hexdigest(),
            "3791ccdfaa1b068cabaa474eef83263f2e0ec49bcb0e2a338cce5b6ac915b4f8",
        )
        self.assertEqual(
            hashlib.sha256(joint_plan_bytes).hexdigest(),
            "3791ccdfaa1b068cabaa474eef83263f2e0ec49bcb0e2a338cce5b6ac915b4f8",
        )
        self.assertNotEqual(fixed_plan, joint_plan)

    def test_new_capture_exports_are_complete_and_self_authenticating(self):
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        for schema in (inventory.FIXED_SCHEMA, inventory.JOINT_SCHEMA):
            with self.subTest(schema=schema):
                files, selected = inventory.capture_sources(schema, revision, NATIVE_REVISION, ROOT)
                hashes = {
                    name: hashlib.sha256(content).hexdigest() for name, content in files.items()
                }
                authenticated = inventory.authenticate(
                    schema,
                    hashes,
                    files,
                    revision,
                    NATIVE_REVISION,
                    ROOT,
                )
                self.assertEqual(set(files), set(inventory.locations_for(schema)))
                self.assertIn("source_inventory.py", files)
                self.assertEqual(authenticated, selected)

    def test_current_capture_cannot_omit_the_inventory_module(self):
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        files, _ = inventory.capture_sources(
            inventory.FIXED_SCHEMA, revision, NATIVE_REVISION, ROOT
        )
        files.pop("source_inventory.py")
        hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        with self.assertRaisesRegex(ValueError, "mandatory source inventory"):
            inventory.authenticate(
                inventory.FIXED_SCHEMA, hashes, files, revision, NATIVE_REVISION, ROOT
            )

    def test_current_capture_rejects_readme_from_a_fallback_path(self):
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        for schema in (inventory.FIXED_SCHEMA, inventory.JOINT_SCHEMA):
            with self.subTest(schema=schema):
                files, _ = inventory.capture_sources(schema, revision, NATIVE_REVISION, ROOT)
                primary = files["README.md"]
                alternate = None
                for location in inventory.locations_for(schema)["README.md"][1:]:
                    try:
                        candidate = inventory.read_location(ROOT, revision, location)
                    except (ValueError, subprocess.CalledProcessError, zipfile.BadZipFile):
                        continue
                    if candidate != primary:
                        alternate = candidate
                        break
                assert alternate is not None
                files["README.md"] = alternate
                hashes = {
                    name: hashlib.sha256(content).hexdigest() for name, content in files.items()
                }
                with self.assertRaisesRegex(
                    ValueError, "recorded Git commit or archive: README.md"
                ):
                    inventory.authenticate(schema, hashes, files, revision, NATIVE_REVISION, ROOT)

    def test_saved_capture_sources_match_their_recorded_commits_and_allowlists(self):
        for folder, prefix in (
            ("bounded-policy-0e821c2a", "mpc07-report"),
            ("joint-filter-04369201", "mpc07-joint-report"),
        ):
            with self.subTest(folder=folder):
                environment, sources = saved_capture(folder, prefix)
                selected = inventory.authenticate(
                    environment["schema"],
                    environment["source_sha256"],
                    sources,
                    environment["source_commit"],
                    environment["native_source_commit"],
                    ROOT,
                )
                self.assertEqual(set(selected), set(environment["source_sha256"]))
                self.assertEqual(selected["README.md"].path, "benchmarks/reporting/mpc07/README.md")
                self.assertEqual(selected["PLAN.md"].path, "benchmarks/reporting/mpc07/PLAN.md")

    def test_unknown_source_names_and_changed_sources_are_rejected(self):
        environment, sources = saved_capture("bounded-policy-0e821c2a", "mpc07-report")
        expected = dict(environment["source_sha256"])
        changed = dict(sources)
        expected["../outside.py"] = "0" * 64
        changed["../outside.py"] = b"outside the allowlist"
        with self.assertRaisesRegex(ValueError, "mandatory source inventory"):
            inventory.authenticate(
                environment["schema"],
                expected,
                changed,
                environment["source_commit"],
                environment["native_source_commit"],
                ROOT,
            )

        changed = dict(sources)
        changed["README.md"] += b"tampered"
        with self.assertRaisesRegex(ValueError, "source snapshot hash differs: README.md"):
            inventory.authenticate(
                environment["schema"],
                environment["source_sha256"],
                changed,
                environment["source_commit"],
                environment["native_source_commit"],
                ROOT,
            )


if __name__ == "__main__":
    unittest.main()
