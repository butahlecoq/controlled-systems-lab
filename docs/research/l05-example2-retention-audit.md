# L05 Example 2: active hull filter versus saved linear projections

2026-10-19. This source-bound follow-up to the [four-state candidate reconstruction](l05-example2-candidate-reconstruction.md) advances [issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4). It checks whether the *active* filter path in the archived `Dim4.m` can account for the printed Example 2 modified row of 153 vertices and volume 34764.47. The answer for this hash-identified source revision is **no**: its active path reproduces the general 756-vertex / 40808.17 row. The modified construction's generating code and retention rule remain unidentified.

## Sources and replay

The private `Dim4.m`, `ConvSM_mod.m`, and `Simplex_Hull_mod.m` have SHA-256 values `f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a`, `e178858e42d5f6174d032d9415b9b7412b2e32ca9aa1b9bfbed7b202db65eaa6`, and `6f87f2c674519352f6801df60fe498a33ac091b79a5a6cbe76f0dcf4a20f6229`. `Dim4.m` actively calls `ConvSM_mod` for both linear and nonlinear candidate columns at each transition. Its two `Approx_mod` calls in that loop are commented out. The [checker](tools/check_l05_dim4_retention.py) hash-gates these files, translates the active pivot/filter operations to NumPy binary64, and preserves the source's parent-major, four-control-corner-minor column order. It is not a MATLAB execution; floating pivot decisions can depend on runtime arithmetic and ordering.

| Transition | Generated linear columns | Retained columns | Complete corner-history hull vertices |
| ---: | ---: | ---: | ---: |
| 1 | 4 | 4 | Lower-dimensional |
| 2 | 16 | 16 | 16 |
| 3 | 64 | 52 | 52 |
| 4 | 208 | 128 | 128 |
| 5 | 512 | 260 | 260 |
| 6 | 1040 | 464 | 464 |
| 7 | 1856 | 756 | 756 |

For each full-dimensional stage, an independent complete corner-history enumeration and SciPy 4D hull have the same vertex set as the translated filter to the check's `1e-9` nearest-vertex threshold. At transition 7, the retained hull volume is `40808.165574887025`, matching the separately reconstructed full zonotope and the printed general value at two decimals. The active source revision therefore does not produce the printed modified row from these inputs. That does not exclude a different revision, an enabled reduction call, or a different Table 1 driver.

## Saved 3D linear patches

The three hash-gated saved FIG files each contain a linear-associated patch whose vertices match candidate linear corner endpoints within `1e-12`. Their sets are **strictly smaller** than the active full linear projections, so these saved patches cannot be identified as the current script's full projected hulls. This strengthens the source/figure revision mismatch already observed for the third projection; it does not identify which filtering or plotting step produced the patches.

| Saved projection | Saved patch vertices / hull volume | Active full projection vertices / hull volume | Largest active full-hull vertex distance to a saved vertex |
| --- | ---: | ---: | ---: |
| `2.1.fig` `(1,2,3)` | 64 / 8647.14 | 184 / 9786.71 | 9.73 |
| `2.2.fig` `(2,3,4)` | 63 / 4714.44 | 182 / 5598.77 | 8.00 |
| `2.3.fig` `(1,2,4)` | 66 / 6065.73 | 182 / 6963.41 | 8.82 |

These 3D volumes are projected-hull measurements, **not** the article's 4D modified volume. Matching a saved projected vertex to some candidate endpoint does not recover its missing fourth coordinate uniquely, the complete retained 4D set, or the 153-vertex row. The source's current third terminal plot requests `(1,3,4)`, while the saved `2.3.fig` axes are `(1,2,4)`.

## Reproduction and remaining gates

Run from the repository root with the private Buryatia files available:

```powershell
python -B -O -m docs.research.tools.check_l05_dim4_retention --source "$privateL05/Dim4.m" --convsm "$privateL05/ConvSM_mod.m" --simplex "$privateL05/Simplex_Hull_mod.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"
python -B -O -m unittest docs.research.tools.test_l05_dim4_retention -v
```

The [derived record](evidence/l05-dim4-retention.json) contains only aggregate results. No historical MATLAB timing or modified 4D polytope was reproduced. The L05 retention-predicate interpretation, versioned Table 1 generator, common physical/deviation coordinate map, and physical nonlinear/discretization/rounding enclosure remain open. Source-bound numerical correspondence does not close issue #4 or certify nonlinear reachability.
