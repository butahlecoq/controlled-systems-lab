"""Public-log redaction and source-bound collector regressions."""
import importlib
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
from types import ModuleType
import unittest
from pathlib import Path
from unittest.mock import patch

_package_name = "csl_opt07_report_tooling"
_tooling = Path(__file__).resolve().parents[2] / "reports/algorithm-results/tooling/opt07"
if _package_name not in sys.modules:
    package = ModuleType(_package_name)
    package.__path__ = [str(_tooling)]
    sys.modules[_package_name] = package
collector = importlib.import_module(_package_name + ".collect")
sanitize_build_log = collector.sanitize_build_log


class SanitizedLogTests(unittest.TestCase):
    ROOTS = {
        "$SOURCE_ROOT": Path("D:/work/private/repo"),
        "$BUILD_ROOT": Path("D:/work/private/repo/build/opt07"),
        "$TEMP_ROOT": Path("C:/Users/Ada/AppData/Local/Temp"),
        "$USER_ROOT": Path("C:/Users/Ada"),
        "$PROGRAM_FILES": Path("C:/Program Files"),
    }

    def test_both_separator_styles_and_cmake_change_dir(self):
        raw = (
            "Change Dir: 'D:/work/private/repo/build/opt07'\n"
            'Run Clean Command: "C:/Program Files/Tools/MSBuild.exe"\n'
            'CL.exe /O2 /D NDEBUG /std:c++20 '
            '"D:\\work\\private\\repo\\reports\\driver.cpp" '
            '"D:/work/private/repo/build/opt07/Release/driver.obj"\n'
            'Temp: C:\\Users\\Ada\\AppData\\Local\\Temp\\build.log\n'
            'User: c:/users/ada/.cache/config\n'
        )
        clean = sanitize_build_log(raw, self.ROOTS)
        self.assertIn("Change Dir: '$BUILD_ROOT'", clean)
        self.assertIn("$SOURCE_ROOT\\reports\\driver.cpp", clean)
        self.assertIn("$BUILD_ROOT/Release/driver.obj", clean)
        self.assertIn("$PROGRAM_FILES/Tools/MSBuild.exe", clean)
        self.assertIn("$TEMP_ROOT\\build.log", clean)
        self.assertIn("$USER_ROOT/.cache/config", clean)
        self.assertIn("/O2 /D NDEBUG /std:c++20", clean)
        for private in ("D:/work", "D:\\work", "C:/Users", "C:\\Users",
                        "C:/Program Files"):
            self.assertNotIn(private.lower(), clean.lower())

    def test_unknown_absolute_path_fails_closed(self):
        for raw in ("unexpected E:/private/other/file.cpp",
                    "Path:C:/private/file.cpp"):
            with self.subTest(raw=raw), self.assertRaisesRegex(
                    ValueError, "residual absolute"):
                sanitize_build_log(raw, self.ROOTS)

    def test_unc_paths_with_forward_or_mixed_separators_fail_closed(self):
        for path in ("//private-host/share/build.log",
                     "\\/private-host\\share/build.log"):
            with self.subTest(path=path), self.assertRaisesRegex(
                    ValueError, "residual absolute"):
                sanitize_build_log(f"Change Dir: '{path}'", self.ROOTS)

    def test_mocked_collection_saves_raw_digests_with_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "release.log"
            log.write_bytes(b"Clean Release log\n")
            out = root / "saved"
            commit = "a" * 40
            stdout = b'{"purpose":"test","synthetic":true}\n'
            stderr = b"synthetic diagnostic\r\n"
            evidence = {"source_commit": commit,
                        "sanitized_build_log_sha256": hashlib.sha256(
                            log.read_bytes()).hexdigest()}
            argv = ["collect.py", "measure", "--exe", str(root / "build/Release/csl_opt07_measure.exe"),
                    "--source-root", str(root), "--source-commit", commit,
                    "--build-log", str(log), "--concurrent-work-file", str(log),
                    "--out", str(out)]
            with patch.object(sys, "argv", argv), \
                 patch.object(collector, "preflight", return_value=evidence), \
                 patch.object(collector.subprocess, "run", return_value=
                              subprocess.CompletedProcess([], 0, stdout, stderr)), \
                 patch.object(collector, "command", side_effect=lambda *args:
                              commit if args[-2:] == ("rev-parse", "HEAD") else ""), \
                 patch.object(collector, "validate_stream", return_value=
                              {"purpose": "measurement", "fixtures": 3,
                               "batches": 24, "calls": 2400}), \
                 contextlib.redirect_stdout(io.StringIO()):
                collector.main()
            saved = json.loads((out / "collection.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["purpose"], "measurement")
            self.assertEqual(saved["raw_stdout_sha256"], hashlib.sha256(stdout).hexdigest())
            self.assertEqual(saved["raw_stderr_sha256"], hashlib.sha256(stderr).hexdigest())
            self.assertEqual((out / "raw-stdout.jsonl").read_bytes(), stdout)
            self.assertEqual((out / "raw-stderr.txt").read_bytes(), stderr)


if __name__ == "__main__":
    unittest.main()
