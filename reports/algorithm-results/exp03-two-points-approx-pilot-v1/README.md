# EXP-03: TwoPoints differential-game approximation pilot

This pilot compares the terminal stage-three projected convex hull of the
finite-game forward reachable states with CSL's registered exact hull and
outer approximation methods. It uses the existing [TwoPoints finite-feedback
report](../env717-two-points-feedback-v1/README.md), whose SVG draws forward
reachable polytopes by control prefix, marks forward nodes that also belong to
the legacy robust-backward and finite-feedback winning sets, and overlays the
open-loop and finite-feedback trajectories in `(x1,x2)` and `(x3,x4)`.
The added figure traces the convex hull of the legacy minimax-threshold target
nodes and the stage-three finite-feedback winning nodes; each outline is a
projected finite-node hull, not a continuous winning region.
The two hulls coincide in both projections, so their outlines overlap; in the
`(x1,x2)` plane each collapses to one point, while in `(x3,x4)` both coincide
with the forward hull.

The added [combined figure](reachability-and-approximations.svg) overlays the
terminal projected hull, the two stage-three winning-node hull outlines, and
four outer representations on that game geometry.
The first panel is position/velocity `(x1,x2)` for point 1; the second is
position/velocity `(x3,x4)` for point 2. It highlights winning nodes within
the forward graph and traces the finite terminal nodes meeting the gap
threshold. It does not draw the continuous 4D target's projection, which is a
coupled squared position-gap condition. Each approximation
relation was checked independently against every projected terminal state
vertex using exact dyadic arithmetic over the stored binary64 values. The
reduced zonotope has an explicit `1 + 2^-32` outward padding on its derived
source generators;
the checker verifies reference inclusion in that padded source and then checks
every source corner against the reduced output.

## Scope and interpretation

- The method-comparison reference is the convex hull of the 345 terminal
  finite-game states after projection to binary64. The discrete nodes are
  preserved separately in `reference.json`. Transitions are exact on a
  scale-2000 integer lattice, but coordinates are converted to binary64 when
  the native 4D V input is built, before projection, hull and approximation.
- In exact rational lattice coordinates, the terminal hull has 4 vertices in
  `(x1,x2)` and 6 in `(x3,x4)`. The binary64 input hull has 4 and 8. The
  distinction is recorded in exact-lattice diagnostics in `check.json`.
- The finite-game model has three stages, controls `{-2.5, 0, 2.5}`, and
  disturbance vertices `{-1, 0, 1}`. The report is not a reproduction of the
  upstream continuous-action 10-second RL task.
- Enclosure claims apply separately to the two 2D projections. They do not
  establish containment of the full 4D sets.
- This pilot approximates the final projected forward hull. It does not
  propagate approximations through the reachability or minimax recursions.
- This pilot records the compatible outer methods and exact hull only. It
  does not produce an inner reachable set, control witnesses for inner-set
  points, or objective bounds; no inner-set claim is inferred from sampled
  states.
- Several outputs do not enclose every exact rational lattice point: QuickHull
  excludes 1 and 2 points in the two projections, the axis box excludes 1 and
  2, and the rotated parallelotope excludes 1 and 0. The ellipsoid and padded
  zonotope enclose all rational lattice points. These diagnostics do not
  change the separately labelled binary64-reference results.
- Directional support gaps are recorded for eight directions as diagnostics,
  not as uniform error bounds. Area ratios describe geometric looseness only.
- Ellipse and rotated-parallelotope outlines can extend outside the inherited
  game-plot limits; the overlay clips those paths to the panel. The area ratios
  use the full computed outputs, not the clipped drawing.
- Timing is one warmup plus seven alternating calls per method and projection.
  All 80 returned warmup and timed sets are retained and pass the independent
  inclusion checker. These short, single-call timings are descriptive
  observations with no speedup or performance ranking claim.

## Results

The exact QuickHull of the stored binary64 projected input has four vertices
in `(x1,x2)` and eight in `(x3,x4)`. All four outer methods contain every
binary64 reference vertex in both planes. The reduced zonotope area ratios
were `1.00000000047` in both
projections. This table gives the declared direction, requested budget, output
size, and area ratio:

