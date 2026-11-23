import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[2] / "scripts/ci/check_comment_ratchet.py"


class CommentRatchetTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.file = self.root / "scripts/ci/tool.py"
        self.file.parent.mkdir(parents=True)
        self.file.write_text("# First existing comment\n# Another existing comment\nx = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Existing comment debt")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def checker(self, *args):
        return subprocess.run(
            [sys.executable, str(CHECKER), *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_allows_deletion_but_rejects_replacement_and_duplicate(self):
        self.file.write_text("# Another existing comment\nx = 1\n")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)

        for added in ("# New comment", "# Another existing comment"):
            with self.subTest(added=added):
                self.file.write_text(f"# Another existing comment\n{added}\nx = 1\n")
                result = self.checker("check", "--base", "HEAD")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"scripts/ci/tool.py:2: {added}", result.stderr)

    def test_accepts_required_directives_and_hashes_in_strings(self):
        self.file.write_text(
            "#!/usr/bin/env python3\n# coding: utf-8\n# SPDX-License-Identifier: MIT\n"
            'x = "# prose in a string"  # noqa: F841,\tF401\n'
            "values = []  # type: list[int]\n"
            "def f(values):\n    # type: (list[int]) -> None\n    pass\n"
            "ignored = x  # type: ignore[assignment]\n"
            "# ruff: isort: skip_file\n"
            "# isort: split\n"
            'text = """# text in a multiline string\n"""\n'
        )
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_type_prefix_cannot_disguise_new_prose(self):
        for prefix in ("type", "TYPE"):
            with self.subTest(prefix=prefix):
                self.file.write_text(f"# {prefix}: This is prose with no typing action\nx = 1\n")
                result = self.checker("check", "--base", "HEAD")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"scripts/ci/tool.py:1: # {prefix}: This is prose", result.stderr)

    def test_free_form_ignore_payload_is_prose(self):
        self.file.write_text("x = 1  # type: ignore[this is an excuse]\n")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("scripts/ci/tool.py:1: # type: ignore[this is an excuse]", result.stderr)

    def test_rejects_a_cookie_like_comment_after_the_encoding_header(self):
        self.file.write_text("x = 1\n# coding: utf-8\n")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("scripts/ci/tool.py:2: # coding: utf-8", result.stderr)

    def test_an_old_comment_cannot_return_after_its_deletion_is_committed(self):
        self.file.write_text("x = 1\n")
        self.git("commit", "-qam", "Remove comment debt")
        self.file.write_text("# First existing comment\nx = 1\n")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("scripts/ci/tool.py:1: # First existing comment", result.stderr)

    def test_checks_new_tracked_files_and_ignores_other_directories(self):
        outside = self.root / "outside.py"
        outside.write_text("# Outside initial scope\n")
        other = self.file.with_name("new.py")
        other.write_text("# Forbidden in new file\n")
        self.git("add", ".")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("scripts/ci/new.py:1: # Forbidden in new file", result.stderr)
        self.assertNotIn("outside.py", result.stderr)

    def test_checks_catalogue_ci_test_and_cmake_test_scopes(self):
        paths = (
            "scripts/catalogue/qualify.py",
            "tests/ci/test_guard.py",
            "tests/cmake/test_archive.py",
        )
        for path in paths:
            source = self.root / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# New prose\n")
        self.git("add", ".")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        for path in paths:
            self.assertIn(f"{path}:1: # New prose", result.stderr)

    def test_checks_the_report_landing_source_scope(self):
        source = self.root / "scripts/reports/landing.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# New report source prose\n")
        self.git("add", ".")
        result = self.checker("check", "--base", "HEAD")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("scripts/reports/landing.py:1: # New report source prose", result.stderr)

    def test_inventory_reads_the_requested_commit_and_counts_physically_removable_lines(self):
        self.file.write_text('# comment only\nx = "#"  # inline\n')
        self.git("commit", "-qam", "Change comment inventory")
        self.file.write_text("# worktree edit\n")
        result = self.checker("inventory", "--ref", "HEAD", "scripts/ci")
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads(result.stdout)
        self.assertEqual(inventory["counts"], {"comment_only": 1, "inline": 1, "directives": 0})
        self.assertEqual(
            [item["text"] for item in inventory["comments"]], ["# comment only", "# inline"]
        )
