from __future__ import annotations

import sys
import tempfile
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

    def test_validates_every_embedded_build_field_against_selected_release_graph(self):
        compiler = {"id": "MSVC", "version": "19.44.35215.0", "path": "C:/VS/cl.exe"}
        graph = {"cmake": {"generator": "Visual Studio 17 2022"}, "targets": [{
            "name": "csl_opt12_warm_start_measure", "compileGroups": [{
                "language": "CXX", "languageStandard": {"standard": "20"},
                "compileCommandFragments": [{"fragment": "/DWIN32 /D_WINDOWS /EHsc /O2 /Ob2 /DNDEBUG -std:c++20"}],
            }],
        }]}
        cache = {"CMAKE_SYSTEM_PROCESSOR": "AMD64", "CMAKE_GENERATOR_PLATFORM": "x64",
                 "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
                 "CMAKE_CXX_FLAGS_RELEASE": "/O2 /Ob2 /DNDEBUG"}
        record = {"schema": "csl.opt12-build/1", "source_commit": "a" * 40,
                  "build_owner_sha256": "b" * 64, "compiler": compiler["id"],
                  "compiler_version": compiler["version"], "generator": graph["cmake"]["generator"],
                  "architecture": "AMD64/x64", "configured_flags": cache["CMAKE_CXX_FLAGS"],
                  "release_flags": cache["CMAKE_CXX_FLAGS_RELEASE"], "configuration": "Release",
                  "ndebug": True}
        opt12_collect.validate_build_identity(record, source_commit="a" * 40,
                                              build_owner="b" * 64, compiler=compiler,
                                              graph=graph, cache=cache,
                                              system_processor="AMD64")
        for field in ("architecture", "configured_flags", "release_flags", "compiler_version"):
            inconsistent = dict(record)
            inconsistent[field] += " mismatch"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "differs from CMake cache"):
                opt12_collect.validate_build_identity(inconsistent, source_commit="a" * 40,
                                                      build_owner="b" * 64, compiler=compiler,
                                                      graph=graph, cache=cache,
                                                      system_processor="AMD64")
        incomplete = dict(record)
        del incomplete["release_flags"]
        with self.assertRaisesRegex(ValueError, "fields differ"):
            opt12_collect.validate_build_identity(incomplete, source_commit="a" * 40,
                                                  build_owner="b" * 64, compiler=compiler,
                                                  graph=graph, cache=cache,
                                                  system_processor="AMD64")

    def test_reads_system_processor_from_generated_cmake_system_file(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            cmake_files = build / "CMakeFiles" / "3.31.6"
            cmake_files.mkdir(parents=True)
            (cmake_files / "CMakeSystem.cmake").write_text(
                'set(CMAKE_SYSTEM_PROCESSOR "AMD64")\n', encoding="utf-8")
            self.assertEqual(opt12_collect.cmake_system_processor(build), "AMD64")


if __name__ == "__main__":
    unittest.main()
