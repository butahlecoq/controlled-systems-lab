# Native CI event policy

The native Actions workflow retains three full Release toolchains (MSVC, GCC and
Clang), GCC ASan/UBSan and both optional-backend package configurations. These
check different compatibility guarantees. The event policy avoids duplicate
feature-branch builds without deleting those checks.

| Event / changes | Native result |
| --- | --- |
| Push to a feature branch | No automatic native run; opening/updating its PR validates it |
| Open/reopen/update a PR with C++, CMake, examples or executable scripts | All six native jobs |
| New update to the same PR | Cancel its superseded native run; keep unrelated PRs |
| Push to main with native-relevant changes | All six jobs; preserve each integrated-main run |
| Only Markdown and/or saved algorithm-result bundles | No native run; report inputs still use the report validation/Pages workflow |
| Mixed Markdown/saved records and native-relevant changes | All six jobs |
| Manual `workflow_dispatch` | Full native validation, regardless of paths |
| Push of a tag | No native run; release validation is a separate delivery decision |

The path exclusions are deliberately narrow: `**/*.md` and saved result bundles.
Python tools, fixture JSON outside saved bundles, dependency pins/patches and the
workflow itself retain native validation. Markdown-only changes to report guides
do not invoke the report workflow unless its own path rules include them.

See GitHub's [event and path-filter semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
and [concurrency controls](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
The concurrency key includes the event and PR number, or a unique run ID for
non-PR events. Manual dispatch and main pushes therefore cannot cancel a PR or
one another. The separate Pages deployment queue and current-main check remain
unchanged; native run cancellation does not authorize a stale report deployment.

When introducing required checks or branch protection, account for skipped
workflows: GitHub can leave a path-filtered required check pending. Use an
always-present lightweight gate if that policy requires every PR to emit a
status, rather than forcing documentation through the native matrix.

Observe hosted trigger and cancellation behavior after publication. Step/job
timestamps establish what work ran and when; they do not by themselves prove a
runtime speedup. Repeated dependency compilation and possible caching are tracked
separately in [#481](https://github.com/butahlecoq/controlled-systems-lab/issues/481).
