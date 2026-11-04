# EXT-07 capability profile and fixture report

This report records the finite hybrid profiles directly exercised by the
current test suite and saved numerical reports. It describes tested fixtures,
not guaranteed capacity. Path growth, exact-integer growth, projection
intermediates, and provider resource limits can reject larger requests.

## Capability-report contract

The unit test `hybrid capability report records request dimensions and
complete path count` constructs a one-step dimension-changing reset fixture.
The report records a horizon of 1, two modes, one edge, maximum state
dimension 2, maximum control dimension 1, and one complete allowed path. A
paired test sets the path cap below the required inventory and verifies that
the report exposes the limit without returning a partial path count. Separate
cases cover profile rejection and cancellation.

These assertions exercise the report's fields and refusal behavior. They do
not establish a general scalability bound.

## Independent small-instance evidence

The model tests compare tiny mode histories with direct graph traversal. The
one-step synthesis oracle independently evaluates raw edge guards, singleton
reset relations, and terminal costs; it checks tied optimal edge identities
and an outgoing edge whose guard excludes the flowed state. The two-stage
oracle enumerates each pair of raw edges and checks all four histories,
including two distinct tied optimal histories. A continuous interval oracle
checks the complete feasible interval on each branch rather than only a
sampled witness.

These fixtures verify selected cases of path enumeration, joint-relation
construction, and optimal-family retention. The synthesis tests also include
`exact H verifier matches tied multi-edge simplex families with different
guards`: it independently enumerates both permitted edge paths and all vertices
of the four-control simplex clipped by the two inclusive guards, constructs
literal H relations for each full optimal face, and checks complete-family
verification for both tied branches. The guards overlap at their shared
boundary. This is exhaustive for that one-stage, two-edge simplex fixture, not
for the full admitted continuous H-relation domain. Broader coverage across
arbitrary H sets, longer horizons, and larger path inventories remains open.

Additional exact linear-H tests now verify literal full optimal faces for a
three-control box, a four-control simplex, and a five-control simplex. Each
case also checks the verifier's completeness result; the four- and five-
control cases reject a feasible candidate that narrows the true face. These are
single-path verifier fixtures and complement, rather than replace, exhaustive
multi-path continuous-family coverage.

| Verifier fixture | State dimension | Control dimension | Horizon | Modes | Edges | Paths | Joint variables | Literal complete family |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Three-control box | 3 | 3 | 1 | 2 | 1 | 1 | 12 | Two free controls in `[0, 1]` after minimizing the first |
| Four-control simplex | 1 | 4 | 1 | 2 | 1 | 1 | 7 | `u_i >= 0`, `sum(u_i) <= 1` |
| Five-control simplex | 1 | 5 | 1 | 2 | 1 | 1 | 8 | `u_i >= 0`, `sum(u_i) <= 1` |
| Guard-clipped four-control simplex | 1 | 4 | 1 | 2 | 2 | 2 | 7 | Overlapping lower/upper guard faces, both globally tied |

## Saved numerical fixtures

| Fixture | State dimension | Control dimension per stage | Horizon | Modes | Edges | Allowed paths | Joint variables per path | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| One-step scalar hybrid profile | 1 | 1 | 1 | 2 | 1 | 1 | 4 | [Saved measured report](../../reports/algorithm-results/ext07-hybrid-51d9ee2e89d240eb/index.html) |
| Two-stage scalar hybrid profile | 1 | 1 | 2 | 3 | 3 | 2 | 7 | [Saved measured report](../../reports/algorithm-results/ext07-hybrid-two-parameter-8ad871b5ea29fc7b/index.html) |

The separate capability-report test records the dimension-changing fixture's
maximum state dimension 2, maximum control dimension 1, horizon 1, two modes,
one edge, and one complete allowed path. The table's joint-variable counts
come from the relation coordinate layouts: four coordinates for one stage and
seven for two stages.

Both reports are listed in the repository publication manifest. Their
main-only Pages deployment and live URL/hash checks are recorded in
[PR #543](https://github.com/butahlecoq/controlled-systems-lab/pull/543).
This report makes no new publication or performance claim.

## Remaining capability limits

The named tests and reports are finite correctness and measurement fixtures.
They do not establish general scaling by state dimension, control dimension,
horizon, mode count, edge count, path count, or provider workload. PR #881 adds
request-wide admission, per-operation composer accounting, and path/branch
operation elapsed wall time to the bounded profile tracked by EXT-07. Each
relation trace records mode or edge, stage, composer version, joint-variable
count, row and matrix-element deltas, elapsed composer wall time, and completion
status. Reachability paths and solver branches record operation elapsed wall
time. Verifier invocations record the full verification phase, including
coordinator checks and path enumeration as well as the adapter call; this is not
provider-only time. Backend thread width is retained when reported.
The separate resource capture records whole-process CPU and memory for two
fixtures. The path, branch, and verifier records also retain process CPU deltas
around those operation intervals, summed over all process threads; concurrent
unrelated work can contribute, so these are not provider-only CPU measurements.
Heap use remains unmeasured, and requested resource limits are not enforced by
these records. Those limits keep the issue open. See the
[implementation capability profile](../architecture/hybrid-capability-profile.md)
for supported dimensions, counts, and remaining capability work.

## Bounded admission and path-count sweep (2026-11-04)

The new [capability scale profile](../../reports/algorithm-results/ext07-capability-scale-925d2910a9a3080d/README.md)
measures the request capability report itself across ten fixtures. It varies
state/control dimension from 1 to 8, horizon from 1 to 8, mode/edge catalogue
size from 2/2 to 8/8, and complete path count from 1 to 256. Each fixture has
seven measured batches of 1,000 calls after an excluded warmup; the collector
checks all 70 records before summarizing them.

The largest tested path inventory (256 paths, horizon 8, two modes, four
parallel edges) has a median capability-report duration of 109,406 ns per call
(range 107,245–110,662 ns). A one-path case with the same state dimension,
horizon, and mode count has median 5,694 ns. These numbers cover model admission
and complete path enumeration only. They do not measure relation construction,
optimization, verification, provider resources, or memory, and establish no
general limit or scalability guarantee. This is an initial capability profile;
larger fixtures and operation-level resource limits remain open under #156.
