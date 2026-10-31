# HORIZON-01: scalar integrator horizon ladder

## Problem

The current paired comparison application requires a registered exact-family profile. Its general Strategy A and Strategy B paths admit `nominal_open_loop` only as `candidate_relaxation`, so the T-S01/T-S02 comparison harness cannot be extended by changing the horizon alone. HORIZON-01 exercises those existing candidate paths on a small exact problem without changing their completeness contract. It is a synthetic pilot for #95, not a historical reproduction, general scaling claim, or hard real-time result.

The case is `x[t+1] = x[t] + u[t]`, `x[0] = 0`, `0 <= u[t] <= 1`, minimizing `x[T]`, for `T` in `{2,4,8}`. Since `x[T] = sum(u[t])`, the objective is nonnegative, zero is attained, and a zero objective forces all controls and states to zero. The unique optimal history and value therefore have an exact, horizon-independent oracle.

## Usage (caller's view)

The benchmark README will show one command for each immutable fixture and one suite command:

```sh
python3 benchmarks/reporting/review05/run_horizon_ladder.py \
  --driver build/review05-horizon/csl_review05_horizon_ladder \
  --scenarios benchmarks/reporting/review05/scenarios \
  --output reports/algorithm-results/review05-horizon-ladder-v1

python3 benchmarks/reporting/review05/check_horizon_ladder.py \
  reports/algorithm-results/review05-horizon-ladder-v1

python3 benchmarks/reporting/review05/summarize_horizon_ladder.py \
  reports/algorithm-results/review05-horizon-ladder-v1
```

The C++ driver runs one prepared Strategy A or Strategy B request and emits one structured result. The Python runner owns the schedule, process limits, raw stdout/stderr, repetition order and immutable files. The offline checker reads only the saved fixture, result and H-relation artifacts; it does not load solver libraries.

An invocation records a candidate result, not a complete-family assertion:

```cpp
auto prepared = strategies.prepare(request, candidate_output_requirements);
auto workspace = prepared.create();
const auto result = workspace->run(context); // measured interval
auto relation = export_candidate_h_relation(result); // outside the measured interval
auto check = check_unique_zero_history(fixture, relation, result);
```

## Shape

### Data and ownership

`HorizonFixture` owns a fixture ID, horizon, source scenario bytes/hash, resolved problem identity and the analytic oracle parameters. The fixture list is fixed to horizons 2, 4 and 8; it is not a general public scenario API.

`StrategyAttempt` owns one strategy ID/version, termination and mathematical-outcome labels, the exact monotonic duration of `SynthesisWorkspace::run`, an optional exported H relation, diagnostics, and raw-artifact references. A candidate relation stays labeled as a candidate; the offline checker verifies only this fixture's analytic optimum and required rows.

`HorizonCheck` records fixture identity, candidate output shape, zero-point feasibility, required H rows, and numerical objective/witness observations in one saved status row. Each attempt is `verified`, `incorrect`, `inconclusive`, or `unavailable`; solver completeness metadata never changes these statuses.

### Modules and signatures

- `benchmarks/reporting/review05/horizon_ladder.cpp` loads one pinned scenario, creates the existing provider/strategy registries, admits a candidate-relaxation request, executes one side, and serializes the outcome and H rows.
- `benchmarks/reporting/review05/run_horizon_ladder.py` runs one warmup pair and six measured AB/BA pairs per horizon, rotates the horizon order, enforces process limits, and retains every attempt including timeouts and crashes.
- `benchmarks/reporting/review05/check_horizon_ladder.py` validates immutable fixture identity and applies exact rational checks to saved relation rows without calling either solver.
- `benchmarks/reporting/review05/summarize_horizon_ladder.py` reports attempts, per-horizon medians/ranges and checker states from raw records; it does not drop failed pairs or derive an asymptotic claim.
- `benchmarks/reporting/review05/CMakeLists.txt` builds the isolated benchmark driver against the current source checkout; it does not add a public library API or weaken `application::prepare_comparison`.

The driver exports `CandidateFamily::relation.payload->h_relation_for_recording()` only when present. It records the coordinates and exact binary64 coefficient values. The checker interprets each finite coefficient as its exact dyadic value (using round-trip binary64 decoding), never as a tolerance-based decimal approximation.

The fixture checker uses one structural proof tailored to this case. When a strategy emits an H-relation, it requires the exact initial equality `x0=0`, every transition equality `x[t+1]-x[t]-u[t]=0`, and both control bounds `-u[t]<=0`, `u[t]<=1`, with coefficient comparison performed over exact dyadic rationals. It checks that the all-zero history satisfies every emitted equality and inequality, that the objective upper bound is zero, and that a zero incumbent is retained. The required rows imply `x[T]=sum(u[t])>=0`, so the zero incumbent proves the global minimum is zero. It does not prove the returned candidate relation is the complete feasible or optimal history family. A missing row, unsupported representation, malformed dimensions or non-finite coefficient yields `inconclusive`; a concrete violated constraint yields `incorrect`. A strategy that returns no H-relation is retained as an inconclusive attempt rather than dropped.

This verifier checks the saved relation for this fixed fixture. It is not a general H-polyhedron equivalence engine, and its success does not establish a generic Strategy A/B completeness guarantee.

### Execution and measurement

