import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
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

    def test_rejects_empty_source_hash_map(self):
        commit = git("rev-parse", "HEAD").decode("ascii")
        self.assertFalse(report_source_identity.source_hashes_match_commit(ROOT, commit, {}))

    def test_rejects_symlink_even_when_its_target_text_hash_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Report identity test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "report-identity@example.invalid"], check=True)
            (root / "source.py").write_text("value = 1\n", encoding="utf-8")
            (root / "source-link.py").symlink_to("source.py")
            subprocess.run(["git", "-C", str(root), "add", "source.py", "source-link.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "fixture"], check=True)
            commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True).stdout.strip()
            target_text_hash = hashlib.sha256(b"source.py").hexdigest()
            self.assertFalse(report_source_identity.source_hashes_match_commit(
                root, commit, {"source-link.py": target_text_hash}))

    def test_accepts_exact_checkout_hashes_when_captured_commit_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            expected = {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}
            missing_commit = "f" * 40
            self.assertFalse(report_source_identity.source_hashes_match_commit(
                root, missing_commit, expected))
            self.assertTrue(report_source_identity.source_hashes_match_commit_or_checkout(
                root, missing_commit, expected))

    def test_unavailable_commit_fallback_rejects_changed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            expected = {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}
            source.write_text("value = 2\n", encoding="utf-8")
            self.assertFalse(report_source_identity.source_hashes_match_commit_or_checkout(
                root, "f" * 40, expected))

    def test_unavailable_commit_fallback_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            source = root / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            (root / "source-link.py").symlink_to("source.py")
            expected = {"source-link.py": hashlib.sha256(source.read_bytes()).hexdigest()}
            self.assertFalse(report_source_identity.source_hashes_match_commit_or_checkout(
                root, "f" * 40, expected))


if __name__ == "__main__":
    unittest.main()
