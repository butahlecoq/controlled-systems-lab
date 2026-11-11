# Native closed-loop feedback evidence

This evidence directory contains several generations of native-policy runs.
The first full LV, fuel, and orbit episodes used the per-edge approximation
filters available at the time. Each approximation call enclosed one retained
parent and one fixed authored action. Those runs exercise path-conditioned
edge filters; they do not establish that the selected box, zonotope,
parallelotope, or ellipsoid enclosed the full multi-action reachable cloud.
The whole-action cloud route is a later implementation and has separate
analytic evidence.

The first full episodes remain unchanged. Root independently checked their
observed states, applied controls, task hashes, original horizons, and common
and tighter physical replays. Seven earlier full-run directories do not
contain raw per-query request/response receipts. Their replay and applied
control evidence remains available, while those missing native query bytes
cannot be reconstructed as original bytes. Later captures must use new
attempt directories.

Some prototype attempt metadata predates the final native graph and shared
capability registration. Its requested-module summaries include structural
`not_used` values for operations that the prototype actually called. Do not
interpret those rows as a canonical resolved-provider graph. The saved traces
and source/binary hashes remain available with their stated provenance.

The analytic whole-action CLI attempts are not source-task episodes. Attempts
`native-multiaction-parent-cloud-cli-20261111-01` and `-02` use the placeholder
task digest `aaaaaaaa…`; the digest is retained as an explicit limitation.
Attempt `-01` conservatively refused path selection because its stage-zero
constraint was the exact observed singleton and outward-rounded box
enclosure could not prove containment. This is not a physical infeasibility
result. Attempt `-02` adds stage-zero margin and selects the authored center
action; both raw requests and responses are preserved. A later clean-source
attempt will bind a retrievable analytic task contract and its computed hash.

Objective values in episode records distinguish the selected policy's
applied-history objective from the independent replay check. A zero
`objective_difference` field denotes agreement between the independent
checker and its full replay, not zero difference between the applied
objective and replayed objective.
