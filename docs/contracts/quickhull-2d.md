# Geometric QuickHull in two dimensions

`<csl/geometry/quickhull_2d.hpp>` and `CSL::quickhull_2d` expose a separate
geometric hull adapter. `quickhull_2d(points)` borrows a cloud of finite
binary64 coordinate pairs and returns original input indices. It performs no
LP query, does not project higher dimensional data, and is separate from the
LP membership reducer and the LP backed recursive hull strategy.

## Archived source audit

The inspected source is A32, `Scientific Research/quickhull.m`, SHA-256
`6787ac407682391bf6837273b4c2e6175846da5ce21798a640c8ceb82c8c760b`
in `docs/research/archive-selected-sources.json`. Lines 1–21 select minimum
and maximum x endpoints, divide remaining points by side and plot the result.
The nested `qh` at lines 22–52 selects a farthest point and recurses over two
subsets. No simplex call appears. The source mixes plotting with computation,
divides by edge x differences in slope expressions, and indexes a farthest
point even when a subset is empty. It does not define duplicate identity or
all-collinear output. The C++ implementation follows only the geometric
endpoint/side/farthest-point structure; it does not copy the plotting or
slope-based subset predicates.

## Interface and ordering

- Empty input returns no vertices. Each nonempty row must have exactly two
  finite coordinates; otherwise `Diagnostics` reports `invalid_input` on
  `points` before any hull work. In particular, a 3D point is rejected.
- The output begins at the lexicographically smallest coordinate pair and
  proceeds counterclockwise, without a repeated closing vertex. A singleton
  has one index; a collinear cloud has only its two endpoint indices.
- Exactly coincident input pairs retain the lowest original index. Interior
  and collinear edge points are omitted. Equal farthest-area candidates are
  resolved by lexicographic coordinate order, then original index. Input
  permutation can change indices and tie choice but not the geometric hull.
- The orientation and area ordering use exact integer arithmetic on the
  supplied finite binary64 values. There is no tolerance threshold that can
  turn a small nonzero orientation into a tie. This is exact for represented
  coordinates, not for an unrounded physical measurement or decimal source.

The divide and conquer search has expected `O(n log n)` and worst case
`O(n^2)` time after sorting; recursion and subset copies can use quadratic
memory in a pathological case. The LP reducer remains the separate reference
for analytic clouds; equality tests compare vertex coordinates after duplicate
identity is removed. Those tests establish the named examples, not a general
formal proof of equivalence to an arbitrary LP backend.
