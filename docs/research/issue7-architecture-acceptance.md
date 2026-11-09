# Issue 7 architecture acceptance

This review maps the six requirements of [issue #7](https://github.com/butahlecoq/controlled-systems-lab/issues/7)
to architecture evidence. It does not certify completion of the later
implementation or experiment program.

| Requirement | Evidence and disposition |
| --- | --- |
| Review specifications and distinguish requirements from proposals | The master design defines confirmed requirements, proposals and reserved extensions. The [REVIEW-01 audit](../architecture/review-01-audit.md) checks native module and ownership boundaries at a fixed source revision. |
| Select integrations with explicit capabilities | [ADR 0002](../architecture/decisions/0002-native-integrations.md) selects pinned matrix, LP/QP, bounded geometry, JSON, test and build integrations. Its 2026-11-10 decision separates adapter admission from supervised process limits and records uncapped Qhull output. |
| Require module and reusable backend tests, analytic families and independent witness verification with stable IDs | The [master design](../superpowers/specs/2026-10-11-controlled-systems-master-design.md) defines T-M01–03, T-L01, T-C01, T-S01–03, T-V01–02 and T-X01. The LP/convex backend contract suites, synthesis tests and independent trajectory verifier implement those boundaries. [ADR 0003](../architecture/decisions/0003-numerical-input-and-coverage-policy.md) separates complete-family evidence from witness residuals. |
| Derive scoped tickets, dependencies and ownership before parallel implementation | The [backlog plan](../superpowers/plans/2026-10-11-controlled-systems-backlog.md), backlog.json and ticket files record stable IDs, prerequisites and module ownership. The class-level delivery sequence was merged through PR #451 at `316514e88b451a6ab1952d5de297eb5e77b0c7b5`. Live GitHub dependencies govern subsequent work. |
| Preserve immutable inputs, exclusive workspaces, coarse ports and local specialization | The native contracts and [ownership checks](../testing/native-ownership.md) describe immutable snapshots, owning prepared state and exclusive workspaces. REVIEW-01 checks these against source. Later race tests retain their executed-path limits. |
| Require equal output scope, evidence, residuals, memory and runtime; separate archival B04 restoration | The [comparison program](../architecture/comparison-program.md) requires matched scope, independent checking, explicit failures, separate timing and declared resource accounting. B04 restoration remains issue #10 and is not established by a corrected scenario. |

The architecture decision is complete when these reconciled documents pass
independent specification and standards review. Broader algorithm support,
stronger resource guarantees, final execution review under #95, package delivery
and the remaining comparison experiments retain their own acceptance criteria.
No new binary, public API, dependency or executable behavior changes here;
no release is needed.
