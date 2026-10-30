# Approximation checker events in comparison records

The `csl.approximation-check-event/1` measurement payload records one
approximation attempt and its independent inclusion check. It is carried by
`csl.comparison-record/1`; the event is inert data and does not rerun either
the approximation method or the checker.

The payload binds the result to `problem_id`, `input_set_id`, `output_set_id`,
and `request_id`. The latter three must match the external method result
payload. It records the declared `relation` and `structural_basis` so
the approximation claim and its evidence survive comparison serialization.
These identities do not establish that the input is the complete reachable
set or that the output is an optimizer family.

The `algorithm.elapsed_ns` and `checker.elapsed_ns` fields have separate scopes.
Checker wall-time budgets are stored in `checker.budget`; the selected profile's
default is 5 seconds for `comparison` and 30 seconds for `local_exploration`.
`wall_time_ns` records the effective configurable budget. It is repeated as the
requested wall-time limit in `checker.resources.wall_time` so a mismatch is
rejected during encoding and decoding. When both checker elapsed time and
observed wall time are present, they must agree.

`checker.resources` records wall-time and memory bytes independently. Each
resource has `requested`, `enforced`, `observed`, `mechanism`, `scope`, and
`unavailable_reason` fields. A missing observation needs a reason. An enforced
limit needs a mechanism and scope. The memory request may name the shared
per-attempt comparison allocation; its scope must say
`shared_comparison_attempt`. This is not a checker-local cap. Leave the
checker-local `enforced` and `observed` values null, and give a reason when the
checker cannot be separately attributed. The comparison environment remains
the source for the supervisor and host-specific enforcement details.

Checker `status` is one of `verified`, `incorrect`, or `inconclusive`.
`verified` requires a completed, independent, sound, complete inclusion oracle
with no counterexample. Its `claim` must match the recorded inner or outer
relation, and `structural_basis` must name a current `StructuralBasis` value.
`incorrect` requires a completed independent sound oracle and a concrete point
membership witness in `oracle.counterexample`: `kind` is
`point_membership`, `point` is a nonempty finite coordinate array, and
`contained_in` / `excluded_from` name the corresponding sets. For an `outer`
claim, the point must be declared in the input set and excluded from the output
set; for an `inner` claim, the reverse applies. Both claims require
`oracle.scope` to be `inclusion`. A verified or incorrect checker conclusion is
accepted only when the approximation algorithm itself completed; after failed
or incomplete algorithm output, checker evidence remains diagnostic.
Timeout, refusal, unsupported checking, cancellation, resource exhaustion, or
incomplete evidence remains `inconclusive`. Sampled support and volume results
must therefore stay inconclusive. The algorithm attempt status remains separate
from checker outcome.

The comparison artifact codec validates this event shape and preserves it in
the canonical record. It checks witness shape and set bindings but does not
validate the scientific truth of the membership claims or an oracle's `sound`
declaration; that requires an independent code and evidence review.

## Ownership

The event stays in the attempt's measurement payload because the comparison
record already owns its run identity, digest, and round-trip validation. A
separate checker artifact would require a second reference plus cross-artifact
identity checks without removing the need to validate the same evidence. The
current public comparison API remains unchanged; the codec owns the
schema-specific boundary. A typed producer API can be considered separately if
multiple approximation runners need to construct these events.
