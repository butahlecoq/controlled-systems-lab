# REVIEW-05 Pages hook handoff

The callable `scripts.reports.stage_review05_family_query.stage(site)` stages the
reviewed family-query and build-phase reports plus a discoverable scalar-state
T=2 example. It returns its content-addressed route. It executes independent
checks against saved records in scratch directories; it never runs an algorithm
binary or rewrites the frozen evidence.

The owner of `augment_pages_bundle.py` can import this module and call `stage`
after the site root and `examples/index.html` exist. Record its returned route in
the augmentation result. The default hook uses the existing archive landing-link
helper and `landing.links_html`; a central gallery helper can instead be passed
as `example_card_writer(site, marker, card_html)`. That callback receives scratch
indexes and must insert the supplied card, including its report anchor. No shared
augmentation, inventory or audit files are changed by this unit.

Before wiring, update the centrally owned visual-route inventory and route audit
for this stager, generated report, SVG/PNG and examples card. Run their focused
checks and a complete managed Pages bundle check. Retain the existing
`check_deploy_head.py` current-main guard before upload/deployment; this local
hook deliberately provides no publishing bypass. Review, CI and main freshness
remain required before publication.

The hook pins the two reviewed frozen manifest digests, verifies all outer files
and inner raw ZIP members, and independently rechecks mathematical outcomes,
direction optima and timing bindings with current repository checkers. It rejects
unsafe paths, symlinks, duplicate ZIP entries and changed evidence. Recomputed
summaries must equal the frozen summaries. New recheck provenance is separate
from the original checks and ZIP. The complete publication ZIP includes both
reports, inputs, source snapshots, raw data, plotting provenance and offline
reproduction commands. The scalar-state label and inconclusive performance
verdict are retained; selected paths do not establish family coverage.

This adds no public library API or required dependency. The managed Linux Python
environment suffices; plotting is already frozen and is not rerun. No native
build, benchmark execution, deployment or release/package version change is
required. A later evidence revision needs an explicitly reviewed manifest-anchor
update; existing staged routes are immutable and cannot be overwritten.
