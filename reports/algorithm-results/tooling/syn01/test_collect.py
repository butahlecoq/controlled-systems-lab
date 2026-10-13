"""Tests for extracting reproducible Release compiler evidence from configured build files."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

TOOLING = Path(__file__).resolve().parent
ROOT = TOOLING.parents[3]
sys.path.insert(0, str(TOOLING))
SPEC = importlib.util.spec_from_file_location("csl_syn01_test_collect", TOOLING / "collect.py")
collect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect)


class Syn01BuildEvidenceTests(unittest.TestCase):
    def test_release_metadata_uses_generated_project_properties_and_hashes_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / "CMakeCache.txt").write_text("""CMAKE_GENERATOR:INTERNAL=Visual Studio 17 2022
CMAKE_GENERATOR_PLATFORM:INTERNAL=x64
CMAKE_CXX_FLAGS_RELEASE:STRING=/O2 /Ob2 /DNDEBUG
""", encoding="utf-8")
            (build / "csl_syn01_nominal_forward_report.vcxproj").write_text("""<Project xmlns=\"http://schemas.microsoft.com/developer/msbuild/2003\">
<ItemDefinitionGroup Condition=\"'$(Configuration)|$(Platform)'=='Release|x64'">
<ClCompile><LanguageStandard>stdcpp20</LanguageStandard><Optimization>MaxSpeed</Optimization>
<WarningLevel>Level4</WarningLevel><TreatWarningAsError>true</TreatWarningAsError>
<ConformanceMode>true</ConformanceMode><RuntimeLibrary>MultiThreadedDLL</RuntimeLibrary>
<PreprocessorDefinitions>NDEBUG;CMAKE_INTDIR=\"Release\"</PreprocessorDefinitions></ClCompile>
</ItemDefinitionGroup></Project>""", encoding="utf-8")
            report = collect.build_configuration(build, "MSVC", "19.44", "cl.exe", "cmake 3.31", b"Release build evidence")
            self.assertEqual("c++20", report["cxx_standard"])
            self.assertIn("/O2", report["effective_release_flags"])
            self.assertIn("/W4", report["effective_release_flags"])
            self.assertIn("/permissive-", report["effective_release_flags"])
            self.assertEqual(64, len(report["evidence_sha256"]["build_configuration_file"]))
            self.assertEqual("Release", report["configuration"])


if __name__ == "__main__":
    unittest.main()
