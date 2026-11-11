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
action; both raw requests and responses are preserved.

Those prototype attempts are followed by source-bound captures in
`native-multiaction-parent-cloud-cli-20261111-03` and the four
`native-multiaction-parent-cloud-{box,zonotope,parallelotope,ellipsoid}-20261111-f84`
directories. These use the canonical task contract in attempt `-03`, SHA-256
`f60b9ef5d38bac3d0d202913b8e6ca5c219597b5cfe3751dcd8e3c71d642cc82`, and
source commit `f84bf6fa`. Each route reports five stage-zero parent clouds,
five authored actions per cloud, and numerical selected-shape membership
witnesses for all 25 child nodes. These remain bounded analytic queries, not
source-task full episodes or global-optimality results.

The visual summary is [analytic-action-clouds.html](figures/analytic-action-clouds.html).
Its panels plot each actual selected set payload, all five recomputed action
children, and the selected retained-graph MPC trajectory and first action.
The reusable renderer is [plot_analytic_action_clouds.py](figures/plot_analytic_action_clouds.py).
The fresh installed-package consumer check for commit `f84bf6fa` is in
`attempts/installed-consumer-f84`; it compiled and ran only the public graph
client against a fresh prefix and passed CTest 1/1.

Objective values in episode records distinguish the selected policy's
applied-history objective from the independent replay check. A zero
`objective_difference` field denotes agreement between the independent
checker and its full replay, not zero difference between the applied
objective and replayed objective.
