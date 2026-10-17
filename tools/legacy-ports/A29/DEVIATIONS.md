# A29/A30 Python 3 transcription deviations

Track label: **A29/A30 Python 3 transcription, synthetic inputs**. Reported
B03 figures remain historical context. This ticket runs no performance
benchmark and makes no B03 reproduction claim.

| Original behavior / line | Port behavior | Evidence and consequence |
| --- | --- | --- |
| A29 lines 7–19: sorted unique input columns; descending `abs(max((p-d)./r))` | NumPy unique rows, then stable descending score; lexicographic unique order breaks score ties. | Test distinguishes A29 from A33's `max(abs(...))`. MATLAB/NumPy tie ordering across releases is unproven, so output order is a disclosed runtime deviation. |
| A29 lines 23–36: `Modified_SM(C,p)`, append only `F>0`, add returned `tmp` to `itrt` | Identical active loop and cumulative pivot count. | Tests assert candidate scan count and `itrt=stage2_pivots+final_pivots`. `P` and `K` assignments are unused in active flow. |
| A29 lines 44–64 proposed grouping and `SMLP` | Entirely omitted because it is commented out in the original. | This port is not the grouped A33 variant; `grouping_executed=false` in every record. |
| A29 lines 65–76: test each C column against `TMP=C` minus that column; apply Boolean `ver` only after all tests | Each final membership query uses the same unchanged C, then Boolean results select output. | Test checks every final helper's support count stays `|C|-1`. Final reduction is not a sequential in-place deletion. |
| A30: fixed `eps=1e-9`, signed candidate transform, fresh identity basis, first maximum/minimum tableau pivot, `F` and `Basis`/`itrt` return | Same active equations and first-tie indices with NumPy binary64 linear solve. | Direct helper tests cover inside/outside, basis length and pivot counts. The distinct constrained sibling helper and modern OPT-05 are not used. MATLAB backslash and NumPy LAPACK can diverge on ill-conditioned tableaux. |
| A30's `degeneracy` local function has one call in a commented block | Uncalled local function omitted. | The branch cannot affect active A30 return values. |
| A29 divides by every bounding-box width and selects `M(:,1:2)` | Zero-width axis returns recorded `inconclusive`; fewer than two unique points returns recorded `failed`. | Explicit tests. Inventing a zero-width score or silently repairing short input would alter source behavior. |
| A30 loop/solve has no finite resource bound and can encounter singular/nonfinite tableaux | 100,000-pivot capacity and uncertain solves return `inconclusive`, retaining stage/reason. | Bounded, fail-closed execution deviation; no output is promoted after numerical uncertainty. |

Validated on Windows x64 with Python 3.13.5 and NumPy 2.3.2. Native
MATLAB/Octave was unavailable. The tests establish Python transcription
behavior and exact quality of named binary64 2D fixtures, not universal
MATLAB runtime parity. The independent `oracle.py` enumerates exact
`Fraction.from_float` segments and triangles and checks every source point.
Its `verified` status covers only the input/output convex hull for at most 64
finite 2D points; it does not certify source fidelity, minimality, runtime,
or B03 numbers. Unsupported dimensions and over-capacity evidence remain
`inconclusive`; omitted extreme points are `incorrect` with source index.
