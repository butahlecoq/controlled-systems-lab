# L05 Example 1: candidate linear zonotope and saved stage plots

2026-10-19. This bounded reconstruction advances [issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4). It uses the hash-identified private `Volterra.m` candidate and `4.fig` described in the [source check](issue4-volterra-source-check.md) and [saved-figure audit](l05-saved-figure-audit.md). Neither private file nor any saved plot coordinate is copied into the repository. The [derived record](evidence/l05-linear-zonotope.json) and [checker](tools/check_l05_linear_zonotope.py) preserve the comparisons.

## Independent linear construction

The candidate source starts its plotted linear array at `(1,2)`, derives zero reference controls, and uses independent scalar control intervals `[-0.3,0.3]` for 60 stages. Its forward-Euler reference and frozen matrices use the reference at `i+1` (one-based source indexing); the source check records the literal coefficients and the difference from the article's displayed time index. For these *candidate* affine maps, with no state constraints in this loop, the mathematically exact linear reachable set after stage `j` is a planar zonotope:

```text
R_j = c_j + sum_{k=1}^j [-g_{j,k}, g_{j,k}]
c_0 = (1,2),          c_j = A_j c_{j-1}
g_{j,k} = A_j g_{j-1,k}  (k < j)
g_{j,j} = 0.3 B_j
```

This follows by induction from `R_j = A_j R_(j-1) + B_j[-0.3,0.3]`; every generator sign is an independently selectable control endpoint. The checker propagates the center and generators, then constructs each 2D boundary by sorting oriented generator edge directions. It does **not** invoke the archived `ConvSM_mod`, `Simplex_Hull_mod` or `Approx_mod` functions, and it does not replay a historical MATLAB run.

## Saved-plot comparison

The independent floating-point zonotope has `2j` boundary vertices at each stage `j=1,...,60`. Its vertices match the saved second-group linear patch vertex sets at every stage to a maximum symmetric nearest-vertex Euclidean distance of `2.2391302085285913e-14` in plotted coordinates (the check's association threshold is `1e-12`). The terminal polygon has 120 vertices; the earlier [exact saved-vertex audit](l05-saved-figure-audit.md#terminal-results) gives its stored binary64 hull area as `4.619042908487410...`, matching Table 1's general row at two decimals. The close stagewise match strongly supports that the saved 120-vertex linear sequence uses the candidate's frozen maps and control interval. It does not identify the versioned generator, support/retention code or historical timing run. The nearest-vertex distance is a floating-point comparison, not a certified error bound or a polygon Hausdorff distance.

Exact dyadic orientation tests on the **saved** patch vertices give the following stagewise inclusion facts for the full-dimensional plots (stages 2–60):

| Saved hull comparison | Stages with an inner vertex outside the proposed outer hull |
| --- | --- |
| 16-vertex-associated modified plot versus 120-vertex-associated general plot | None |
| General linear plot versus nonlinear plot | 2–54 |
| Modified linear plot versus nonlinear plot | 2–54 |
| Nonlinear plot versus general linear plot | 2–60 |

The first modified and general plots are the same two-point segment; polygon tests start at stage 2. Thus the saved modified hull lies in the saved general hull throughout the plotted sequence, but the linear and nonlinear saved hulls cross in both directions at stages 2–54. The terminal nesting `modified ⊂ general ⊂ nonlinear_plot` observed in the previous audit holds for stages 55–60 only among the full-dimensional plots. No stagewise nonlinear inclusion theorem follows from the terminal image. The nonlinear plot is itself the hull of generated points, so these comparisons do not establish containment of *all* nonlinear trajectories.

## Reproduction and remaining gates

With the private files available, run from the repository root:

```powershell
python -B -O -m docs.research.tools.check_l05_linear_zonotope --source "$privateL05/Volterra.m" --figure "$privateL05/4.fig"
python -B -O -m unittest docs.research.tools.test_l05_linear_zonotope -v
```

The checker rejects changed source hashes or plot structure. Its public test checks the independent zonotope boundary against a literal rectangle and checks the source-hash gate; the private FIG comparison requires the registered local archive. No MATLAB execution, benchmark or timing reproduction was performed. The candidate has no explicit state constraints in this loop, and its plotted `(1,2)` start does not establish the article's common physical/deviation coordinate map. The historical driver and retention predicate, complete nonlinear feasible-history coverage, and evaluated physical nonlinear, discretization and rounding bounds remain open.
