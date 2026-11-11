from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_mpc06_tube_objective as stage


class Mpc06RoutePolicySourceTests(unittest.TestCase):
    def copy_validation_tree(self, root: Path, bundle: Path) -> tuple[Path, Path]:
        staged_bundle = root / "reports/algorithm-results" / bundle.name
        shutil.copytree(bundle, staged_bundle)
        for relative in stage.SOURCE_MODULES:
            is_snapshot = relative in stage.SOURCE_SNAPSHOT_SHA256
            source = (ROOT / stage.SOURCE_SNAPSHOT_ROOT / relative
                      if is_snapshot else ROOT / relative)
            target = root / stage.SOURCE_SNAPSHOT_ROOT / relative if is_snapshot else root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for relative in (
            "reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1/result.json",
            "benchmarks/scenarios/mpc06-nilpotent-tube-v1.json",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        return root, staged_bundle

    def test_pinned_manifest_rejects_resealed_source_hash_change(self):
        source_bundle = stage.SOURCE
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in source_bundle.iterdir() if path.is_file()}
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / source_bundle.name
            shutil.copytree(source_bundle, copied)
            manifest_path = copied / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source = "benchmarks/scenarios/mpc06-tube-objective-v1.json"
            manifest["source_files"][source] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                                indent=2) + "\n", encoding="utf-8")
            members = sorted(path.name for path in copied.iterdir()
                             if path.is_file() and path.name != "SHA256SUMS")
            (copied / "SHA256SUMS").write_text("".join(
                f"{hashlib.sha256((copied / name).read_bytes()).hexdigest()}  {name}\n"
                for name in members), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "frozen manifest identity"):
                stage.validate(copied)
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in source_bundle.iterdir() if path.is_file()}
        self.assertEqual(after, before)

    def test_live_scientific_source_remains_hash_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            fake_root, copied_bundle = self.copy_validation_tree(Path(temporary), stage.SOURCE)
            with patch.object(stage, "ROOT", fake_root):
                stage.validate(copied_bundle)
                scenario = fake_root / "benchmarks/scenarios/mpc06-tube-objective-v1.json"
                scenario.write_text(scenario.read_text(encoding="utf-8") + " ", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "source hash differs"):
                    stage.validate(copied_bundle)


if __name__ == "__main__":
    unittest.main()
