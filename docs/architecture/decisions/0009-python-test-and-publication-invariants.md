# ADR 0009: Preserve Python test and publication invariants

Date: 2026-11-22
Status: Accepted

## Context

Several maintained Python tests encode provenance and admission rules that are
not obvious from their local assertions. Keeping those reasons beside the
implementation duplicates policy in comments and makes the invariant harder to
find across related tests.

## Decision

- MPC-11 catalogue qualification validates task identity and source binding
  before checking optional solver availability. Missing optional backends may
  make a qualified run unavailable, but must not hide malformed or
  source-mismatched evidence.
- The route-change fixture for Pages aggregation preserves the four reporting
  paths from [PR #1111](https://github.com/butahlecoq/controlled-systems-lab/pull/1111)
  at `224cad7804bfdaa162ebfb1f2affae8aafea476f`. A separate synthetic
  `src/existing.cpp` change verifies that the Python quality gate can coexist
  with native routing.
- The dependency archive test exercises both a local path passed through
  FetchContent and a file URI used by the cache download path. These are
  distinct call sites and the fixture verifies their interaction; it does not
  establish a general prohibition on file URIs.
- The Pages publisher keeps `queue: max` and rechecks the source when a job
  obtains its deployment slot. A late older validation must not displace the
  newest pending publication. See [GitHub concurrency behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
- Registered report kinds keep kind-specific schema and manifest validation
  while projecting into a shared catalogue identity contract. Publication
  identity includes source archive bytes: repacking identical admitted entries
  changes the publication identity while retaining the same source report and
  payload identity.
- The archive landing accepts compact list items whose scope is available only
  in the first report link label. It falls back to that label when no explicit
  scope text exists; remove the fallback only after all stage producers supply
  a dedicated scope field. Each report family is registered against its full
  route pattern, so unknown route shapes fail instead of receiving a broad
  prefix classification.

## Verification

The qualification, route, archive, deployment and registered-kind behavior is
covered by `tests/` at the corresponding boundary. Changes to these assertions
must preserve the provenance and identity invariants above. The reporting
publication policy and frozen publisher identities remain independently
checked by saved-output tests.
