"""Literal public checks for arithmetic on L13's printed Table 2 coordinates."""
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent


class L13DisplayedCriteriaTests(unittest.TestCase):
    def test_optimized_cli_reports_all_four_printed_rows(self):
        result = subprocess.run(
            [sys.executable, "-B", "-O", str(HERE / "check_l13_displayed_criteria.py")],
            text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "simplified/open_loop: euclidean_squared=5536289/2000 synchronization_squared=26836769/2000 reported=115.79",
            "simplified/adaptive: euclidean_squared=864761/2000 synchronization_squared=514283/1000 reported=22.658",
            "original/open_loop: euclidean_squared=669809/1250 synchronization_squared=1594643/2500 reported=25.295",
            "original/adaptive: euclidean_squared=21617/50 synchronization_squared=205697/400 reported=22.657",
        ])

    def test_custom_coordinates_distinguish_the_two_criteria(self):
        sys.path.insert(0, str(HERE))
        try:
            from check_l13_displayed_criteria import squared_criteria
        finally:
            sys.path.pop(0)
        self.assertEqual(squared_criteria(("60", "4", "24", "2")),
                         (Fraction(20), Fraction(21)))


if __name__ == "__main__":
    unittest.main()