For each horizon, the runner executes one excluded warmup pair, then six measured pairs with a fresh process/workspace for each strategy invocation. It alternates AB and BA three times per horizon, so first-side order is balanced within each size. It rotates horizon order across repetitions. Each pair uses the same resolved scenario bytes, provider set, resource request, target, representation and numerical policy. One solver thread is requested.

The timed interval begins immediately before `workspace->run(context)` and stops immediately after it returns. Scenario loading, provider setup, strategy preparation, workspace creation, H-relation export, exact checking, serialization and process launch are outside that interval and are recorded separately where observable. Strategy B's internal original-trajectory check remains inside its public run interval; this is part of its implementation and is disclosed rather than hidden.

The runner retains process failures, incomplete results, unsupported relations, checker refusals and timeouts. It records requested and enforced resource limits with mechanism and scope, build and binary identities, host details, fixture digest, exact run order, and stdout/stderr hashes. A missing relation can still leave a candidate-attempt row, but it cannot support a correctness-qualified paired comparison. Six measurements per horizon provide an initial descriptive range; no performance threshold, asymptotic complexity or hard real-time guarantee is inferred.

### Synthesis decision

Candidate 2 is the base because its fixture-specific benchmark boundary, outcome lifecycle and exact checker conditions preserve the existing generic comparison contract. The cross-judge rated it higher for an explicit checker gate, retained failures and keeping changes local to benchmarking. Candidate 1's separate analytic/objective and relation-check statuses are retained. Its cross-horizon balancing idea is implemented as six measured pairs per horizon, giving three AB and three BA orders at each size. The offline checker also validates fixture identity and ignores solver-provided completeness flags.

The checker is intentionally narrower than Candidate 2's proposed general Fourier-Motzkin implication engine: exact required-row checks, the zero witness and the analytic objective bound verify the fixture's optimum without relying on solver completeness claims. They do not prove that an emitted candidate relation is itself the singleton or the complete optimal family. This keeps the checker small and auditable while returning inconclusive for any output that does not expose the required structure. Candidate 1's proposed generic application-level candidate-comparison API was rejected for this first pilot because it expands a public API solely to serve one benchmark and risks confusing candidate evidence with the existing exact comparison contract.

### Tradeoffs accepted

- We accept a fixture-specific checker that verifies the analytic optimum and required candidate rows; it makes no completeness claim about the returned relation.
- We accept that an algebraically equivalent H-relation may be reported inconclusive if it omits required canonical rows; this avoids treating numerical equivalence as exact.
- We accept a separate benchmark driver and Python runner in exchange for leaving production comparison admission unchanged.
- We accept a small one-state horizon ladder in exchange for a clean oracle and a bounded first measurement; it cannot support general scaling or ranking claims.

### Alternatives considered

- **Broaden `application::prepare_comparison` for candidate requests:** rejected because it would mix the existing exact-family contract with a candidate-only pilot. It exposes completeness policy to callers and requires broader API semantics.
- **Add a new registered exact profile for T=2/4/8:** rejected because accepting the profile name would not prove generic completeness. It would require independent verifier registrations and a separate mathematical contract.
- **Use only objective and a verified witness:** rejected as insufficient to assess the returned relation; the saved H artifact is small enough here to check independently.
- **Implement general exact rational polyhedral implication:** deferred because the fixture has a simpler structural proof and this pilot does not need a reusable geometry verifier.

### Open questions and risks

- Does each algorithm expose enough evidence for verified paired timings? The first capture found that Strategy A completes but emits no recordable candidate relation or objective bound on these general horizons. Those rows remain inconclusive; Strategy B's H relations passed the fixture-specific check.
- Do process-level CPU and memory limits work on the measurement host with the requested scope? Record unavailable enforcement honestly.
- Are repeated-process timings stable enough to describe for this small workload? If not, report inconclusive ranges and retain all attempts.

### Current pilot result

The exploratory capture is retained separately in `reports/algorithm-results/review05-horizon01-20261030/`. A clean Release rebuild and 42-process capture from committed source `34bc9fdf437d6eaa63f28c579acc6c82f506ede5` are retained in `reports/algorithm-results/review05-horizon01-34bc9fdf-20261031/`. Across all three horizons, Strategy B's six measured attempts per horizon passed the fixture-specific analytic check. Strategy A's six measured attempts per horizon completed without a recordable H relation or objective bound and are marked inconclusive. No measured pair is fully verified, so the individual run durations are descriptive invocation timings only; they do not support a winner, speedup, or relative-performance claim.

The clean run began with host load averages 10.03, 9.50, and 5.31 on 8 logical CPUs. AB/BA order was balanced, but observed ranges are wide and `perf`/`pidstat` were unavailable, so the runtime limiter is not identified and the measurements are not suitable for performance conclusions.

| Horizon | Reach-back median (range), all completed attempts | Strategy B median (range), all completed attempts | Verified pairs |
|---:|---:|---:|---:|
| 2 | 8.503 ms (5.954–12.685 ms) | 1.115 ms (0.711–1.528 ms) | 0/6 |
| 4 | 14.880 ms (10.682–19.919 ms) | 0.978 ms (0.770–1.817 ms) | 0/6 |
| 8 | 26.599 ms (22.614–32.164 ms) | 0.903 ms (0.778–2.012 ms) | 0/6 |

The timing medians include the inconclusive Strategy A calls. The missing Strategy A evidence is itself a useful limitation to carry into the broader #95 comparison work.
