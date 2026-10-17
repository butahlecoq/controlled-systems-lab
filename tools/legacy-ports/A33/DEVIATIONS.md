# A33 Python 3 transcription deviations

Track label: **A33 Python 3 transcription, synthetic inputs**. Historical B03
figures remain immutable reported context; no timing or B03 reproduction is
claimed. This file records both faithful control flow and explicit limits.

| Source behavior / line | Port behavior | Evidence and consequence |
| --- | --- | --- |
| A33 lines 6–18: `unique(M','rows')'`, midpoint/range, descending `max(abs((p-d)./r))` | NumPy unique rows and stable descending score; lexicographic unique order breaks equal-score ties. | Signed-metric test distinguishes A33 from A29's `abs(max(...))`. MATLAB/NumPy equal-key ordering is not proven identical across releases, so tie-dependent output order is a port deviation. Hull quality is checked independently. |
| A33 lines 25–35: append candidate, call A16, break after ten consecutive `ver=0` outcomes | Same tenth-point trigger. The tenth point is included in the grouped remainder as `M(:,i:end)`. | Threshold test checks stage-2 and stage-3 scan counts. |
| A33 lines 50–72: `Ck=C(:,1:floor(size(C,2)*1))`; C initially empty; `Cj` persists; constrained `Modified_SM` decides additions; restore Ck | All current C is fixed Ck, Cj accumulates nearby columns across candidates, outside points join C, then Ck is restored. | Grouping tests include a later outside point and a nearby append. The commented `SMLP` block is omitted because it is inactive. |
| A33 lines 73–87: final A16 reduction and `itrt=0`, commented pivot accumulation | Final scan uses A16's returned `num` to advance. `itrt` remains zero; actual helper pivots/calls are reported in separate fields. | Tests assert final reduction, source `itrt=0`, and nonzero observed helper pivots. The source counter is not a total-pivot measurement. |
| A16: `eps=1e-9`, fresh identity basis, signed target transform, first maximum/minimum pivots, basis-column bulk deletion and front move | Same tableau operations and fixed tolerance, with NumPy `float64` solve on each pivot. | Direct helper tests cover inside/outside and pivot counts; no modern OPT-05 reducer is called. NumPy LAPACK and MATLAB backslash may differ on ill-conditioned tableaux. |
| Constrained `Modified_SM`: signed candidate transform, fresh identity basis, first-tie tableau pivots, `F` from final target objective | Same active operations; 1-based basis identities are returned by the helper API. | Direct helper tests cover inside/outside and pivots. The A30 file with another digest is not used. |
| A33 divides by every coordinate range; zero range creates NaN scores. It assumes at least two unique columns. | Zero-range inputs return `inconclusive`; fewer than two unique points return a recorded `failed` preprocessing outcome. | Explicit tests. Sorting NaN rows or inventing a normalized zero-width score would silently change this source behavior. |
| A16/Modified_SM have unbounded loops and may encounter singular or nonfinite tableau solves. | A 100,000-pivot capacity or uncertain solve returns `inconclusive`, retaining stage/reason. | Fail-closed execution bound; no deletion or correctness claim follows numerical uncertainty. This is a bounded execution deviation. |

The port was executed on Windows x64 with Python 3.13.5 and NumPy 2.3.2.
Original MATLAB/Octave execution was unavailable on this host. Thus the tests
establish the stated Python transcription behavior and exact quality of the
named binary64 2D fixtures; they do not establish byte-for-byte MATLAB
runtime parity on every input. `oracle.py` uses `Fraction.from_float` for an
independent exact 2D segment/triangle check, including every source point.
`verified` quality is scoped to that input hull, not to source-code fidelity,
minimal vertex count, performance, or B03 published results. Non-2D and
over-capacity oracle inputs remain `inconclusive`.
