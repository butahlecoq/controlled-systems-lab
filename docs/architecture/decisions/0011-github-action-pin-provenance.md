# ADR 0011: GitHub Actions pin provenance

Date: 2026-11-22
Status: Accepted

## Context

Workflows pin reusable actions by full commit SHA. Inline version annotations
make those opaque pins easier to recognize, but they are comment-shaped
metadata repeated across many workflow files and are not consumed by GitHub
Actions. Keeping the version mapping in one place makes it reviewable without
scattering comments through workflow definitions.

## Decision

Keep full commit SHAs as the authoritative action references in workflows.
Record each distinct action/ref/SHA mapping in this decision record. When a
workflow pin changes, update the workflow reference and this table together,
and verify the selected upstream ref resolves to the recorded SHA at update
time. Upstream refs can move; the table records the checked mapping, not a
promise that a mutable ref will remain at that commit.

The mappings below were checked against the upstream refs on 2026-11-22 with
`git ls-remote`.

| Action | Upstream ref | Workflow commit SHA |
| --- | --- | --- |
| `actions/checkout` | `v4` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/configure-pages` | `v6.0.0` | `45bfe0192ca1faeb007ade9deae92b16b8254a0d` |
| `actions/download-artifact` | `v4.3.0` | `d3f86a106a0bac45b974a628896c90dbdf5c8093` |
| `actions/setup-python` | `v5` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/upload-artifact` | `v4` | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `actions/upload-pages-artifact` | `v5.0.0` | `fc324d3547104276b827a68afc52ff2a11cc49c9` |

## Consequences

The workflow files retain immutable commit references without inline version
annotations. Reviewers can check the intended upstream release line and exact
commit in this table. Any action update now has a paired workflow and ADR edit;
do not infer that a recorded upstream ref is permanently immutable.
