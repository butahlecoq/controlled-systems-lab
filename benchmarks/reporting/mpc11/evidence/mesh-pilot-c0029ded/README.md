# MPC-11 two-element mesh correctness pilot

The clean controller source `c0029ded52b7ae3f2965a9f54c3efdbb3e625e2b`
completed all 30 LV and 40 fuel receding-horizon updates with two Radau
subelements per original held-control interval. The original fixed terminal
time, original running-cost denominator, physical constraints, plant,
observation and CVODES execution semantics are unchanged. This is a different
local discretized NLP from the one-element pilot; neither is a global optimum.

The saved checker rebuilt all 70 transcriptions without optimization. Sampled
execution, optimization-node and applied-control physical violations were zero.
Maximum scaled NLP primal violations were 2.12e-11 (LV) and 9.92e-9 (fuel);
local stationarity infinity norms were 4.34e-11 and 1.71e-10. These diagnostics
are numerical checks, not continuous-time enclosures.

| Case | NI1 executed J_0 | NI2 executed J_0 | Maximum held-control difference |
| --- | ---: | ---: | --- |
| LV | 0.09168477962868322 | 0.09168477962863394 | 1.44e-7 |
| Fuel | 0.0038259850540860742 | 0.0038259850561094162 | (5.21e-6, 9.64e-6) |

The summary reports componentwise physical trajectory differences, original
objective differences, both CSL RK4 replay tolerances and local diagnostics.
Fresh execution of the existing native bridge reproduced every saved numerical
and identity field for both cases at both replay tolerances. The elapsed clock
is a fresh measurement and is retained separately. No controller solve or
native build was repeated for these checks. Small observed mesh differences
are sensitivity evidence on these two scenarios, not a mesh convergence bound.

All raw accepted attempts, both initial profile-validation refusals, source
snapshots at each capture commit, bound scenario bytes, native IPOPT streams,
independent replay requests/responses, process outcomes, prior environment/build
receipts and checker fixtures are retained in `capture.zip`. The existing
bridge SHA matches the prior NMPC environment receipt. The do-mpc controller
source hash was checked against that same receipt; all-node state bounds remain
in the captured controller source and checker reconstruction. The first fresh
replay comparison also remains: it differed only in elapsed time, which prompted
an explicit clock policy and regression test rather than changing numerical
acceptance.

Check the outer hashes, extract into a new directory and check the inner
`SHA256SUMS`. With the pinned optional MPC-11 environment, run:

```sh
python benchmarks/reporting/mpc11/check_nmpc_saved.py --bundle <EXTRACT>/accepted
python benchmarks/reporting/mpc11/mesh_summary.py \
  --baseline <EXTRACT_NI1>/accepted --refined <EXTRACT>/accepted \
  --output <NEW_COMPARISON_JSON> --package <EXTRACT>
```

The package option checks source snapshots against their recorded Git commits,
the native capture source hashes and scenario bytes before comparison. A copied
source mutation is rejected even when an archive inventory is renewed.

The baseline is the immutable `nmpc-pilot-55f65110/capture.zip`. For fresh native
replay add `--bridge <EXISTING_BINARY> --fresh-replay <NEW_DIRECTORY>` to the
second command. This checks all response fields except the explicitly recorded
elapsed clock. The comparison checks that scenario differences consist only of
controller identity and collocation element count.

Fifteen focused NMPC tests passed (one unrelated legacy publication mutation
fixture skipped because this raw mesh archive has no publication redactions).
The NI2 fuel initialization test checks every subelement/node at a nonzero
initial time; deleting subelement time scaling fails it. Scenario tests also
pass. Native QP or solver APIs, dependencies, install artifacts and publication
workflows are unchanged; no library release is needed.

Setup, solve, execution and process clocks are retained as descriptive single
pilot observations. These sequential captures on a shared host do not establish
a causal performance ranking. Repeated alternating runs, if performed, need a
separate measurement plan and evidence. This unit does not close issue #607.
