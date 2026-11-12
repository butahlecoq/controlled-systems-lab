"""Print checked analytic values for the learning book's common 2D toy."""
from __future__ import annotations

from math import sqrt


def main() -> None:
    square_vertices = ((-1.0, -1.0), (-1.0, 1.0), (1.0, -1.0), (1.0, 1.0))
    directions = ((1.0, 0.0), (1.0, 1.0))
    for direction in directions:
        square_support = max(x * direction[0] + y * direction[1]
                             for x, y in square_vertices)
        disk_support = sqrt(2.0) * sqrt(direction[0] ** 2 + direction[1] ** 2)
        print(f"d={direction}; exact_square={square_support:g}; outer_disk={disk_support:.6g}")
    print("polytope=exact zonotope=exact parallelotope=exact ellipsoid=outer box=exact")
    print("Q subset E; E subset [-sqrt(2),sqrt(2)]^2; Q is [-1,1]^2")


if __name__ == "__main__":
    main()
