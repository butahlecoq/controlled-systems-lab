"""Observable checks on the candidate enclosure's saved numerical result."""

from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "research"))
import issue4_volterra_enclosure as checker  # noqa: E402


def arctan_inverse(n: int) -> Decimal:
    x = Decimal(1) / n
    total = Decimal(0)
    power = x
    for k in range(150):
        term = power / (2 * k + 1)
        total += -term if k % 2 else term
        power *= x * x
    return total


class CandidateEnclosureTest(unittest.TestCase):
    def test_step_and_one_step_quadratic_error(self) -> None:
        record = checker.run()
        step_lo, step_hi = map(Decimal, record["step_size"])
        with localcontext() as context:
            context.prec = 70
            step = (16 * arctan_inverse(5) - 4 * arctan_inverse(239)) / (18 * Decimal(2).sqrt())
            self.assertLessEqual(step_lo, step)
            self.assertLessEqual(step, step_hi)
            first = record["rows"][0]["same_control_error"]
            for coordinate, exact in zip(first, (-Decimal("0.006") * step,
                                                 Decimal("0.004") * step)):
                self.assertLessEqual(Decimal(coordinate[0]), exact)
                self.assertLessEqual(exact, Decimal(coordinate[1]))

    def test_complete_sample_histories_fit_all_saved_boxes(self) -> None:
        record = checker.run()
        with localcontext() as context:
            context.prec = 70
            step = (16 * arctan_inverse(5) - 4 * arctan_inverse(239)) / (18 * Decimal(2).sqrt())
            a, b, c, d, gain = map(Decimal, ("0.9", "0.003", "0.8", "0.002", "0.85"))
            for history in (lambda i: Decimal("-0.3"), lambda i: Decimal(0),
                            lambda i: Decimal("0.3"),
                            lambda i: Decimal("0.3") if i % 2 else Decimal("-0.3")):
                reference = [Decimal(410), Decimal(300)]
                linear = [Decimal(1), Decimal(2)]
                nonlinear = linear.copy()
                for index, row in enumerate(record["rows"]):
                    r1, r2 = reference
                    reference = [r1 + step * (a * r1 - b * r1 * r2),
                                 r2 + step * (-c * r2 + d * r1 * r2)]
                    r1, r2 = reference
                    matrix = ((1 + step * (a - b * r2), -step * b * r1),
                              (step * d * r2, 1 + step * (-c + d * r1)))
                    u = history(index)
                    def advance(state):
                        return [matrix[0][0] * state[0] + matrix[0][1] * state[1] + step * gain * u,
                                matrix[1][0] * state[0] + matrix[1][1] * state[1]]
                    product = nonlinear[0] * nonlinear[1]
                    nonlinear = advance(nonlinear)
                    nonlinear = [nonlinear[0] - step * b * product,
                                 nonlinear[1] + step * d * product]
                    linear = advance(linear)
                    for label, values in (("reference", reference), ("linear", linear),
                                          ("nonlinear", nonlinear),
                                          ("same_control_error", [nonlinear[j] - linear[j] for j in range(2)])):
                        for bounds, value in zip(row[label], values):
                            self.assertLessEqual(Decimal(bounds[0]), value, (index, label))
                            self.assertLessEqual(value, Decimal(bounds[1]), (index, label))
        self.assertEqual(record["error_linf_upper"], "11.384829795848264")


if __name__ == "__main__":
    unittest.main()
