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
construction, and optimal-family retention. They do not exhaust the admitted
continuous H-relation domain. The independent exhaustive continuous-family
oracle remains an open EXT-07 acceptance item.

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
horizon, mode count, edge count, path count, or provider workload. EXT-07 still
requires broader operation-plan admission, provider resource and per-mode /
per-transition provenance accounting, and resource-scale evidence. The issue
remains open until those gates and the full acceptance checklist are met.
