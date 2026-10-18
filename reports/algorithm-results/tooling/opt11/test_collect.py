"""Focused checks for the source-bound Release build-log gate."""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collect import (HARNESS, TIMING_TRANSLATION_UNITS, compiler_identity,
                     validate_release_build_evidence, write_utf8_lf)


class ReleaseBuildEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / "opt11-source-test"
        self.build_root = Path.cwd() / "opt11-build-test"
        self.exe = self.build_root / "Release" / "csl_opt11_measure.exe"
        self.compiler_path = self.build_root / "toolchain" / "cl.exe"
        self.commit = "a" * 40
        self.harness_hash = "b" * 64
        self.log = self.valid_log()

    def compile_line(self, source: str, extra: str = "") -> str:
        path = (self.root / source).as_posix().replace("/", "\\")
        compiler = self.compiler_path.as_posix().replace("/", "\\")
        return (f'"{compiler}" /O2 /std:c++20 /D NDEBUG /D "CMAKE_INTDIR=\\"Release\\"" '
                f'{extra} "{path}"')

    def valid_log(self) -> str:
        lines = ["Run Clean Command: MSBuild.exe /t:Clean"]
        for source in TIMING_TRANSLATION_UNITS:
            lines.append(self.compile_line(source))
        lines.append(self.compile_line(
            HARNESS,
            f'/D "CSL_OPT11_SOURCE_COMMIT=\\"{self.commit}\\"" '
            f'/D "CSL_OPT11_HARNESS_SHA256=\\"{self.harness_hash}\\""'))
        exe = self.exe.as_posix().replace("/", "\\")
        lines.append(f'link.exe /OUT:"{exe}" csl\\Release\\csl_hull.lib '
                     'csl\\Release\\csl_highs_lp.lib')
        lines.append(f'csl_opt11_measure.vcxproj -> {exe}')
        return "\n".join(lines)

    def test_accepts_full_clean_release_graph_bound_to_source(self):
        validate_release_build_evidence(self.log, self.root, self.build_root,
                                        self.exe, self.commit, self.harness_hash,
                                        str(self.compiler_path))

    def test_rejects_missing_timing_translation_unit(self):
        incomplete = self.log.replace(self.compile_line("src/adapters/lp/highs.cpp") + "\n", "")
        with self.assertRaisesRegex(ValueError, "src/adapters/lp/highs.cpp"):
            validate_release_build_evidence(incomplete, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_rejects_log_without_clean_first_evidence(self):
        incomplete = self.log.replace("Run Clean Command: MSBuild.exe /t:Clean\n", "")
        with self.assertRaisesRegex(ValueError, "explicit clean-first MSBuild command"):
            validate_release_build_evidence(incomplete, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_rejects_link_library_from_wrong_root(self):
        wrong_root = self.log.replace("csl\\Release\\csl_hull.lib",
                                      "other\\csl\\Release\\csl_hull.lib")
        with self.assertRaisesRegex(ValueError, "both expected libraries under the verified build root"):
            validate_release_build_evidence(wrong_root, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_rejects_missing_release_optimization_flag(self):
        line = self.compile_line("src/geometry/hull_reducer.cpp")
        incomplete = self.log.replace(line, line.replace("/O2", "/Od"))
        with self.assertRaisesRegex(ValueError, "src/geometry/hull_reducer.cpp"):
            validate_release_build_evidence(incomplete, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_rejects_source_compiled_from_different_root(self):
        line = self.compile_line("src/adapters/lp/highs.cpp")
        wrong_source = line.replace(str(self.root).replace("/", "\\"),
                                    str(self.root.parent / "other-source").replace("/", "\\"))
        incomplete = self.log.replace(line, wrong_source)
        with self.assertRaisesRegex(ValueError, "src/adapters/lp/highs.cpp"):
            validate_release_build_evidence(incomplete, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_rejects_timing_compile_from_different_compiler(self):
        line = self.compile_line("src/geometry/hull_reducer.cpp")
        other = line.replace(str(self.compiler_path).replace("/", "\\"),
                             str(self.build_root / "other" / "cl.exe").replace("/", "\\"))
        log = self.log.replace(line, other)
        with self.assertRaisesRegex(ValueError, "src/geometry/hull_reducer.cpp"):
            validate_release_build_evidence(log, self.root, self.build_root,
                                            self.exe, self.commit, self.harness_hash,
                                            str(self.compiler_path))

    def test_compiler_identity_comes_from_hashed_generated_cmake_source(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            compiler_dir = build / "CMakeFiles" / "3.31.6"
            compiler_dir.mkdir(parents=True)
            compiler_file = compiler_dir / "CMakeCXXCompiler.cmake"
            compiler_file.write_text(
                'set(CMAKE_CXX_COMPILER "C:/Program Files/MSVC/cl.exe")\n'
                'set(CMAKE_CXX_COMPILER_ID "MSVC")\n'
                'set(CMAKE_CXX_COMPILER_VERSION "19.44.1")\n', encoding="utf-8")
            compiler_id, version, path, sanitized, relative = compiler_identity(
                build, {"$PROGRAM_FILES": Path("C:/Program Files")})
            self.assertEqual((compiler_id, version, path), ("MSVC", "19.44.1", "C:/Program Files/MSVC/cl.exe"))
            self.assertIn(b'set(CMAKE_CXX_COMPILER_ID "MSVC")', sanitized)
            self.assertNotIn(b"C:/Program Files", sanitized)
            self.assertEqual(relative, "CMakeFiles/3.31.6/CMakeCXXCompiler.cmake")

    def test_utf8_lf_persistence_does_not_translate_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sanitized.txt"
            written = write_utf8_lf(target, "first\nsecond\n")
            self.assertEqual(written, b"first\nsecond\n")
            self.assertEqual(target.read_bytes(), b"first\nsecond\n")


if __name__ == "__main__":
    unittest.main()
