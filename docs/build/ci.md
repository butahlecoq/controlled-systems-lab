# Native CI event policy

The native Actions workflow retains three full Release toolchains (MSVC, GCC and
Clang), GCC ASan/UBSan and both optional-backend package configurations. These
check different compatibility guarantees. The event policy avoids duplicate
feature-branch builds without deleting those checks.

| Event / changes | Native result |
| --- | --- |
| Push to a feature branch | No automatic native run; opening/updating its PR validates it |
| Open/reopen/update a PR with native, coupled or unknown files | All six native jobs |
| New update to the same PR | Cancel its superseded native run; keep unrelated PRs |
| Push to main with native-relevant changes | All six jobs; preserve each integrated-main run |
| Only Markdown and/or saved algorithm-result bundles | Routing/status jobs; saved report inputs still use complete reporting validation/staging |
| Only educational renderer, stylesheet or gallery tests | Routing/status jobs and complete reporting validation/staging; no native matrix |
| Mixed Markdown/saved records and native-relevant changes | All six jobs |
| Manual `workflow_dispatch` | Full native validation, regardless of paths |
| Push of a tag | No native run; release validation is a separate delivery decision |

Both workflows now start lightweight routing/status jobs for every PR and main
push. The shared [validation ownership map](validation-routing.md) governs job
selection from complete Git diffs. Only the named educational renderer,
stylesheet and gallery test receive a presentation exemption. Other Python
tools, fixture JSON outside saved bundles, dependency pins/patches and workflow
changes retain native validation. Executable measurement drivers under
`reports/algorithm-results/tooling/` retain both gates. Other Markdown-only
documentation edits emit aggregate statuses without native/report validation.

See GitHub's [event and path-filter semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
and [concurrency controls](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
The concurrency key includes the event and PR number, or a unique run ID for
non-PR events. Manual dispatch and main pushes therefore cannot cancel a PR or
one another. The separate Pages deployment queue and current-main check remain
unchanged; native run cancellation does not authorize a stale report deployment.

When introducing required checks or branch protection, require the always-present
`Native validation` and `Reporting validation` aggregate jobs. They check routing
and every requested job's outcome explicitly. Conditional matrix jobs are
intentionally skipped for presentation changes; workflow path filters are absent
so they cannot leave required aggregate checks pending.

Observe hosted trigger and cancellation behavior after publication. Step/job
timestamps establish what work ran and when; they do not by themselves prove a
runtime speedup. Repeated dependency compilation and possible caching are tracked
separately in [#481](https://github.com/butahlecoq/controlled-systems-lab/issues/481).
