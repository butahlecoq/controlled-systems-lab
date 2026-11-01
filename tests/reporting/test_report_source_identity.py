import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import report_source_identity


def git_bytes(*arguments: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *arguments], check=True,
                          capture_output=True).stdout


def git(*arguments: str) -> bytes:
    return git_bytes(*arguments).strip()


class ReportSourceIdentityTests(unittest.TestCase):
    def test_accepts_commit_and_blob_identity(self):
        commit = git("rev-parse", "HEAD").decode("ascii")
        source = git_bytes("show", f"{commit}:scripts/reports/report_source_identity.py")
        expected = {"scripts/reports/report_source_identity.py": hashlib.sha256(source).hexdigest()}
        self.assertTrue(report_source_identity.source_hashes_match_commit(ROOT, commit, expected))

    def test_rejects_tree_object_as_commit(self):
        commit = git("rev-parse", "HEAD").decode("ascii")
        tree = git("rev-parse", f"{commit}^{{tree}}").decode("ascii")
        source = git_bytes("show", f"{commit}:scripts/reports/report_source_identity.py")
        expected = {"scripts/reports/report_source_identity.py": hashlib.sha256(source).hexdigest()}
        self.assertFalse(report_source_identity.source_hashes_match_commit(ROOT, tree, expected))

    def test_rejects_tree_path(self):
        commit = git("rev-parse", "HEAD").decode("ascii")
        tree = git("show", f"{commit}:scripts")
        expected = {"scripts": hashlib.sha256(tree).hexdigest()}
        self.assertFalse(report_source_identity.source_hashes_match_commit(ROOT, commit, expected))


if __name__ == "__main__":
    unittest.main()
