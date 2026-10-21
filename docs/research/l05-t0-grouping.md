# L05 Example 1: resolve the printed T0 grouping against saved stages

This bounded audit advances [issue #534](https://github.com/butahlecoq/controlled-systems-lab/issues/534). It compares both readings of the printed `T0` expression against the 60 saved general-linear stage polygons, using the hash-identified `Volterra.m` candidate and private `4.fig`. The [checker](tools/check_l05_t0_grouping.py) reuses the saved-patch reader and exact dyadic hull predicates from the existing L05 checks, along with the independent zonotope reconstruction and vertex-distance measure. Private inputs and plot coordinates are not committed. The [machine-readable result](evidence/l05-t0-grouping.json) records both per-stage comparisons.

## The two readings

For `T = 60`, `a = 0.9 = 9/10`, and `c = 0.8 = 4/5`, the candidate grouping is

```text
T0_candidate = 2π / (T√(ac)) = π / (18√2)
```

The alternative grouping is

```text
T0_alternative = (2π/T)√(ac) = π√2 / 50
```

Since `ac = 18/25`, the ratio `T0_candidate / T0_alternative` is exactly `1/(ac) = 25/18`. The candidate code uses the first expression. The checker runs the same affine-control zonotope recurrence with each step size and compares each result with the corresponding saved general-linear polygon.

## Results

The candidate grouping matches the saved vertex sets at all 60 stages. Its maximum symmetric nearest-vertex Euclidean distance is `2.2391302085285913e-14` in plotted coordinates, below the stated `1e-12` tolerance. The alternative matches at none of the stages; its maximum distance is `4.7718446320939645`. For stages 2–60, the checker also applies the existing exact dyadic orientation and convex-hull containment predicates to the saved binary64 vertices and reconstructed polygon vertices. Stage 1 is a segment, so polygon containment is not evaluated there.

This resolves which of the two groupings is consistent with the saved figure's general-linear stage polygons under the registered candidate recurrence. The ratio `25/18` describes the two `T0` formulas; it does not assert that the propagated polygon coordinates are uniformly scaled by that factor.

## Limits and reproduction

The saved figures are required for the 60-stage comparison and remain private. Supply their paths explicitly:

```powershell
python -B -O -m docs.research.tools.check_l05_t0_grouping --source "$privateL05/Volterra.m" --figure "$privateL05/4.fig" --verify-record docs/research/evidence/l05-t0-grouping.json
python -B -O -m unittest docs.research.tools.test_l05_t0_grouping -v
```

The grouping formula and evidence-record metadata have a public test that runs without the private figures. The private-file command recomputes every stage comparison and requires exact record equality.

The result identifies the grouping consistent with these saved figures and the candidate affine-control reconstruction. It does not establish the article's own Table 1 driver, the printed `T0` used for its run, the historical generator, or a nonlinear enclosure. The vertex-distance threshold is a floating-point association check; exact orientation tests apply to the binary64 hull inputs and do not certify a real-arithmetic simulation.
