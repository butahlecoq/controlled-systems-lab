# Controller comparison publication hook

The unique callable `scripts.reports.stage_mpc11_controller_comparison.stage(site)`
stages the reviewed frozen three-variant LV/fuel figures, complete minimal
scenarios/equations, raw pilot archives and source/provenance under an immutable
content-addressed route. It returns that route and inserts archive/example links.
An optional `example_card_writer(site, marker, card_html)` callback lets the shared
catalog owner insert the supplied card using its central helper. Callback indexes
are scratch copies and the returned gallery must retain the discovery link.

The shared augmentation/catalog/inventory/audit owner can import this module and
call `stage` after root and examples indexes exist, then register the returned
route and its SVG/PNG/raw ZIP assets with the existing audit. This unit does not
edit shared wiring. Validate a complete bundle before integration, retain managed
current-main deployment guards, and inspect deployed plots/raw downloads before
claiming publication. The stager itself never deploys.

Run with the existing optional MPC-11 environment and one BLAS/OpenMP thread.
Current saved checkers require NumPy, CasADi and do-mpc to rebuild the 70 saved
transcriptions; they do not solve or integrate. Missing optional dependencies
fail staging. The frozen renderer's source hashes must match the reviewed
checker entry points. Complete archived helpers, the optional exact wheel lock
and notices, and portable offline saved-check commands accompany the output.
No new core dependency, API or library release is needed.

All reviewed figure/reading-layer bytes and pilot ZIPs are pinned and verified
before writing. ZIP entries and checksum inventories are checked before scratch
extraction. Current saved checks must match the frozen figure receipt; plotted
arrays are reconstructed from the checked records. New provenance records all
published hashes separately. Frozen manifests, checks, receipts and archives are
never rewritten. A deliberate evidence revision requires a reviewed anchor
change. Local numerical status, sampled constraints and trajectories do not prove
global/minimax optimality, reachable sets or continuous safety. Pilot timing
comparison remains inconclusive; partial/resource histories remain in raw data.

## Managed publisher environment change required before wiring

At this base, `.github/workflows/pages-augmentation-aggregation.yml` uses Python
3.12 and invokes the combined stager without CasADi/do-mpc. Calling this hook
there unchanged fails; skipping the saved checks is not an alternative.

The integration owner should add a pinned `actions/setup-python` step for exact
3.11.14 with `update-environment: false`, retain its `python-path` output, and
create a dedicated build-directory venv using that executable. Download wheels
with `--only-binary=:all: --require-hashes -r` against the committed
`requirements-linux-cp311.lock`, then install using `--no-index --find-links`
from those same downloaded wheels and run `pip check`. Record interpreter path,
version/hash, wheel hashes and package versions in the CI artifact. Use one
BLAS/OpenMP thread. Invoke this stager as a subprocess with that venv interpreter
and parse its returned route in the shared augmentation owner. Leave the ordinary
3.12 report environment and existing freshness/upload/deploy gates intact. The
same qualified venv must run this unit's end-to-end tests in CI before integration.
Do not wire a fallback to cached statuses or an unpinned dependency install.

## Qualified CI integration

The cumulative publisher now creates the dedicated hash-locked Python 3.11.14
environment and uses it for saved-data staging. A read-only pre-merge workflow,
`controller-report-checks.yml`, exercises the same publication and aggregation
modules in that environment. Its runner fails if any selected check is skipped.
Ordinary reporting CI keeps the lightweight hash/path checks and skips only the
two full staging cases when the optional controller dependencies are absent.
Production staging has no dependency bypass or fallback to saved statuses.

Local validation ran all nine full-profile tests without skips; the ordinary
profile ran its lightweight checks with the two intentional dependency skips.
The source-bound mathematical checks and existing current-main deployment
gates remain unchanged. Hosted exact-head CI is still required before merge.
