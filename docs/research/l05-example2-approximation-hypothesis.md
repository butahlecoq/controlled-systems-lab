# L05 Example 2: commented stagewise reduction hypothesis

2026-10-19. The [active-filter audit](l05-example2-retention-audit.md) shows that the hash-identified current `Dim4.m` retains the complete four-dimensional general linear hull, ending at 756 vertices and volume 40808.17 at printed precision. This follow-up to [issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4) tests the script's **commented** `Z = Approx_mod(Z,0.001)` line as a concrete explanation for the printed modified row, 153 vertices / 34764.47. A source-ordered NumPy binary64 translation produces a smaller inner candidate, but it **does not reproduce** either printed number or the saved linear 3D patches.

## Source and translated experiment

The private `Approx_mod.m` has SHA-256 `7ca79821f39fde91b0eba8681c1b8775713441a1a1ff04159d963a52416b1c5a`. The [checker](tools/check_l05_dim4_approx.py) also gates the previously registered `Dim4.m`, `ConvSM_mod.m`, `Simplex_Hull_mod.m`, and three saved FIGs. It translates `Approx_mod`'s coordinate normalization, distance ordering, `HypInfo` pivot/classification loop, and deletion table. It applies that reduction **after** the active hull filter at each of the seven transitions, in the position of the commented source line and with its stated `dS=0.001`, default scale `M=10`, and default `eps=1e-9`. No private source is modified or copied into the repository.

| Transition | Generated columns | Columns after full hull filter | Columns after commented reduction |
| ---: | ---: | ---: | ---: |
| 1 | 4 | 4 | 4 |
| 2 | 16 | 16 | 16 |
| 3 | 64 | 52 | 52 |
| 4 | 208 | 128 | 75 |
| 5 | 300 | 178 | 116 |
| 6 | 464 | 246 | 130 |
| 7 | 520 | 256 | 148 |

The terminal 4D hull has **148** vertices and floating volume **34421.17014411157**. Every retained terminal point matches one of the candidate's 16,384 complete corner-history endpoints within `8.4e-15` Euclidean distance. Thus, for this discrete affine candidate without stage state constraints, the translated reduction retains an inner hull of feasible corner endpoints. It is not the article's printed 153 / 34764.47 modified construction. Applying the same reduction only to the active terminal full hull also fails: 142 vertices / 32089.220837141474. These comparisons are source-bound trials, not parameter fitting or historical MATLAB timings.

The saved linear-associated patches in `2.1.fig`, `2.2.fig`, and `2.3.fig` have 64, 63, and 66 vertices. The stagewise candidate's corresponding 3D projected hulls have 59, 61, and 65 vertices, with largest nearest-vertex distances from saved to candidate of about 7.50, 6.47, and 6.96. The candidate-to-saved distances are also nonzero. These saved patch sets therefore do not match the tested commented path at the check's `1e-12` scale. The FIGs still do not expose a complete 4D modified point set or its generating revision.

## Reproduction and remaining gates

With the private Buryatia files available, run from the repository root:

```powershell
python -B -O -m docs.research.tools.check_l05_dim4_approx --source "$privateL05/Dim4.m" --convsm "$privateL05/ConvSM_mod.m" --simplex "$privateL05/Simplex_Hull_mod.m" --approx "$privateL05/Approx_mod.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"
python -B -O -m unittest docs.research.tools.test_l05_dim4_approx -v
```

The [derived record](evidence/l05-dim4-approx.json) contains aggregate counts, volumes, source hashes, and distances, not source vertices. NumPy/BLAS pivot and trigonometric rounding, MATLAB version behavior, and the absence of a versioned generating driver limit the inference. The mismatch does not rule out a different revision or reduction schedule. No nonlinear physical plant, state-constraint coverage, validated rounding, or model/discretization-error enclosure was established. Issue #4 remains open for the historical construction and those scientific gates.
