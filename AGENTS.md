# Repository agent practices

When finding or implementing GitHub work, follow the live discovery, claim and dependency-verification protocol in [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md). For comparison-program tickets, also read [the comparison-program contract](docs/architecture/comparison-program.md); it is a planning spec, not authorization to run benchmarks.

For changes to public APIs, dependencies, installation, executable examples or publication workflows, follow [delivery guidance](docs/agents/delivery.md) and record release/package impact in the PR. Numerical algorithms also need a minimal visual example where a supported 2D case exists; preserve the [published-results evidence gates](docs/architecture/published-algorithm-results.md).

Write new plans, designs, task mirrors, research drafts and review notes under `~/.local/state/controlled-systems-lab/working-documents/`, outside the repository. Use live GitHub issues and pull requests for task state. Keep tracked Markdown under `docs/` to the four standing documents linked above and actual numbered ADRs in `docs/architecture/decisions/`. Existing corpus files move only after a verified local backup and consumer review. Preserve functional pages, schemas, catalogues, executable examples, and scientific records as owned assets; any path migration must retain bytes and established publication routes through tested aliases.

## Worktree and disk hygiene

At the end of a session that creates worktrees or local build directories, and before starting another large local build:

1. Check free space on the target drive and list registered worktrees with `git worktree list --porcelain`.
2. For each completed or superseded worktree, resolve its absolute path, verify it lies under the intended worktree root, and inspect `git status --porcelain` including untracked files.
3. Remove clean, unused worktrees with `git worktree remove`. Inspect ignored build output before using `--force`. Preserve dirty worktrees and user-authored artifacts until their changes are accounted for.
4. For disposable build output, verify the resolved path lies under the intended build root and inspect it for authored files. Remove only generated output after validation, then prune stale worktree registrations. Keep the branch when its commits are still needed.
5. When free space is low, pause new local builds and perform this cleanup first. Record any worktree or build directory that could not be removed and why.
