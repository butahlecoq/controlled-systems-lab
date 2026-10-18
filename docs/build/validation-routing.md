# Validation ownership and routing

The executable ownership map is in [route_changes.py](../../scripts/ci/route_changes.py).
Both [native](../../.github/workflows/native.yml) and
[reporting](../../.github/workflows/algorithm-reports.yml) workflows call the
[same router](../../.github/workflows/validation-routing.yml). It reads complete,
NUL-delimited Git diffs without an API file-count limit: three-dot for PRs,
two-dot for main pushes, and both sides of renames. Manual runs, unknown events,
empty diffs, invalid event data and unavailable history request both gates.

| Owner / changed paths | Native matrix | Full reporting validation and staging |
| --- | --- | --- |
| Educational renderer `scripts/reports/visual_examples.py` (embedded CSS, legends, hyperlinks) and its `tests/reporting/test_visual_examples.py` | Skip | Run |
| Saved `reports/algorithm-results/` bundles, except `tooling/` | Skip | Run |
| Other Markdown documentation | Skip | Skip |
| Everything else, including unknown executable files | Run | Run |

The educational files are neither named CTest inputs nor dependencies of native
collectors or smoke checkers. Their imports of existing report validators do not
make those validators educational: a change to an imported validator still
requests both gates. Expand the allowlist only after checking consumers and
adding a behavioral routing case. Shared record/schema validators, collectors,
smoke checkers, executable drivers, C++, CMake, dependency pins/patches and workflow
or router changes retain both gates. A mixed diff uses the union of its needs.
Untracked local files do not define ownership.

Presentation changes still run the entire reporting unittest suite, frozen
saved-record checks, all catalogue/publication staging and the educational
gallery staging. They omit the APP-01 C++ build/smoke step as well as the six
native configurations. Manual runs keep all of them. No binary or numerical
measurement is reused as evidence for a different embedded source commit.
Frozen bundles, content-bound identities and Pages' main-only/stale-head guards
are unchanged.

## Status checks and evidence

Both workflows start on every PR and main push. Their lightweight, unconditional
`Native validation` and `Reporting validation` jobs use `always()` and fail if
routing failed or a requested validation failed, was cancelled or was skipped.
If branch protection is introduced, require these two aggregate checks, rather
than conditional matrix jobs or a workflow with path filters. GitHub documents
that [path-filtered workflows can leave required checks pending](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
and [dependent required checks need explicit failure handling](https://github.com/github/docs/blob/main/content/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks.md).
Commit-message workflow-skip directives can still prevent checks from starting;
do not use them for required validation.

For one presentation event, the avoided work is six native configuration jobs
(three Release toolchains, one sanitizer configuration and two installed-package
presets), plus the APP-01 reporting build/smoke step. Routing and aggregate status
jobs still execute. These are scheduled-work counts, not elapsed-time measurements
or a speedup claim. The full report gate still executes at the reviewed commit.

Run the event/history tests locally with:

```sh
python -m unittest discover -s tests/ci -p 'test_*.py'
```

Tests cover presentation, coupled collectors and smoke checkers, mixed files,
unknown executable paths, main push/manual events, missing history, renames,
PR merge bases, saved bundles and Markdown. Actual workflow runs remain the
evidence for job scheduling and status propagation.
