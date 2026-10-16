# Repository agent practices

## Worktree and disk hygiene

At the end of a session that creates worktrees or local build directories, and before starting another large local build:

1. Check free space on the target drive and list registered worktrees with `git worktree list --porcelain`.
2. For each completed or superseded worktree, resolve its absolute path, verify it lies under the intended worktree root, and inspect `git status --porcelain` including untracked files.
3. Remove clean, unused worktrees with `git worktree remove`. Inspect ignored build output before using `--force`. Preserve dirty worktrees and user-authored artifacts until their changes are accounted for.
4. Remove disposable build output after validation and prune stale worktree registrations. Keep the branch when its commits are still needed.
5. When free space is low, pause new local builds and perform this cleanup first. Record any worktree that could not be removed and why.