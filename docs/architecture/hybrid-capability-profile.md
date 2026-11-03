# EXT-07 implementation capability profile

This profile records only the hybrid dimensions and path counts supported by
saved numerical reports or explicit independent-oracle tests. The finite
fixtures below do not establish general scalability or a maximum supported
dimension, horizon, or mode count. The accepted model contract is described in
[`hybrid-systems.md`](../contracts/hybrid-systems.md).

## Measured profiles

| Evidence | State dimension | Free control dimensions | Horizon | Modes | Edge catalogue | Admitted paths | Joint variables | Verification scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [One-step scalar report](../../reports/algorithm-results/ext07-hybrid-51d9ee2e89d240eb/records.json) | 1 | 1 | 1 | 2 | 1 | 1 | 4 | Complete interval minimizer family for a bounded scalar control interval and scalar guard; numerical binary64 |
| [Two-stage scalar report](../../reports/algorithm-results/ext07-hybrid-two-parameter-8ad871b5ea29fc7b/records.json) | 1 | 2 scalar parameters | 2 | 3 | 3 | 2 | 7 | Both tied continuous branch families checked by `ExactLinearHHybridFamilyVerifier`; numerical binary64 exactness checks |

Each saved report contains 140 successful public hybrid portfolio calls on its
single fixed analytic fixture. The one-step report used the registered HiGHS
LP provider and `OneStepScalarIntervalHybridFamilyVerifier`; the two-stage
report used the registered HiGHS LP provider and
`ExactLinearHHybridFamilyVerifier`. Both reports retain the analytic family,
raw repetitions, source commit, executable/build evidence, and a standalone
visual example. See the records for exact scenario hashes, environments,
timing scope, and detailed limitations.

These are separate scope demonstrations, not a paired comparison. They use a
single Windows MSVC Release host each; their timings support no speedup,
cross-host, application-scale, or general scalability claim. The verifier
assurance is numerical binary64, not validated arithmetic.

An additive Linux resource capture records whole-invocation limits and cgroup
counters for those two fixture profiles. This is process-tree accounting, not
provider-specific or per-transition resource use:

| Profile | Runtime / memory / swap / CPU cap | Observed peak memory / swap | Cgroup CPU time |
| --- | --- | --- | ---: |
| One-step scalar | 300 s / 1,610,612,736 B / 0 B / 100% of one CPU | 2,359,296 B / 0 B | 62,144,000 ns |
| Two-stage scalar | 300 s / 1,610,612,736 B / 0 B / 100% of one CPU | 2,359,296 B / 0 B | 519,431,000 ns |

The measurements include the shell wrapper and an idle tail while live cgroup
counters were read; build and smoke are excluded. The profiles differ in
horizon, paths, and relation size, so these values do not support a cross-profile
scaling comparison. Full receipts, raw rows, and their accounting scope are in
the [EXT-07 bounded resource observation report](../../reports/algorithm-results/ext07-resource-observation-cfec938d120c95cb/).

Schema `/2` follow-up reports add process CPU deltas around each solver-branch
workspace/execution interval. The one-step profile records 140 observed branch
intervals (median 181,360 ns; range 177,052–527,189 ns). The two-stage profile
records 140 intervals per edge path: `enter-half` median 222,978 ns (range
210,775–329,312 ns), and `enter-full` median 195,036 ns (range
188,503–235,868 ns). Both runs are Release builds with zero failed calls. These
are process CPU values summed over all process threads; unrelated concurrent
work may contribute. They do not attribute CPU to HiGHS, measure heap use, or
support a performance comparison. The [one-step schema `/2` report](../../reports/algorithm-results/ext07-hybrid-e7bb939d854b1907/)
and [two-stage schema `/2` report](../../reports/algorithm-results/ext07-hybrid-two-parameter-bc3c6ca5f7a606ee/)
retain source commits, raw rows, and plots.

Schema `/3` is being added to preserve the full joint-relation operation trace
with composing-thread CPU beside each operation's identity, matrix deltas,
composer wall time, and completion status. It excludes helper-thread CPU and
includes clock-read overhead; process-wide branch CPU remains a distinct scope.
The next two versioned captures will remain descriptive one- and two-stage
profiles, not controlled comparisons.

