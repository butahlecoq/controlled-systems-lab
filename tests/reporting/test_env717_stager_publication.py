"""Check the frozen Pages output of the maintained environment stagers."""

import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Published route IDs and ZIP hashes from the preserved Pages artifact.
REPORTS = (
    (
        "stage_env717_multipoint_cost_game.py",
        "env717-multipoint-cost-game-pilot-v1",
        "env717-multipoint-96e7f4fa2a0f7bc543a5",
        "a5b13f547aa40b59b9e00c3b2245873c914a63745de7d151e1cc26193617e7cd",
    ),
    (
        "stage_env717_broken_triangle.py",
        "env717-broken-triangle-pilot-v1",
        "env717-broken-triangle-9f6110ba0f279f0796e9",
        "989ee72aba36930ffbfe937fe59c192828e1328cc977589b84bae5df60510db1",
    ),
)


class EnvironmentStagerPublicationTests(unittest.TestCase):
    def test_absolute_file_imports_work_without_the_checkout_on_sys_path(self) -> None:
        check_imports = """\
import importlib.util
import sys
from pathlib import Path

for filename in sys.argv[1:]:
    path = Path(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.stage)
"""
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    check_imports,
                    *(str(ROOT / "scripts/reports" / stager) for stager, *_ in REPORTS),
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_script_entrypoints_preserve_routes_and_zip_bytes(self) -> None:
        self.assert_archived_routes(use_module=False)

    def test_module_entrypoints_preserve_routes_and_zip_bytes(self) -> None:
        self.assert_archived_routes(use_module=True)

    def assert_archived_routes(self, *, use_module: bool) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            landing = site / "index.html"
            landing.write_text("<ul></ul>", encoding="utf-8")
            for stager, bundle, route, expected_hash in REPORTS:
                with self.subTest(route=route):
                    invocation = (
                        ["-m", f"scripts.reports.{Path(stager).stem}"]
                        if use_module
                        else [str(ROOT / "scripts/reports" / stager)]
                    )
                    completed = subprocess.run(
                        [
                            sys.executable,
                            *invocation,
                            "--source",
                            str(ROOT / "reports/algorithm-results" / bundle),
                            "--site",
                            str(site),
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout.strip(), route)
                    bundle_zip = site / f"{route}.zip"
                    self.assertEqual(
                        hashlib.sha256(bundle_zip.read_bytes()).hexdigest(), expected_hash
                    )
                    published = {path.name: path.read_bytes() for path in (site / route).iterdir()}
                    with zipfile.ZipFile(bundle_zip) as archive:
                        self.assertEqual(
                            set(archive.namelist()),
                            {"index.html"} | {f"{route}/{name}" for name in published},
                        )
                        for name, content in published.items():
                            self.assertEqual(archive.read(f"{route}/{name}"), content, name)
                    self.assertIn(f'href="{route}/index.html"', landing.read_text(encoding="utf-8"))
