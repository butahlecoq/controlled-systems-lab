# B08 printed terminal-row rounding audit

Date: 2026-10-17. This is a bounded source-reading increment for [issue #6](https://github.com/butahlecoq/controlled-systems-lab/issues/6). It checks the numbers printed in L04 against its stated Euclidean criterion and, separately, the published plan against its printed linear recurrence. It does not revise the historical rows or identify the arrays that generated them.

## Source and test convention

L04 is the privately held article registered in the [inventory](inventory.json): 390,884 bytes, SHA-256 `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f`. The original was hash-checked locally. Physical PDF p. 7 Eq. (15) defines `F(x)=||x-xd||₂`; p. 12 sets `xd=(1200,0,450,0)` and prints the four-step linear model, actions and disturbance intervals; p. 13 prints the nonlinear terminal vector and `14.048` in the text, and both nonlinear and linear rows in Table 2. No original PDF bytes or extracted text are committed.

The [standalone checker](tools/check_b08_reported_rounding.py) treats each printed coordinate and cost as the center of a **nearest-decimal rounding interval**, with half a unit in its last printed place. That convention tests whether ordinary display rounding could explain a discrepancy; the article does not specify its formatter or promise nearest rounding. For a coordinate box centered at `c` with uniform half-width `h`, the exact squared-norm bounds are the sums of `max(0,|cᵢ-targetᵢ|-h)²` and `(|cᵢ-targetᵢ|+h)²`. Squared reported-cost intervals are compared using exact `Fraction` arithmetic, without square-root rounding.

## Exact dispositions

| L04 p. 13 row | Exact squared-norm interval from rounded coordinates | Exact squared reported-cost interval | Intersection? |
|---|---|---|---|
| Nonlinear text `(1200.139,-2.294,450.406,-16.254)`, `14.048` | `[269620017/1000000,269658203/1000000]` | `[31573161/160000,789441409/4000000]` | No |
| Nonlinear Table 2 `(1200.14,-2.29,450.41,-16.25)`, `14.05` | `[538607/2000,2696853/10000]` | `[7890481/40000,7901721/40000]` | No |
| Linear Table 2 `(1201.14,-27.29,452.61,-61.25)`, `67.12` | `[9006991/2000,45053413/10000]` | `[180176929/40000,288369/64]` | Yes |

The nonlinear text row's possible norm is about `16.42011` to `16.42127`; its `14.048` cannot follow from Eq. (15) by coordinate or cost display rounding under this convention. The coarser nonlinear table row also has disjoint intervals. This is a **printed criterion/row inconsistency**, not a nonlinear trajectory replay or a diagnosis of the historical implementation.

For the linear row, the printed coordinates and printed `67.12` can agree by rounding, so the checker does not call their arithmetic contradictory. It separately enumerates the `2⁸=256` disturbance-history corners for L04's printed rational four-step affine model and reported control `(0.6,0.6,-0.3,0)`. Zero corners lie in the table row's coordinate rounding box; the nearest corner's largest coordinate gap is exactly `3/80`, above the box half-width `1/200`. The exact worst-corner squared norm is `112730080707/25000000`, agreeing with the earlier [printed-data minimax audit](b08-displayed-exact-audit.md) and lying outside the reported `67.12` cost interval. The table row could describe an interior or an unreported numerical variant; lack of a matching *corner* does not rule out every reachable interior state.

The [machine-readable result](evidence/b08-reported-rounding.json) is produced without importing the earlier B08 checker. Its SHA-256 is `0f55e48a2e2fd09bf09e2144aacb3a55f8a5957b20f0c440301914bd335075ee`; the checker source SHA-256 is `111e6a2a931f7fb917b8e4d59595489dd3b0abfa11c5a90369da7bc6c10fd01a`. These are fixed to this source-bound check, not a new historical result. Original unrounded matrices, full nonlinear run, source-to-row mapping, MATLAB optimizer behavior and historical timing remain unresolved. This exact arithmetic utility is not a new measured algorithm or a publication of the historical baseline; the existing versioned B08 HTML/raw report remains unchanged.

## Reproduce

From the repository root:

```text
python -B -m unittest docs.research.tools.test_b08_reported_rounding -v
python -B -O docs/research/tools/check_b08_reported_rounding.py --verify-record docs/research/evidence/b08-reported-rounding.json
```

To recheck the private original when locally available, add `--source-pdf <path-to-L04-PDF>` to the second command. The public record and tests do not require that file. Documentation verification checks the links and research-tool syntax. The historical B08 measurement and its published report are separate; no runtime, memory, representation-size, or complete optimal-family claim follows from this note.
