---
name: delete-comment
description: Use when auditing or removing code comments, reviewing comment debt, or extending the repository comment ratchet.
---

# Delete comment

1. Read the live issue and the code around the comments. Work in independently reviewable batches.
2. Pin the base commit. Inventory Python comments with `python scripts/ci/check_comment_ratchet.py inventory --ref BASE PATH...`. Keep the inventory and a ledger of path, line, category and disposition in the local working-documents directory. Use a language-aware lexer when expanding to another language. Identify archived snapshots and generated evidence separately. Preserve required notices and executable directives.
3. Apply the four dispositions.

   | Category | Action |
   | --- | --- |
   | Tautology | Delete a comment that repeats the code. |
   | Stale | Delete a comment whose statement no longer applies. |
   | Excuse | Delete the comment and file a linked issue identifying the workaround, its impact, and how a fix can be verified. |
   | Decision Record | Record the decision and rationale in the relevant numbered ADR, then delete the inline comment. |

4. Run `python scripts/ci/check_comment_ratchet.py check --base BASE`. This checks tracked Python under `scripts/ci/`. Stage new files first. The Git base carries the per-file allowance, so each merged deletion reduces that allowance. Extend the scope in the checker with tests for the new parser or path behavior.
5. Run the tests for affected callers. Report the exact base, comment-only lines removed, inline comments removed, and remaining audit scope. Inline deletion leaves the underlying code line. Link the ADRs and issues from the batch PR.
