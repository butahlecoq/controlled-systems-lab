# Issue 4: bounded candidate Volterra model error

2026-10-19. This is a corrected-track calculation for the candidate described
in the [source check](issue4-volterra-source-check.md). The versioned
[saved report](../../reports/algorithm-results/issue4-volterra-7dce05b47c50c27a/index.html)
contains all 60 interval rows, a labelled 2D figure, CSV, raw JSON, exact-byte
manifest and offline ZIP. Its frozen checker commit is
`9286b5ffa9313650ceea0fc033c1410395db22fe`.

## Claim and derivation

For the *candidate's* shared initial state `(1, 2)`, scalar controls
`u_i ∈ [-0.3, 0.3]`, and 60 discrete steps, let `z_i` be its linear recurrence
and `x_i` its quadratically corrected recurrence under the **same** control
history. Both use a matrix `A_i` built from the next zero-control reference
sample. Then `e_i = x_i - z_i` obeys

```text
e_0 = (0, 0)
e_(i+1) = A_i e_i + T0 (-b, d)^T x_(i,1) x_(i,2),
T0 = pi/(18 sqrt(2)), b = 0.003, d = 0.002.
```

The control term cancels exactly. The checker brackets `pi` using the
alternating Machin identity `pi = 16 arctan(1/5) - 4 arctan(1/239)` and brackets
`sqrt(2)` by an integer square root. It computes with integers scaled by
`10^15`, rounding outward on each product and division. At every stage it
propagates boxes for the reference, linear state, nonlinear state and error.
Interval addition and multiplication preserve inclusion; induction therefore
encloses every history admitted by the stated control box. The terminal error
box is

```text
e_60,1 ∈ [-11.384829795848264, 10.972861225716151]
e_60,2 ∈ [ -7.575433251975735,  7.822240492249602].
```

Every admitted control history produces a point in each reachable set, with
the matching point under the same history at `L∞` distance no greater than
`11.384829795848264`. This proves a **two-sided Hausdorff upper bound** for
these control-only candidate sets. It does not prove either set contains the
other. The interval boxes discard dependence between coordinates and stages;
their width is intentionally conservative. The 2D drawing is a view of those
boxes, not a sampled reachable region.

The independent decimal replay in
[`test_issue4_volterra_enclosure.py`](../../tests/reporting/test_issue4_volterra_enclosure.py)
checks four complete control histories against every saved stage box and checks
the analytic one-step error. Those samples catch transcription and rounding
mistakes; the induction with outward intervals supplies the all-history claim.

## Reproduce and limitations

```sh
python scripts/research/issue4_volterra_enclosure.py --output /tmp/issue4-records.json
python scripts/reports/issue4_volterra/render.py --record reports/algorithm-results/issue4-volterra-7dce05b47c50c27a/records.json --out-root reports/algorithm-results --check
python -m unittest discover -s tests/reporting -p test_issue4_volterra_enclosure.py
```

Pass `--source PATH` to the checker to verify the private candidate's SHA-256
when the archive is available. The checked transcription and source hash are
recorded in the report. This result does **not** reconcile L05's printed
physical nonlinear start `(410, 300)` with its linear start `(1, 2)`, prove a
coordinate map, reproduce Table 1, include state constraints or retention
pruning, or evaluate continuous-flow integration error. The candidate's
reference indexing also differs from the printed `A(t)` convention. No
performance measurement or historical timing claim is made. Issue #4 remains
open for those scientific questions and the construction inclusion contracts.
