#!/usr/bin/env python3
"""Exact illustrative affine-set checks; not a replay of L05's algorithm."""
from fractions import Fraction
from itertools import product


def hull(points):
    """Distinct 2D extreme vertices, excluding collinear edge points."""
    ordered = sorted(set(points))
    chains = []
    for sequence in (ordered, reversed(ordered)):
        chain = []
        for point in sequence:
            while len(chain) >= 2:
                o, a = chain[-2:]
                cross = ((a[0] - o[0]) * (point[1] - o[1])
                         - (a[1] - o[1]) * (point[0] - o[0]))
                if cross > 0:
                    break
                chain.pop()
            chain.append(point)
        chains.append(chain)
    return chains[0][:-1] + chains[1][:-1]


def area(vertices):
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(vertices, vertices[1:] + vertices[:1]))) / 2


def check():
    q = Fraction
    generators = ((q(1), q(0)), (q(0), q(1)), (q(1), q(1)))
    corners = {tuple(sum(sign * g[j] for sign, g in zip(signs, generators))
                     for j in range(2))
               for signs in product((-1, 1), repeat=3)}
    vertices = hull(corners)
    assert len(vertices) == 6
    assert all((-x, -y) in vertices for x, y in vertices)
    shift = (q(7), q(-3))
    translated = hull({(x + shift[0], y + shift[1]) for x, y in corners})
    assert set(translated) == {(x + shift[0], y + shift[1]) for x, y in vertices}
    assert area(translated) == area(vertices) == 12
    # [-1,1]^2 intersect {x+y <= 0}: an asymmetric stage constraint.
    triangle = hull({(q(-1), q(-1)), (q(-1), q(1)), (q(1), q(-1))})
    assert len(triangle) == 3 and area(triangle) == 2
    assert not all((-x, -y) in triangle for x, y in triangle)
    # Deleting one genuine hexagon vertex is a strict feasible inner hull.
    reduced = hull(vertices[:-1])
    assert len(reduced) == 5 and area(reduced) < area(vertices)
    print('PASS: exact 6-vertex zonotope, translated area 12, clipped triangle, '
          'and strict 5-vertex inner reduction; no L05 implementation replay.')


if __name__ == '__main__':
    check()
