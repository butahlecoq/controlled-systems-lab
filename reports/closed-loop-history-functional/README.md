# Continuous affine-history functional records

These records cover three observed-state controller episodes. Each query uses the original continuous action bounds, source cost, and full remaining horizon. The controller optimizes the recovered affine-history relation and applies its first control to the nonlinear plant. No representation provider is used.

| Task | Solver | Holds | Applied source objective | Corrected plots | Raw evidence |
| --- | --- | ---: | ---: | --- | --- |
| Lotka-Volterra | HiGHS QP | 30 of 30 | 0.09206356098706904 | [Trajectory](lv-highs-f4/trajectory.png), [controls](lv-highs-f4/controls.png), [phase](lv-highs-f4/phase.png) | [Receipt](lv-highs-f4/receipt.json), [ZIP](lv-highs-f4/raw.zip) |
| Earth orbit | CasADi/IPOPT | 20 of 20 | 65.22966483569324 | [Trajectory](orbit-ipopt-f4/trajectory.png), [controls](orbit-ipopt-f4/controls.png), [phase](orbit-ipopt-f4/phase.png) | [Receipt](orbit-ipopt-f4/receipt.json), [ZIP](orbit-ipopt-f4/raw.zip) |
| Fuel | CasADi/IPOPT | 40 of 40 | 0.003834213429545932 | [Trajectory](fuel-ipopt-3c/trajectory.png), [controls](fuel-ipopt-3c/controls.png), [phase](fuel-ipopt-3c/phase.png) | [Receipt](fuel-ipopt-3c/receipt.json), [ZIP](fuel-ipopt-3c/raw.zip) |

These are individual numerical functional records. IPOPT provides local numerical results. The records do not establish global optimality, continuous-time safety, performance rankings, or coverage of the five representation tracks.

The original runner labeled the raw trajectory images and generic coverage text as NMPC. Those labels do not describe these affine-history controllers. The ZIP files preserve the original images and metadata. The linked plots were rendered again from the saved state and control records, without rerunning a controller. Each [render receipt](lv-highs-f4/render-receipt.json) records the renderer commit, source hashes, input hashes, actual provider, and plot hashes. The other two bundles contain their own render receipts.

Each bundle contains the original attempt files, a fixed member inventory with byte counts, SHA-256 digests and CRCs, the independent audit source, the build receipt, and the installed SDK file manifest. The native policy preparation receipt recorded its binary source as unknown. The separate build receipt records the clean source revision, the incremental build, the exact executable hash, and the source capsule hash. It does not claim an independently reproduced binary.

To check a bundle, run `sha256sum -c SHA256SUMS` inside its directory, then run `python -m zipfile -t raw.zip`. The [bundle producer](../../scripts/reports/package_history_functional.py) verifies every member against the source before it publishes a bundle. The [renderer](../../scripts/reports/render_history_functional.py) uses saved records and records its own source revision.

## Incomplete HiGHS fuel attempt

The separate HiGHS fuel attempt timed out at its predeclared 1,800-second worker budget after two of 40 holds. The third query used the original remaining horizon of 38 intervals. The worker recorded the sent request but received no solver result before termination. The timeout does not establish infeasibility or incompatibility.

The [timeout receipt](fuel-highs-f4-timeout/receipt.json) and [raw ZIP](fuel-highs-f4-timeout/raw.zip) preserve the partial trajectory, request, supervisor outcome, source and binary hashes, and independent audit of the two completed holds. No full-episode objective, replay, or plot is claimed for this attempt.
