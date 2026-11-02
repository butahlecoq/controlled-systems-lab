"""Validate and checksum the B04-C exact-dyadic evidence bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from check_b04_c_exact_fiber import DEFAULT_RECORD, check
from render_b04_c_exact_fiber import main as render
from render_b04_c_exact_fiber_report import main as render_report

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / "docs/research/evidence/b04-c-exact-dyadic-v1"
PUBLICATION_BUNDLE = ROOT / "reports/algorithm-results/b04-c-exact-dyadic-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    verified = check(DEFAULT_RECORD)
    render()
    render_report()
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.reporting.test_b04_c_exact_fiber", "-v"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (BUNDLE / "verification.json").write_text(
        json.dumps(verified, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (BUNDLE / "tests.txt").write_text(tests.stdout, encoding="utf-8")
    if tests.returncode != 0:
        raise SystemExit(f"focused tests failed (exit {tests.returncode}); see {BUNDLE / 'tests.txt'}")

    evidence_files = ("README.md", "record.json", "trajectory.svg", "index.html", "verification.json", "tests.txt")
    source_files = (
        "docs/research/tools/b04_c_exact_profile.py",
        "docs/research/tools/build_b04_c_exact_fiber.py",
        "docs/research/tools/check_b04_c_exact_fiber.py",
        "docs/research/tools/render_b04_c_exact_fiber.py",
        "docs/research/tools/render_b04_c_exact_fiber_report.py",
        "docs/research/tools/finalize_b04_c_exact_fiber.py",
        "tests/reporting/test_b04_c_exact_fiber.py",
        "docs/research/tools/README.md",
        ".github/workflows/algorithm-reports.yml",
        "scripts/reports/b04_c_exact_registered_reports.py",
        "scripts/reports/b04_c_exact_publication_policy.py",
        "scripts/reports/registered_reports.py",
        "scripts/reports/publication_policy.py",
        "scripts/reports/report_data.py",
        "scripts/reports/schema3_publication_policies.py",
        "scripts/reports/site.py",
        "scripts/reports/landing.py",
        "scripts/reports/visual_examples.py",
        "scripts/reports/algorithm_visual_coverage.json",
    )
    manifest = {
        "schema": "csl.b04-c-exact-dyadic-manifest/1",
        "scenario_id": "B04-c-exact-dyadic-20261102",
        "source_commit": json.loads(DEFAULT_RECORD.read_text(encoding="utf-8"))["source_commit"],
        "publication_scope": "Research-only report-index entry: external Python exact-arithmetic audit, not a registered Strategy A result or compiled complete-family publication. The numerical source commit remains the record source_commit.",
        "evidence_files": {name: digest(BUNDLE / name) for name in evidence_files},
        "source_files": {name: digest(ROOT / name) for name in source_files},
        "verification": verified,
        "commands": [
            "python docs/research/tools/build_b04_c_exact_fiber.py",
            "python docs/research/tools/finalize_b04_c_exact_fiber.py",
        ],
    }
    (BUNDLE / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copytree(BUNDLE, PUBLICATION_BUNDLE, dirs_exist_ok=True)
    print(json.dumps({"manifest": str((BUNDLE / "manifest.json").relative_to(ROOT)),
                      "scenario_id": manifest["scenario_id"],
                      "tests": "passed", "evidence_files": len(evidence_files)}, sort_keys=True))


if __name__ == "__main__":
    main()
