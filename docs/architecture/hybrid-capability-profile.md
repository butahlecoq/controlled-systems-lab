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
single Windows MSVC Release host each; they have no source-mapped limiter or
resource-scale profile, and their timings support no speedup, cross-host,
application-scale, or general scalability claim. The verifier assurance is
numerical binary64, not validated arithmetic.

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
- Provider-consumed CPU, memory, and thread use are not established by the
  saved hybrid reports. A requested `ResourcePolicy` is not proof of provider
  enforcement or consumption.

The implementation issue remains open for broader adapter/resource evidence,
operation admission, continuous-family coverage, and capability validation.
