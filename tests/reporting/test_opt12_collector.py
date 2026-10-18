from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
import opt12_collect


class CMakeCompilerIdentityTests(unittest.TestCase):
    def test_reads_nested_cxx_compiler_identity_from_file_api(self):
        compiler = {"id": "MSVC", "version": "19.44.35215.0",
                    "path": "C:/VS/VC/bin/cl.exe"}
        self.assertEqual(opt12_collect.cxx_compiler([
            {"language": "C", "compiler": {"id": "MSVC"}},
            {"language": "CXX", "compiler": compiler},
        ]), compiler)

    def test_rejects_incomplete_cxx_compiler_identity(self):
        with self.assertRaisesRegex(ValueError, "compiler record is incomplete"):
            opt12_collect.cxx_compiler([{"language": "CXX", "compiler": {"id": "MSVC"}}])


if __name__ == "__main__":
    unittest.main()
