"""Public-log redaction and source-bound collector regressions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "reports/algorithm-results/tooling/opt07"))
from collect import sanitize_build_log  # noqa: E402


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
        with self.assertRaisesRegex(ValueError, "residual absolute"):
            sanitize_build_log("unexpected E:/private/other/file.cpp", self.ROOTS)


if __name__ == "__main__":
    unittest.main()
