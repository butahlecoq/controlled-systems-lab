import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.reports.ext07.capture import capture, cmake_build_command
from scripts.reports.ext07.two_parameter_capture import capture as capture_two_parameter


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

    def test_both_capture_commands_reject_invalid_jobs_before_creating_output(self):
        with TemporaryDirectory() as temporary:
            for capture_command in (capture, capture_two_parameter):
                destination = Path(temporary) / capture_command.__module__.rsplit(".", 1)[-1]
                with self.subTest(capture_command=capture_command.__module__):
                    with self.assertRaisesRegex(ValueError, "parallelism"):
                        capture_command(Path("missing-source"), destination, "0" * 40,
                                        "cmake", jobs=0)
                    self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