## Independent-oracle test profiles

The unit suite adds exact H-relation and optimal-family checks beyond the two
measured profiles. These are correctness fixtures, not benchmark or performance
evidence.

| Test fixture | State dimension | Free controls | Horizon | Modes | Edges | Paths | Joint variables |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Independent 3D control-box oracle | 3 | 3 | 1 | 2 | 1 | 1 | 12 |
| Tied multi-edge control-box oracle | 1 | 3 | 1 | 2 | 2 | 2 | 6 |
| Guard-split four-control simplex oracle | 1 | 4 | 1 | 2 | 2 | 2 | 7 |
| Four-control simplex through existential reset | 1 | 4 | 1 | 2 | 1 | 1 | 7 |
| Five-control simplex oracle | 1 | 5 | 1 | 2 | 1 | 1 | 8 |

The fixtures independently enumerate edge identities and compare literal
joint-relation constraints or complete optimal-family faces. Source: the
[`hybrid_path_program_tests.cpp`](../../tests/unit/synthesis/hybrid_path_program_tests.cpp)
cases named `exact linear H verifier matches independent 3D control-box
oracle`, `exact linear H verifier matches an independent tied multi-edge box
oracle`, `exact H verifier matches tied multi-edge simplex families with
different guards`, `exact linear H verifier preserves a four-control simplex
through an existential reset`, and `exact linear H verifier checks a five-control
simplex optimal family`.

The tests extend evidence for bounded exact-H handling of several control
polytope shapes and branch ties. They do not measure runtime or memory, and do
not imply that all systems with these dimensions or counts are admitted. The
full accepted operation, objective, assurance, and resource limits remain
adapter-specific and are checked by preflight.

Each built path and its verification record retain an ordered operation trace.
The trace identifies the mode or transition, stage, composer implementation
and version, joint-variable count, rows added and cumulative rows, and
cumulative coefficient-matrix elements. Each record also gives the matrix
element delta, elapsed wall time for that composer operation, and completion
status, including partial resource counts for a failed operation. The
`exact singleton hybrid verifier independently retains every tied edge path`
test checks this evidence for every path, including guard and reset identity
and the structural counters. These counts describe relation construction;
they do not measure provider CPU or heap use. Elapsed wall time is recorded
separately for staged reachability, solver-branch execution, and the full
verification phase. Backend thread width is retained when a provider reports it.

## Implementation-domain limits

- `JointHReachabilityAdapter` and `JointHDirectTrajectoryAdapter` preserve the
  full branch-labelled joint H relation; they do not project intermediate
  coordinates or merge edge paths.
- `ProjectedStateHybridReachabilityAdapter` currently admits only its narrow
  one-step scalar profile. Its projected terminal-set relation evidence is
  unestablished; the labelled joint relation remains available.
- `ExactSingletonHybridFamilyVerifier` handles bounded enumeration of integral
  singleton trajectories over finite horizons, not continuous families.
- The scalar interval verifiers have the distinct horizon and parameter limits
  stated in [`hybrid-systems.md`](../contracts/hybrid-systems.md).
- `ExactLinearHHybridFamilyVerifier` checks its admitted exact-H, linear-
  objective domain. The test profiles above are sampled fixtures, not an
  exhaustive description of every admitted H relation.
- Path, branch, and verifier reports retain typed process CPU duration or
  explicit unavailability for each operation interval. The clock sums all
  process threads and unrelated concurrent work may contribute, so it does not
  attribute CPU to a provider. Heap use and resource enforcement remain
  unmeasured. A requested `ResourcePolicy` is not proof of enforcement.

PR #881 adds request-wide admission, per-mode/edge composer accounting, and
path/branch operation wall-time plus reported thread observations to the
bounded profile tracked by issue #156. This follow-up records process-wide CPU
intervals; provider-only CPU, heap use, and broader operation profiles remain
incomplete. Future
extensions can add more set representations, enforce provider CPU or memory
limits, and measure larger dimensions or path inventories. The current evidence
makes no general scalability claim. The two saved-report routes
and their manifest-listed files and ZIPs were verified against the live
main-only Pages site on 2026-11-02; details are recorded in
[published algorithm results](published-algorithm-results.md#ext-07-hybrid-profile-report).
