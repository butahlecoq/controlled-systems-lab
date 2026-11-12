# B04-c preliminary numerical run

Scenario `B04-c-preliminary-numerical-20261023` uses the saved A39/A01/A40 linear family specified in issue #531. It is separate from `B04-historical`; no historical reproduction is claimed. The three pre-registered bands are copied unchanged in `attempt-002/record.json`.

## Candidate result

SciPy SLSQP returned a feasible terminal candidate with objective `30.899136030011615`. Exact rational replay of the returned binary64 controls confirmed the stage flow box and records the exact squared objective. This candidate's value lies in the pre-registered `|J* - 30.899| <= 0.0005` band. This does **not** confirm the diagnosis: a single SLSQP result and a small gradient residual do not certify the global optimum, and the complete optimal history family was not computed. The optimum-band verdict remains inconclusive.

A separate HiGHS LP found a control sequence whose exact dyadic terminal state lies inside all four published coordinate rounding intervals and satisfies the `[-1,1]` control bounds and stage box exactly. The saved point's exact flow-plane and stock-plane residuals are retained in the record. Reachability and objective results are separate. The independent replay checker verifies every reachability control against the declared bounds.

The solver call took 6,180,953 ns on this one run. This is a single exploratory duration, with no comparator or limiter profile; it is not a performance claim. Host load, software versions, process output, and all returned binary64 control values are saved in `attempt-002/`.

## Attempts and limits

`attempt-001/` is retained as a rejected first attempt. Its LP reachability output landed outside a printed-coordinate interval under exact replay, and its plane-residual labels used an incorrect coefficient; do not use those fields as evidence. The corrected attempt maximized interior slack in the rounding box and uses the saved `(12,23)` plane weights.

The result is candidate-only: no dual/KKT certificate, exact global-optimum proof, complete control-history fiber, or independent profile coverage verifier is present. It does not satisfy issue #531's completion criteria. The published objective `30.899` and historical rows are immutable context. The A40 coefficient scaling interpretation remains an open item.
