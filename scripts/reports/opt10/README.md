# OPT-10 saved smooth-convex example

The saved report records one two-dimensional box-constrained quadratic from
the public feasible-directions adapter. The analytic constrained minimizer is
`(1, -1)` with objective `1`. Each measured call checks that literal point,
objective, projected residual, and successful status. The SVG is a diagram of
the feasible box and analytic solution; its dashed segment is illustrative,
not an iteration trace.

The frozen source commit is `9becda80d9a0eb7383fa2215f6b5c1932d3502a0`.
Use a clean detached checkout at that commit and a fresh capture directory:

```powershell
python -B scripts/reports/opt10/capture.py --source D:\path\to\frozen-checkout --capture D:\path\to\fresh-capture --commit 9becda80d9a0eb7383fa2215f6b5c1932d3502a0 --cmake C:\path\to\cmake.exe
python -B scripts/reports/opt10/collect.py --capture D:\path\to\fresh-capture --source D:\path\to\frozen-checkout --out reports/algorithm-results
python -B scripts/reports/opt10/render_saved.py --bundle reports/algorithm-results/opt10-smooth-REPORT_ID
python -B scripts/reports/opt10/render_saved.py --bundle reports/algorithm-results/opt10-smooth-REPORT_ID --check
python -B scripts/reports/stage_opt10.py --source reports/algorithm-results/opt10-smooth-REPORT_ID
```

The final staging command prints the catalogue JSON; redirect it to
`reports/algorithm-results/opt10-publications.json`. The collector validates
the clean source receipts, frozen driver, executable hash, Release CMake
configuration, raw CSV rows, and analytic literals before producing the record.
The renderer reproduces the report, figure, summary, manifest, and offline ZIP
from saved bytes. The Pages stager accepts only the catalogued byte inventory.

One warmup batch of 100 calls is excluded. Seven measured batches of 100 calls
each include feasible-set and objective construction, production HiGHS LP
registration and workspace construction, the public minimize call, and literal
result checks. CSV writing and report rendering are outside the timed region.
The durations describe one adapter on one host and fixed case. There is no
comparator, speedup, hardware-limiter attribution, global-optimality
certificate, or nonconvex support claim. Native thread observations and
submodule counters are unavailable. Numerical stationarity depends on the
caller's declared convexity and gradient contract.
