"""Exact criterion arithmetic for the displayed L13 Table 2 decimals.

This checks printed coordinates only. The synchronization term is from the
related A09 MATLAB routine; no publication-generating source is asserted.
"""
from fractions import Fraction


TARGET = (Fraction(60), Fraction(0), Fraction(24), Fraction(0))

# L13 Table 2, PDF p. 14. Keep the reported criteria as printed.
ROWS = (
    ("simplified/open_loop", ("60.08", "47.7", "24.09", "-22.2"), "115.79"),
    ("simplified/adaptive", ("59.82", "20.3", "23.91", "4.5"), "22.658"),
    ("original/open_loop", ("60.26", "22.6", "23.86", "5"), "25.295"),
    ("original/adaptive", ("60", "20.3", "24", "4.5"), "22.657"),
)


def squared_criteria(coordinates):
    """Return Eq. (16) and A09-candidate squared norms as exact fractions."""
    state = tuple(Fraction(value) for value in coordinates)
    if len(state) != 4:
        raise ValueError("L13 terminal state must have four coordinates")
    euclidean = sum((value - goal) ** 2 for value, goal in zip(state, TARGET))
    synchronization = Fraction(5, 2) * state[3] - state[1]
    return euclidean, euclidean + synchronization ** 2


def main():
    for label, coordinates, reported in ROWS:
        euclidean, augmented = squared_criteria(coordinates)
        print(f"{label}: euclidean_squared={euclidean} "
              f"synchronization_squared={augmented} reported={reported}")


if __name__ == "__main__":
    main()
