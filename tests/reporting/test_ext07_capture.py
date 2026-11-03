import unittest
from pathlib import Path

from scripts.reports.ext07.capture import cmake_build_command


class CMakeBuildCommandTests(unittest.TestCase):
    def test_unix_generator_does_not_receive_msbuild_switches(self):
        command = cmake_build_command("cmake", Path("build"), "target", 2,
                                      "Unix Makefiles", ("/p:PreferredUILang=en-US",))

        self.assertEqual(command, ["cmake", "--build", "build", "--config", "Release",
                                   "--target", "target", "--parallel", "2"])

    def test_visual_studio_generator_receives_only_declared_msbuild_switches(self):
        command = cmake_build_command("cmake", Path("build"), "target", 4,
                                      "Visual Studio 17 2022",
                                      ("/nologo", "/p:PreferredUILang=en-US"))

        self.assertEqual(command[-3:], ["--", "/nologo", "/p:PreferredUILang=en-US"])

    def test_rejects_nonpositive_parallelism(self):
        with self.assertRaises(ValueError):
            cmake_build_command("cmake", Path("build"), "target", 0, "Unix Makefiles")


if __name__ == "__main__":
    unittest.main()
