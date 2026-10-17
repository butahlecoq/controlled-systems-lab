# Issue tracker

Use GitHub issues and pull requests in [butahlecoq/controlled-systems-lab](https://github.com/butahlecoq/controlled-systems-lab). Always pass the repository explicitly to GitHub CLI commands.

Stable task keys, requirements, acceptance criteria and prerequisites are recorded in the [backlog](../superpowers/plans/backlog.json). Fetch the live issue before starting; closed dependencies and merged code are authoritative. Publication snapshots record the initial state, not current completion.

## Discover and claim work

Discover open, unassigned implementation/test work from GitHub rather than relying on a local backlog snapshot. For the staged comparison program, start with:

```sh
gh issue list -R butahlecoq/controlled-systems-lab --state open --label comparison-program --json number,title,labels,assignees,url
```

Use `--label comparison-program` as the focused filter; omit it to discover all open work. `ready-for-agent` is only a shortlist hint, never proof a ticket is actionable. For each candidate fetch the live issue including comments (`gh issue view N -R butahlecoq/controlled-systems-lab --json number,title,body,state,labels,assignees,comments,url`) and its native blocking dependencies (`gh api repos/butahlecoq/controlled-systems-lab/issues/N/dependencies/blocked_by`). Verify linked PRs and dependent issue state on GitHub. Skip/hand off tickets that are closed, assigned, marked `in-progress`, blocked by any open prerequisite, or have an open PR actively implementing them, even if labels are stale. Never use this snapshot or a readiness label to ignore newer live issues.

Before editing, claim an unblocked issue using the repository's human assignment protocol: assign the authorized developer identity and post a comment naming the agent/session and working branch; apply `in-progress`. Then immediately re-fetch issue, dependencies, assignment, labels, comments and linked PRs. This is coordination, not an atomic lock: if another worker claimed or started first, stop and hand off without overwriting their assignment or claim. Work in an isolated worktree from current `main`; follow the issue's acceptance criteria, run required tests and independent review, and integrate only when those gates pass. On completion or a failed attempt, leave an actionable issue/PR comment with evidence and next steps. Release only your own claim when stopping; preserve other workers' assignments. After a merge, refresh readiness for affected issues from live dependencies; never treat the local backlog as authority.

### Comparison-program discovery index

The [comparison-program spec](../architecture/comparison-program.md) defines intended scope and evidence rules. Current implementation work spawned from its decisions is indexed in [comparison-jobs.json](../superpowers/plans/comparison-jobs.json) by stable task key, GitHub issue number and native blockers. This supplemental index complements rather than rewrites the historical [backlog snapshot](../superpowers/plans/backlog.json). The issue tracker remains canonical; query GitHub each time, since issue state and newly created jobs can change independently of either file. Wayfinder decision/map tickets are planning work, not implementation jobs.

For each task, create an isolated branch and PR. Put `Closes #N` in the PR only when its complete acceptance checklist is satisfied. Post independent standards and specification reviews as PR comments with reviewed base/head commits, actionable findings, severity and verification evidence. Post fix responses and scoped re-review results so the next agent can continue from the PR itself.

Merge only after meaningful tests and independent review pass. The user authorized autonomous PR publication, review comments, integration and evidence-based issue closure. Do not close scientific restoration questions merely because a software workaround exists. Preserve unresolved source assumptions in results and issue discussions.

Use actual newline-containing files with `--body-file` or structured JSON API input for PR bodies and comments. Keep credentials out of tool output. Update readiness labels from live closed prerequisites after each merge; never alter the original acceptance checklist to make work appear complete.
