# L05 Example 2: four-state candidate reconstruction

2026-10-19. This source-bound audit advances [issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4). The [L05 baseline register](baselines.md#b02-nonlinear-reachability-approximation) reports Example 2 at dimension four: general `756 / 40808.17`, modified `153 / 34764.47`, and nonlinear reference `436 / 47795.76` (vertices / volume). The private archive's `Dim4.m` and three saved projection figures supply a strong candidate for **two** of those rows. The [checker](tools/check_l05_dim4_candidate.py) and [derived record](evidence/l05-dim4-candidate.json) retain the hash gates and aggregate results without copying source files or plotted coordinates.

## Candidate inputs and independent construction

The private `Dim4.m` has SHA-256 `f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a`. It sets `n=7` transitions, two independent control coordinates with four corners `(±1,±1)` at each transition, a reference start `(1,1,1,1)`, and **both plotted** linear and nonlinear starts `(1,-1,1,1)`. Thus its eight plotted state sections are compatible with an eight-section reading of the printed Example 2 horizon, but the source/print time-index convention and the different printed nonlinear start are not reconciled. Its `Approx_mod` calls are commented out. The script has no stage state-constraint check in this loop.

The checker independently enumerates all `4^7 = 16384` corner-control histories under the source's seven frozen linear matrices and separately affine nonlinear recurrence. The linear set is a four-dimensional zonotope with `14` generators. A generic-position 4D zonotope with 14 segments has at most `2 Σ_(k=0)^3 C(13,k) = 756` vertices. Here a floating 4D convex hull has 756 vertices, and its volume is `40808.16557488733`, matching the printed general row at two decimals. Independently, the 4D zonotope determinant identity `volume = 16 Σ_|I|=4 |det(G_I)|` over all 1001 generator quadruples gives `40808.16557488736`. The smallest absolute determinant in this floating calculation is about `1.4e-5`. This is a strong numerical correspondence, not validated arithmetic for the source's real trigonometric values or historical MATLAB output.

The convex hull of all 16384 candidate nonlinear corner histories has 436 vertices and 4D volume `47795.758789498876`, matching the printed nonlinear row at two decimals. In this **candidate recurrence**, the one-step map is affine in state for fixed control and affine in control for fixed state. If the four source control columns are interpreted as the corners of the full box `[-1,1]^2`, with no state constraints, induction shows that the convex hull of its complete continuous-control reachable set equals the convex hull of corner-control histories. The script itself branches over the four corners. This characterizes the ideal-arithmetic **convex hull** of candidate reachable states, not the generally nonconvex reachable set itself. The recorded vertices and volume are floating hull calculations; they do not certify the physical nonlinear plant, state constraints omitted from this loop, or rounding/integration error.

## Saved projections and source revision boundary

The three private MATLAB FIG files are hash-gated in the checker. Each has two 3D patches. One patch's vertex set matches the independently generated candidate nonlinear corner-history projection within `7.4e-15` Euclidean nearest-vertex distance; the other patch's vertices all match projected candidate linear corner endpoints to the check's `1e-12` threshold. The second patch is *linear-associated*, but its smaller projected vertex count does not recover the printed 153-vertex modified **4D** polytope or its volume.

| Private FIG | Saved axis labels | Nonlinear projected hull vertices | Linear-associated saved vertices |
| --- | --- | ---: | ---: |
| `2.1.fig` | `x_1, x_2, x_3` | 121 | 64 |
| `2.2.fig` | `x_2, x_3, x_4` | 169 | 63 |
| `2.3.fig` | `x_1, x_2, x_4` | 136 | 66 |

The current `Dim4.m` text requests `(x_1,x_3,x_4)` for its third terminal plot, while the saved `2.3.fig` axis labels and candidate vertex match are for `(x_1,x_2,x_4)`. This is direct evidence of a script/figure projection mismatch; the generating revision or editing step is unidentified. The FIG headers date these saved files to 20 February 2018 and their embedded MATLAB-root paths name R2015b. Those are saved-file metadata, not proof of the numerical run environment; the article reports MATLAB R2014a.

## Reproduction and remaining gates

With the private Buryatia files available, run from the repository root:

```powershell
python -B -O -m docs.research.tools.check_l05_dim4_candidate --source "$privateL05/Dim4.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"
python -B -O -m unittest docs.research.tools.test_l05_dim4_candidate -v
```

No MATLAB run, historical timing, or 153-vertex modified-row reproduction was performed. The match strongly associates candidate parameters with the general and nonlinear Example 2 cells but does not identify a versioned Table 1 generator, the actual retention predicate, a common physical/deviation coordinate map, or evaluated physical nonlinear/discretization/rounding bounds. The [Example 1 saved-figure audit](l05-saved-figure-audit.md) and [linear zonotope reconstruction](l05-linear-zonotope-reconstruction.md) remain separate source-bound results; issue #4 stays open.
