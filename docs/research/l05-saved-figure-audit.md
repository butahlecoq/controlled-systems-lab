# L05 Table 1: saved figure geometry audit

2026-10-19. This source-bound result advances [issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4). It supplements the [Example 1 source dossier](l05-example1-source-dossier.md) and [candidate source check](issue4-volterra-source-check.md); the [L05 publisher record](https://vestnikmi.bsu.ru/?article=1063&issue=34&rus=) identifies the printed article. The original MATLAB figures remain private; the [derived record](evidence/l05-saved-figures.json) contains no plotted coordinates.

## Sources and method

The local Buryatia publication directory contains `4.fig` (SHA-256 `95b9d6a500361a832e6067163e2262fb0e04e2b17f88b83a1af13293c4c728c5`) and `1.fig` (SHA-256 `5a6aeb8a43bf1af1a40c60e34072ce3df3e01cdac1ce4119e76e52cbe83eaf43`). The other archive tree has a byte-identical `4.fig` and an edited `1.fig` (SHA-256 `3c6ab1c8511ca5959d723d600f3d7ab969786f5dd4fc4179480f01ee9ed05d38`) with the same 120 plotted patch vertex arrays. This is archive duplication, not independent numerical reproduction. The nearby `Volterra.m` retains its previously registered SHA-256 `c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1`.

The [checker](tools/check_l05_saved_figures.py) reads the hash-identified MATLAB FIG structs with SciPy 1.16.3. It requires exactly 240 plotted patches with at least two vertices in `4.fig`, arranged as two 60-stage pairs; the first 120 vertex arrays must match `1.fig` exactly. The nonlinear patch vertices match between groups at every stage. The first nonlinear and second linear counts grow as `2, 4, …, 120` over those stages. For each terminal patch it converts every stored binary64 coordinate to its exact dyadic rational value, constructs its planar convex hull with exact orientation tests, and calculates its exact polygon area. An inner polygon is contained in an outer polygon exactly when all its hull vertices satisfy every oriented outer edge; the recorded violation count uses no geometric tolerance. These are operations on the saved vertices, not validated real-arithmetic output of MATLAB or the physical plant.

## Terminal results

| Saved terminal patch in `4.fig` | Hull vertices | Area of saved binary64 hull | L05 Table 1 row matched by count and two-decimal area |
| --- | ---: | ---: | --- |
| First group's plotted nonlinear polygon, index 118 | 120 | 4.681997342186923… | Nonlinear, 120 / 4.68 |
| First group's linear polygon, index 119 | 16 | 4.342896662341959… | Modified, 16 / 4.34 |
| Second group's plotted nonlinear polygon, index 238 | 120 | Same vertices and area as index 118 | Same nonlinear row |
| Second group's linear polygon, index 239 | 120 | 4.619042908487410… | General, 120 / 4.62 |

The numerical match of **all three** Table 1 rows is strong evidence that these saved plots are associated with the reported Example 1 terminal comparison. The script's active plot order and colors distinguish its nonlinear and linear arrays; the assignment of the two linear plots to *modified* and *general* is inferred from their matching Table 1 vertex counts and areas. The saved FIGs alone do not identify which code revision produced the 120-vertex linear plot, its retention rule, or the reported timings.

Exact membership checks on the stored polygon vertices give `linear_16 ⊂ linear_120 ⊂ nonlinear_plot`: zero vertices of the 16-vertex hull lie outside the 120-vertex linear hull, and zero vertices of the latter lie outside the plotted nonlinear hull. Reverse checks find 119 of the 120 linear hull vertices outside the 16-vertex hull and all 120 nonlinear hull vertices outside the 120-vertex linear hull. Thus the three **saved convex polygons** are strictly nested. This establishes inclusion for the plotted hulls only. The nonlinear plot is itself a convex hull of generated points; these tests do not show that it contains every trajectory of the nonlinear recurrence, that either linear construction is an inner approximation of the full nonlinear reachable set, or that the paper's physical and deviation coordinates are reconciled.

## Reproduction and remaining gates

With the private Buryatia `1.fig` and `4.fig` available, run from the repository root:

```powershell
python -B -O docs/research/tools/check_l05_saved_figures.py --figure "$privateL05/4.fig" --companion "$privateL05/1.fig"
python -B -O -m unittest docs.research.tools.test_l05_saved_figures -v
```

The checker rejects wrong source hashes or changed plot structure. The public test checks exact area, hull inclusion, a collinear rejection and the source-hash gate; it cannot replay the private FIG. No MATLAB execution, benchmark, or timing reproduction was performed.

Issue #4 still needs a versioned historical Table 1 driver and inputs, the actual support/retention predicate and its approximation contract, a justified common-coordinate mapping, full feasible-history/constraint coverage, and evaluated physical nonlinear, discretization and arithmetic bounds. The [candidate-only same-control enclosure](issue4-volterra-enclosure.md) remains separate.
