# L05 Example 2: conditional affine-set invariants

2026-11-10. This bounded clarification advances [issue #6](https://github.com/butahlecoq/controlled-systems-lab/issues/6) without resolving its restoration criteria. It distinguishes the published modified method's approximation language from its full-vertex promise. It does not identify the historical 153-vertex construction, prove an implementation error, or infer author intent.

## Source identity and scope

The supplied local `papers/papers_for_professor/1063.pdf` has 883407 bytes and SHA-256 `9327fdc6d4a24258d458d8c80bc5c983ef63b2245eeadce99475e8e66c6942bf`. A fresh download on 2026-11-10 from the publisher's [1063 PDF](https://vestnikmi.bsu.ru/content/articles/1063.pdf) has the same size and SHA-256. The [article record](https://vestnikmi.bsu.ru/?article=1063&issue=34&rus=) identifies the 2018 article, pages 52–65, DOI `10.18101/2304-5728-2018-1-52-65`.

This is a separately identified copy of the L05 article, **not byte-identical** to the earlier [inventory L05](inventory.json): 882534 bytes, SHA-256 `dfc76d4d33dad578567f851ae8169a44af290d2e17ea826cec46271dde2d311d`. The earlier PDF was unavailable at its inventoried local path during this check, so no full page/text equivalence between the two copies is asserted. The new copy's algorithm and Example 2 were read directly, including visual inspection of PDF pages 7 and 10. Earlier inventory hashes, audits and historical results remain unchanged. Neither PDF nor its extracted text or page images is redistributed here.

## What the paper specifies

PDF page 6 (printed 57) gives the general affine recursion: take all pairs of state/control vertex images, form the complete hull, convert to halfspaces, intersect the stage state constraint, then convert back to vertices. PDF pages 7–8 (printed 58–59) describe two modification directions: smaller LP tableaux and approximation of intermediate auxiliary sets, citing reference [6]. The farthest-first candidate procedure nevertheless describes its output as all reachable-set vertices and finishes with an equality to the reachable set. Its supporting-hyperplane retention predicate is not accompanied by an operational LP, numerical tolerance, degeneracy rule or completeness proof in this article. These limitations were already recorded in the [primary claim audit](l05-primary-claim-audit.md) and [predicate crosswalk](l05-retention-predicate-crosswalk.md).

PDF page 10 (printed 61), Example 2 and Table 1, places the general `756 / 40808.17` and modified `153 / 34764.47` vertex/volume rows under the associated linear system. It does not declare a different control sample or a different linearization for those two rows. Nor does it supply an outer-enclosure guarantee for the modified set. Retaining feasible points and taking their exact hull would give an inner set; equality needs a separate completeness argument. Floating-point feasibility and hull calculations alone do not certify that inclusion.

Thus the reported rows concern the same stated linear example, but the text does not resolve whether the modified row is an intentionally smaller inner approximation, another implementation convention, or a count with a different meaning. Calling it the exact same full hull is not justified by the table; calling the algorithm incorrect is also premature. The existing [candidate reconstruction](l05-example2-candidate-reconstruction.md) and [approximation hypothesis](l05-example2-approximation-hypothesis.md) remain distinct source-bound results, not a canonical interpretation of 153.

## Two invariants under explicit premises

Assume a fixed initial point, fixed affine maps `x(t+1)=A(t)x(t)+B(t)u(t)+c(t)`, independent centered interval controls, and no asymmetric stage clipping or extra history coupling. The terminal set is a translated zonotope `z + sum_j [-g_j,g_j]`.

1. **Parity:** central reflection `v -> 2z-v` pairs its distinct extreme vertices. For a non-singleton zonotope, its center is not an extreme point, so there are no fixed vertices and the vertex count is even. This does not require generic generator position or full ambient dimension. Consequently, 153 cannot be the complete distinct extreme-vertex count under these premises. An asymmetric state intersection, approximate retained point count, different model, or other unestablished premise can invalidate that inference about the reported row.
2. **Initial-state translation:** holding all maps and admissible controls fixed, changing the initial point changes only `z` by the state-transition product times the initial-state difference. Vertex count and volume stay unchanged. Therefore the printed nonlinear initial state `(1,1,1,1)` versus linear `(1,-1,1,1)` cannot *by itself* explain different counts or volumes for two computations with the same frozen affine maps. Regenerating the reference trajectory changes the maps and is outside this premise. State clipping or an unprovided coordinate transformation also requires separate analysis. An invertible coordinate transformation preserves vertex count, but can scale volume.

The previously documented generic 4D zonotope count is not new evidence here; see the [candidate reconstruction](l05-example2-candidate-reconstruction.md). The horizon convention also needs care: a seven-transition interpretation and an inclusive printed time index must not silently be interchanged.

## Linearization qualification

The displayed first nonlinear equation on PDF page 10 has a state-dependent input coefficient. Its ordinary full state derivative at a reference pair is

`d f1 / d x1 = 1 - (1/2) sin(xref1) uref1`.

The printed matrix has `A11=1`, while the stated reference input is `uref1=1/2`. For example, at the illustrative reference state `xref1=pi/2`, the full derivative would be `3/4`. This is a generic algebraic qualification, **not an evaluation of the article's actual reference trajectory**, and does not establish an actual reference-point mismatch. The paper may intend a partial approximation or another convention; it says the linearization procedure is outside its scope (PDF pages 3–4). A faithful full-Jacobian claim needs that convention resolved, together with physical/deviation coordinates and any affine offset. It does not explain a difference between general and modified algorithms using the same printed maps.

## Exact illustrative check

Run from the repository root:

```sh
python3 docs/research/tools/check_l05_affine_invariants.py
```

The standard-library-only checker uses rational arithmetic and three 2D generators `(1,0)`, `(0,1)`, `(1,1)`. It enumerates their eight sign combinations, computes six distinct hull vertices, checks antipodal pairing, and verifies that translation by `(7,-3)` preserves the hull and area `12`. Removing one genuine vertex produces a strict five-vertex feasible inner hull: an odd approximate count is compatible with losing equality.

It also checks `[-1,1]^2 intersect {x+y<=0}`, an exact three-vertex triangle of area `2`. This asymmetric-clipping counterexample proves why the no-clipping premise cannot be omitted from the parity inference. These are explanatory toy sets, not implementations or reproductions of the paper's retention algorithm. No benchmark, timing comparison, native build, solver or nonlinear integration is involved.

Remaining work includes the actual modified retention/completeness specification, source-bound driver and tolerances, state constraints/horizon convention, and common model/coordinate semantics. Keep #6 open. This research note changes no public API, dependency, installation or publication workflow; no release or package update is needed.