| Method | Direction | Budget | Output size | Area ratio `(x1,x2)` / `(x3,x4)` |
| --- | --- | ---: | --- | ---: |
| Exact QuickHull | Equivalent | n/a | 4 / 8 V vertices | 1 / 1 |
| Axis box | Outer | 4 H rows | 4 / 4 H rows | 1.45 / 3.2625 |
| Rotated parallelotope | Outer | 4 H rows | 4 / 4 H rows | 3.7411 / 12.0378 |
| Directional ellipsoid | Outer | 1 ellipsoid | 1 / 1 ellipsoid | 5.8766 / 18.9089 |
| Zonotope axis cover | Outer | 4 generators | 4 / 4 generators | 1.00000000047 / 1.00000000047 |

The zonotope producer takes six derived phase-plane generators and retains
four after its axis-cover reduction. Three source generators are zero and one
output generator is zero, so all three active generators are retained; the
near-unit area ratio is not evidence of lossy active-generator reduction. Its
source is padded outward by `1 + 2^-32` to enclose the independently serialized
binary64 reference.

Seven-call median durations in nanoseconds, with observed min/max in
parentheses:

| Method | `(x1,x2)` | `(x3,x4)` |
| --- | ---: | ---: |
| Exact QuickHull | 74,800 (74,311–201,215) | 140,452 (139,893–159,379) |
| Axis box | 259,113 (254,085–742,000) | 533,313 (519,274–572,284) |
| Rotated parallelotope | 482,328 (476,811–1,530,585) | 510,474 (496,785–620,056) |
| Directional ellipsoid | 235,506 (225,659–419,051) | 230,618 (229,710–246,193) |
| Zonotope axis cover | 13,410 (12,292–18,997) | 12,851 (12,083–16,134) |

These are short single-call timings on one host, so they remain descriptive
observations rather than speedup or performance-ranking evidence. The timed
scope is the public hull/approximation operation; input construction and JSON
serialization are excluded.

## Reproduce and inspect

From the repository root, build and run the optional target:

```sh
cmake -S . -B build/exp03 -DCMAKE_BUILD_TYPE=Release \
  -DCSL_BUILD_EXP03_TWO_POINTS_REPORT=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF
cmake --build build/exp03 --target csl_exp03_two_points_approximation
ctest --test-dir build/exp03 -R exp03_two_points_approximation_smoke --output-on-failure
python3 scripts/reports/exp03/build_two_points_reference.py \
  --figure-data reports/algorithm-results/env717-two-points-feedback-v1/figure-data.json \
  --result reports/algorithm-results/env717-two-points-feedback-v1/result.json \
  --output build/exp03/reference.json
build/exp03/csl_exp03_two_points_approximation smoke build/exp03/reference.json
build/exp03/csl_exp03_two_points_approximation measure build/exp03/reference.json \
  > build/exp03/run.json
python3 scripts/reports/exp03/check_two_points_approximation.py \
  --reference build/exp03/reference.json --run build/exp03/run.json \
  --output build/exp03/check.json
python3 scripts/reports/exp03/render_two_points_approximation.py \
  --source-svg reports/algorithm-results/env717-two-points-feedback-v1/projections.svg \
  --source-figure-data reports/algorithm-results/env717-two-points-feedback-v1/figure-data.json \
  --run build/exp03/run.json --reference build/exp03/reference.json \
  --output-svg build/exp03/reachability-and-approximations.svg
```

The reference builder independently replays the finite integer transition
graph from the linked source figure data. The focused CTest smoke also runs the
independent inclusion oracle. The renderer regenerates this bundle's figure
from the run record and the linked source report's SVG.

Timing scopes are not directly comparable: QuickHull times the geometry call,
while approximation adapters time `run_registered` including policy
admission; the zonotope route starts from a separately constructed padded
zonotope rather than the common projected V input. Projection timing is
recorded separately. No speed ranking is claimed.

The original report's pinned upstream source, commit, finite-game assumptions,
and limits are documented in its README and `result.json`. Raw approximation
outputs and complete inclusion diagnostics are in [run.json](run.json) and
[check.json](check.json). The reference reconstruction and exact projected
zonotope derivation are in [reference.json](reference.json). Build, input
hashes, measurement conditions and checker details are in
[provenance.json](provenance.json); bundle hashes are listed in
[SHA256SUMS](SHA256SUMS).

This run used the GCC 16.2.1 Release configuration on Linux with eight logical
CPUs; the optional HiGHS and Qhull backends were disabled. It was built from the
`57aeb555434f679156b3cb58fb558d46454bddc8` base, with the EXP-03 report driver
and target added in this branch.
