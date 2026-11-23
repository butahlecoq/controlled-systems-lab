---
name: delete-comment
description: Audit and remove code comments in reviewable batches.
disable-model-invocation: true
---

# Delete comment

Use `/delete-comment` for an explicitly requested comment audit or deletion batch. Work in independently reviewable batches from a named base commit. Keep the inventory and disposition ledger in local working documents.

1. **Set the boundary.** Inventory comments in the named languages and paths with language-aware extraction. For the Python ratchet, run `python scripts/ci/check_comment_ratchet.py inventory --ref BASE PATH...`. Identify generated, vendored, archived, and immutable evidence separately so the full tree is accounted for. Do not treat markers inside strings as comments.
2. **Classify each prose comment once.** Record path, line or stable location, category, action, and ADR/issue link where applicable.

   | Category | Action |
   | --- | --- |
   | Tautology | Delete comments that repeat behavior already clear from the code. |
   | Stale | Delete comments whose described code or behavior no longer applies. |
   | Excuse | Delete the comment and file a linked issue naming the workaround, its impact, and a verifiable fix criterion. |
   | Decision Record | Record the non-obvious decision and rationale in the relevant numbered ADR, then delete the inline comment. |

3. **Preserve executable syntax.** Keep required notices and directives consumed by compilers, interpreters, formatters, linters, shells, and documentation tools. Record why each preserved comment-shaped line is excluded from prose debt.
4. **Change one batch.** Remove only comments with a supported classification. Keep runtime fixes in a linked issue or separately reviewed change. Run `python scripts/ci/check_comment_ratchet.py check --base BASE` for the current Python ratchet scope (`scripts/ci/`, `scripts/catalogue/`, `tests/ci/`, `tests/cmake/`). The Git base supplies the per-file allowance, so each merged deletion lowers future debt automatically. Stage new files before checking. When adding languages or paths, extend the scope and test the parser/path behavior.
5. **Verify and report.** Inspect the exact diff for behavior changes and accidentally removed directives. Run affected checks. Report base commit, comment-only lines removed, inline comments removed, inventory counts, preserved syntax, and remaining scope. Inline-comment removal does not remove the code line.
6. **Measure this skill.** For a keep/remove decision, compare matched, similarly sized audit batches with and without the skill. Blindly review both for missed comments, wrong dispositions, behavior regressions, rework, and time to an accepted batch. Record model/version and platform-reported input/output tokens, including skill loading. If task-level token telemetry is unavailable, state that token cost is unmeasured; never infer it from file size.
