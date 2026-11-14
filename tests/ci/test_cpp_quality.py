"""Real Git/filesystem boundary checks; native workflows qualify actual compilers."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci import check_cpp_quality as quality


class NativeQualityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "source"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("src/example.cpp", "int value() { return 1; }\n")
        self.write("include/csl/example.hpp", "#pragma once\nint value();\n")
        self.write("CMakeLists.txt", "cmake_minimum_required(VERSION 3.31)\n")
        self.write("CMakePresets.json", '{"version": 6}\n')
        self.write("requirements-cpp-quality.txt", "clang-tidy==23.1.3\n")
        self.write(".clang-format", "BasedOnStyle: LLVM\n")
        self.write(".clang-tidy", "Checks: '-*,bugprone-integer-division'\n")
        self.write(
            "scripts/ci/check_cpp_quality.py",
            "# Fixture identity, not an executed compiler gate.\n",
        )
        self.policy: dict[str, object] = {
            "schema": "csl.cpp-quality-policy/1",
            "roots": ["include", "src", "tests", "examples"],
            "frozen": [],
            "expected_compile_failures": [],
        }
        self.save_policy()
        self.build = Path(temporary.name) / "build"
        self.build.mkdir()

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def save_policy(self) -> None:
        self.write("scripts/ci/cpp-quality-policy.json", json.dumps(self.policy))

    def save_profile(self) -> dict[str, object]:
        source = quality.corpus(self.root)
        inputs = {
            p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in self.root.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }
        manifest: dict[str, object] = {
            "schema": "csl.cpp-quality-profile/1",
            "source_root": str(self.root),
            "binary_root": str(self.build),
            "profile": "core",
            "generator": "Ninja",
            "highs": "OFF",
            "qhull": "OFF",
            "casadi": "OFF",
            "testing": "ON",
            "inputs_sha256": inputs,
            "public_header_contexts": {
                str(self.build / "cpp-quality-headers/example.cpp"): "include/csl/example.hpp"
            },
        }
        self.assertEqual(set(inputs), quality.configuration_inputs(source))
        (self.build / "cpp-quality-profile.json").write_text(json.dumps(manifest))
        (self.build / "CMakeCache.txt").write_text(
            f"CMAKE_HOME_DIRECTORY:INTERNAL={self.root}\n"
            "CMAKE_GENERATOR:INTERNAL=Ninja\n"
            "CSL_CPP_QUALITY:BOOL=ON\n"
            "CSL_CPP_QUALITY_PROFILE:STRING=core\n"
            "CSL_ENABLE_HIGHS:BOOL=OFF\n"
            "CSL_ENABLE_QHULL:BOOL=OFF\n"
            "CSL_ENABLE_CASADI:BOOL=OFF\n"
            "BUILD_TESTING:BOOL=ON\n"
        )
        return manifest

    def test_untracked_future_source_and_header_enter_scope(self) -> None:
        self.write("src/new/nested.cpp", "int future() { return 2; }\n")
        self.write("include/csl/future.hpp", "#pragma once\n")
        source = quality.corpus(self.root)
        self.assertIn("src/new/nested.cpp", source.sources)
        self.assertIn("include/csl/future.hpp", source.public_headers)

    def test_default_test_main_must_use_its_compiled_vendor_owner(self) -> None:
        self.write("tests/future.cpp", "#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN\n")
        with self.assertRaisesRegex(ValueError, "link doctest::doctest_with_main"):
            quality.corpus(self.root)

    def test_custom_test_main_must_preserve_its_own_entry_point(self) -> None:
        self.write("tests/custom.cpp", "# define DOCTEST_CONFIG_IMPLEMENT\nint main() {}\n")
        with self.assertRaisesRegex(
            ValueError, "custom main entry points link csl_doctest_runtime"
        ):
            quality.corpus(self.root)

    def test_compiler_flags_cannot_restore_inline_vendor_implementation(self) -> None:
        for words in (
            ["clang++", "-DDOCTEST_CONFIG_IMPLEMENT_WITH_MAIN=1"],
            ["clang++", "-D", "DOCTEST_CONFIG_IMPLEMENT"],
            ["cl", "/DDOCTEST_CONFIG_IMPLEMENT"],
        ):
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, "compiled target"):
                quality.check_test_runtime_flags({"arguments": words}, self.root / "tests/a.cpp")

    def test_quoted_or_commented_example_is_not_a_runtime_definition(self) -> None:
        self.write(
            "tests/documented.cpp",
            'const char *example = R"doc(\n#define DOCTEST_CONFIG_IMPLEMENT\n)doc";\n'
            "/*\n#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN\n*/\n",
        )
        quality.corpus(self.root)

    def test_line_splicing_cannot_restore_inline_implementation(self) -> None:
        self.write("tests/spliced.cpp", "#def" + "\\" + "\nine DOCTEST_CONFIG_IMPLEMENT\n")
        with self.assertRaisesRegex(ValueError, "inline Doctest implementation"):
            quality.corpus(self.root)

    def test_source_symlink_cannot_import_foreign_bytes(self) -> None:
        foreign = self.root.parent / "foreign.cpp"
        foreign.write_text("int foreign;\n")
        (self.root / "src/foreign.cpp").symlink_to(foreign)
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            quality.corpus(self.root)

    def test_empty_scope_is_not_a_successful_format_check(self) -> None:
        self.policy["roots"] = ["absent"]
        self.save_policy()
        with self.assertRaisesRegex(ValueError, "No retained native sources"):
            quality.corpus(self.root)

    def test_foreign_database_owner_is_rejected_before_tool_execution(self) -> None:
        manifest = self.save_profile()
        manifest["source_root"] = str(self.root.parent / "another-checkout")
        (self.build / "cpp-quality-profile.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "another source tree"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_missing_future_context_is_not_hidden_by_old_manifest(self) -> None:
        self.save_profile()
        self.write("src/future.cpp", "int future;\n")
        with self.assertRaisesRegex(ValueError, "New native files lack configured ownership"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_changed_native_bytes_require_reconfiguration(self) -> None:
        self.save_profile()
        self.write("src/example.cpp", "int value() { return 2; }\n")
        with self.assertRaisesRegex(ValueError, "Stale native profile input src/example.cpp"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_new_configuration_file_requires_reconfiguration(self) -> None:
        self.save_profile()
        self.write("cmake/NewOwner.cmake", "# New owner input\n")
        with self.assertRaisesRegex(ValueError, "configuration input membership changed"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_missing_public_header_context_is_rejected(self) -> None:
        manifest = self.save_profile()
        manifest["public_header_contexts"] = {}
        (self.build / "cpp-quality-profile.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "standalone-header coverage differs"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_profile_name_cannot_relabel_adapter_flags(self) -> None:
        manifest = self.save_profile()
        manifest["profile"] = "highs"
        (self.build / "cpp-quality-profile.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "declared owner"):
            quality.profile_manifest(self.build, quality.corpus(self.root))

    def test_unknown_first_party_dependency_cannot_disappear(self) -> None:
        path = self.write("src/domain.inc", "int injected;\n")
        with self.assertRaisesRegex(ValueError, "Unregistered first-party compiler input"):
            quality.origin(path.resolve(), quality.corpus(self.root), self.build, [], [])

    def test_modified_staged_header_is_not_current_source_qualification(self) -> None:
        prefix = self.build / "prefix"
        header = prefix / "include/csl/example.hpp"
        header.parent.mkdir(parents=True)
        header.write_text("#pragma once\nint changed();\n")
        with self.assertRaisesRegex(ValueError, "Installed header differs from current source"):
            quality.origin(header.resolve(), quality.corpus(self.root), self.build, [], [prefix])

    def test_modified_staged_consumer_cannot_silently_leave_analysis(self) -> None:
        staged = self.build / "installed-consumer/source/example.cpp"
        staged.parent.mkdir(parents=True)
        staged.write_text("int value() { return 2; }\n")
        with self.assertRaisesRegex(ValueError, "Installed consumer differs from current source"):
            quality.copied_origin(staged, quality.corpus(self.root))

    def test_capture_digest_mention_does_not_override_named_member(self) -> None:
        frozen = self.write("tests/captured.cpp", "int captured;\n")
        owner = self.write(
            "reports/frozen.json",
            json.dumps({"sha256": quality.digest(frozen), "member": "source/other.cpp"}),
        )
        self.policy["frozen"] = [
            {
                "path": "tests/captured.cpp",
                "owner": "reports/frozen.json",
                "owner_sha256": quality.digest(owner),
                "digest_key": "sha256",
                "member_key": "member",
                "member": "source/captured.cpp",
            }
        ]
        self.save_policy()
        with self.assertRaisesRegex(ValueError, "Captured source member changed"):
            quality.corpus(self.root)

    def test_source_edit_cannot_be_excused_by_unchanged_capture_record(self) -> None:
        frozen = self.write("tests/captured.cpp", "int captured;\n")
        owner = self.write(
            "reports/frozen.json",
            json.dumps({"sha256": quality.digest(frozen), "member": "source/captured.cpp"}),
        )
        self.policy["frozen"] = [
            {
                "path": "tests/captured.cpp",
                "owner": "reports/frozen.json",
                "owner_sha256": quality.digest(owner),
                "digest_key": "sha256",
                "member_key": "member",
                "member": "source/captured.cpp",
            }
        ]
        self.save_policy()
        frozen.write_text("int changed;\n")
        with self.assertRaisesRegex(ValueError, "Captured native input changed"):
            quality.corpus(self.root)

    def coverage_receipts(self, source: quality.Corpus) -> list[dict[str, object]]:
        # Metadata fixtures exercise reconciliation only; actual native workflows
        # produce receipts after compiler/dependency/tool qualification.
        inputs = {p: quality.digest(source.root / p) for p in quality.configuration_inputs(source)}
        return [
            {
                "schema": "csl.cpp-quality-receipt/1",
                "status": "passed",
                "llvm": quality.LLVM,
                "profile": profile,
                "source_hashes": source.hashes,
                "quality_inputs_sha256": inputs,
                "checked_sources": sorted(source.sources),
                "checked_headers": sorted(source.public_headers),
                "standalone_headers": sorted(source.public_headers),
                "installed_standalone_headers": sorted(source.public_headers),
                "expected_failures": [],
            }
            for profile in quality.PROFILE_OPTIONS
        ]

    def test_public_contexts_cannot_hide_unobserved_private_header(self) -> None:
        self.write("src/internal.hpp", "#pragma once\nint internal();\n")
        source = quality.corpus(self.root)
        with self.assertRaisesRegex(
            ValueError, "Uncovered private/test/example header: src/internal.hpp"
        ):
            quality.coverage(self.coverage_receipts(source), source)

    def test_normal_sources_cannot_hide_missing_actual_compiler_refusal(self) -> None:
        self.write("tests/forge.cpp", "int forged;\n")
        self.policy["expected_compile_failures"] = ["tests/forge.cpp"]
        self.save_policy()
        source = quality.corpus(self.root)
        with self.assertRaisesRegex(
            ValueError, "Uncovered expected compiler refusal: tests/forge.cpp"
        ):
            quality.coverage(self.coverage_receipts(source), source)

    def test_receipts_cannot_outlive_the_quality_policy(self) -> None:
        source = quality.corpus(self.root)
        receipts = self.coverage_receipts(source)
        self.write(".clang-tidy", "Checks: '-*,clang-analyzer-core.*'\n")
        with self.assertRaisesRegex(ValueError, "stale quality/configuration inputs"):
            quality.coverage(receipts, source)

    def test_source_headers_cannot_mask_unavailable_installed_header(self) -> None:
        source = quality.corpus(self.root)
        receipts = self.coverage_receipts(source)
        for receipt in receipts:
            receipt["installed_standalone_headers"] = []
        with self.assertRaisesRegex(ValueError, "Uncovered installed standalone header"):
            quality.coverage(receipts, source)

    def test_coverage_rejects_missing_optional_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires core, HiGHS"):
            quality.coverage([], quality.corpus(self.root))


if __name__ == "__main__":
    unittest.main()
