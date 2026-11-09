# MPC-11 nominal shrinking-horizon NMPC correctness pilot

The actual do-mpc/CasADi/IPOPT controller at source
`55f651105ecf9d19216ab45814614e59b05be4f2` completed both canonical synthetic
cases: 30 LV updates and 40 fuel updates. Every update used the remaining
horizon to the original fixed terminal time, the original running-cost
denominator, and only physical constraints. The first accepted held control
was executed with CVODES before the next full-state observation. There was no
fallback, parameter change, or affine re-optimization.

The saved checker revision is `b5e503b0ab6f8465da0ad470e3263df7985f68d8`.
It rebuilt all 70 NLPs without optimization. Objective, constraint and local
stationarity reconstruction differences were zero in the captured locked
environment. All sampled execution, optimization-node and applied-control
physical violations were zero. These are numerical sampled diagnostics.

| Case | Completed holds | CVODES executed J_0 |
| --- | ---: | ---: |
| SYN-NL-LV-01 | 30 | 0.09168477962868322 |
| SYN-NL-FUEL-01 | 40 | 0.0038259850540860742 |

Independent CSL adaptive RK4 replays at both contract tolerances also complete.
The summary retains their original objectives, execution differences and
sensitivity. These are different-model/controller results with different
controller restrictions from the affine trust-region plan, not equal-problem
solver parity or a proof that a controller is globally best.

## Verify and reproduce the bundle

The ZIP contains 392 members, including 391 SHA256-bound payloads. Verify the
outer checksum, extract into an empty directory, and verify inner SHA256SUMS.
The `accepted` directory contains both original scenarios, complete applied
controls, CVODES states, every NLP's guess/primal/dual/constraints/local solver
status and log, process receipts, and the two independent replay records.
Source snapshots, a dependency/resource receipt and the functional tests are
included separately. No solver binary or paper is redistributed.

From the repository in the pinned optional environment:

```sh
python benchmarks/reporting/mpc11/check_nmpc_saved.py --bundle <EXTRACTED>/accepted
CSL_MPC11_NMPC_BUNDLE=<EXTRACTED>/accepted \
  CSL_MPC11_NMPC_PORTABLE_BUNDLE=<EXTRACTED>/accepted \
  CSL_MPC11_REPLAY_BRIDGE=<BUILD_DIR>/csl_mpc11_nonlinear_replay \
  python -m unittest tests.reporting.test_mpc11_nmpc
```

See [the controller instructions](../../NMPC.md) for a new bounded capture.
The saved checker recreates each do-mpc NLP and evaluates supplied decisions,
but does not call its optimizer. It validates original-N costs, absolute stage
references, shifted primal-only guesses, zero-dual policy, local stationarity,
physical constraints, first-input application and independent replay identities.
It does not turn numerical trajectories into a certified ODE error bound.

Twenty-four focused qualified tests pass, including the short actual NLP,
expanded stage-objective normalization, shifted warm start, held-input
execution, deliberately failed local solve, partial-history original-N replay,
rebound objective metadata rejection and publication-transformation checks.
The induced `max_iter=0` failure belongs to a separate functional fixture, not
to either canonical study run. Its source and console hash are retained in the
receipt. No canonical failure or resource-limited attempt occurred.

## Distinguish warning redactions from raw numerical evidence

Exactly four text streams replace the local environment installation prefix
with `<OPTIONAL_ENV>`: the two workers' stderr files and their first solver
logs. These lines are Python optional-feature and compatibility warnings.
`accepted/publication-redactions.json` records the exact prefix map, original
SHA256 and published SHA256 for every changed stream. The original captured
file-hash manifest is retained as `original-file-hashes.json`.

The published warning streams are not byte-identical raw originals. The
checker verifies that inverse substitution recovers each original stream hash,
that substitutions occur only on Python warning path lines, and that every
other captured payload remains byte-identical to its original hash. A mutation
of a solver outcome line with a rebound published hash is rejected. Numerical
arrays, solver statuses, original controls, trajectories and timing values are
unchanged. Raw originals remain locally preserved. The only original absolute
prefix retained in published metadata is the explicit redaction map; it is not
a filesystem reference used by replay.

## Resource and delivery limits

The cases ran sequentially with one requested numerical-library thread and
300-second process CPU/wall and 8 GiB address-space limits. Observed setup,
solve, execution, replay and end-to-end process durations remain separate.
Actual library thread count, process CPU consumption and peak RSS were not
sampled and are explicitly unavailable. This is a correctness pilot, not
alternating timing evidence, a speed comparison or a limiter profile.

This optional consumer changes no core API, required dependency, installation
or release. Mesh refinement, timing repetitions, saved-data figures and final
publication remain later steps. These results prove neither nonlinear global
optimality nor minimax correctness, continuous-time safety, robustness or
reachable-set containment. Issue #607 remains open.

## Post-capture coverage and native-outcome checks

Checker revision `7bdccb0d0bfc57146f88f9542e4578e12d18eb4a` supersedes
the captured checker for validation. It requires one ordered, unique solve
record for every executed hold, all original N solves for a complete attempt,
and at most one consistent final unexecuted solve for an incomplete attempt.
Declared inventory must match saved result files. Reports now expose 30 and
40 checked transcriptions, so missing coverage cannot resemble a zero-error
reconstruction. Initial observations, remaining horizons, shifted guesses and
applied first inputs remain bound to the execution grid.

The checker also reconciles worker process/return code, manifest and attempt
outcomes, then checks each native IPOPT EXIT and iteration summary, native
iteration-row coverage and exposed iteration-series lengths against the saved
status, success flag and count. Missing or unsupported native evidence cannot
validate a successful solve. Returned failed solves and declared incomplete
prefixes remain distinct from complete execution. Thirty-one qualified tests
pass, including rebound empty histories, missing/duplicate/reordered inventory,
valid failed-prefix policies, native failure/iteration mutations and manifest
or process outcome disagreement. The original archive and source55 numerical
capture remain unchanged. No optimization or ODE rerun occurred.

Replay evidence validation at `b5909228cd1a74dcdbfe5e8bbf1da3bc111bab2b`
also requires the complete supported native RK4 field set and exact full native
projection equality with the annotated record. Process return code, status,
deadline, stream availability and prefix/summary must agree. Empty or truncated
native objects cannot bypass the check. Failed or timed-out processes without
annotated trajectories remain explicit inconclusive outcomes, while returned
native partial traces keep their prefix status. A completed controller whose
independent replay is unavailable is reported as `inconclusive-replay`.
Thirty-three qualified focused tests pass, including these residual mutations
and valid failed/timeout/prefix boundary cases. The same shared boundary was
fixed on PR900 ancestry at `698e163511deacd0f05486f321dbec0b42dda0c4` and
cherry-picked into this branch. No numerical capture or archive changed.
