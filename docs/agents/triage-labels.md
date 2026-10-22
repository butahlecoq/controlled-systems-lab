# Triage Labels

The repository uses five canonical triage roles. These names must match the
GitHub issue labels exactly:

| Role | GitHub label | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer evaluation is still needed. |
| `needs-info` | `needs-info` | Work is waiting for specific information from the reporter or owner. |
| `ready-for-agent` | `ready-for-agent` | Acceptance criteria are clear, required inputs are available, and no open prerequisite or active implementation blocks an agent. |
| `ready-for-human` | `ready-for-human` | The next step needs human judgment, external access, or manual verification. |
| `wontfix` | `wontfix` | The request will not be actioned. |

Every triaged issue should have exactly one category label (`bug` or
`enhancement`) and exactly one state label from the table. Other labels may
describe its work area, phase, or execution status. `in-progress` records active
execution; it does not replace the triage state.

Treat `ready-for-agent` only as a shortlist hint. Before claiming an issue,
fetch its current body, comments, assignee, labels, dependencies, and linked PRs.
Skip it if it is closed, assigned, marked `in-progress`, blocked by an open
prerequisite, or already has an open PR implementing it. A stale readiness label
does not make an issue actionable.
