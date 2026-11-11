from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci/check_local_only_docs.py"


class LocalOnlyDocsTests(unittest.TestCase):
    def repository(self) -> tuple[tempfile.TemporaryDirectory, Path, str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Retention test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "retention@example.invalid"], check=True)
        standing = root / "docs/agents/issue-tracker.md"
        standing.parent.mkdir(parents=True)
        standing.write_text("# Issue tracker\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "docs/agents/issue-tracker.md"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)
        base = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        return temporary, root, base

    def run_checker(self, root: Path, base: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(SCRIPT), "--repo-root", str(root), "--base", base],
                              capture_output=True, text=True, check=False)

    def test_forces_a_tracked_working_document_to_remain_local(self) -> None:
        temporary, root, base = self.repository()
        with temporary:
            plan = root / "docs/superpowers/plans/accidental.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("# New plan\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-f", str(plan.relative_to(root))], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "accidental tracked plan"], check=True)
            result = self.run_checker(root, base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("docs/superpowers/plans/accidental.md", result.stderr)

    def test_accepts_a_properly_named_numbered_adr(self) -> None:
        temporary, root, base = self.repository()
        with temporary:
            adr = root / "docs/architecture/decisions/0005-numerical-membership-witnesses.md"
            adr.parent.mkdir(parents=True)
            adr.write_text("# ADR 0005: Numerical membership witnesses\n\nStatus: accepted\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", str(adr.relative_to(root))], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "add ADR"], check=True)
            result = self.run_checker(root, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_a_working_note_disguised_as_an_adr(self) -> None:
        temporary, root, base = self.repository()
        with temporary:
            adr = root / "docs/architecture/decisions/0005-next-steps.md"
            adr.parent.mkdir(parents=True)
            adr.write_text("# Next steps\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", str(adr.relative_to(root))], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "add disguised note"], check=True)
            result = self.run_checker(root, base)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("0005-next-steps.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
