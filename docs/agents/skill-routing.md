# Skill routing for project work

Use one primary workflow per stage. Select additional principles only for a concrete review question. User instructions and the repository specification take priority. This document records the chosen routing; it does not enable a global router or autonomous task execution.

| Work | Primary skill or workflow | Additional check |
|---|---|---|
| Glossary, domain terms and ADRs | Matt `domain-modeling` | pstack type-system discipline when typed semantics change |
| Module interfaces and extension seams | Matt `codebase-design` | pstack type-system and boundary discipline |
| Small tickets and dependencies | Matt `to-tickets`; Superpowers plan format | Explicit acceptance oracles and module ownership |
| Implementation with subagents | Superpowers `subagent-driven-development` | pstack separate-before-serializing for file/workspace ownership |
| Tests | The selected Superpowers TDD workflow | pstack test-behavior-not-implementation checks assertions |
| Code review | Matt `code-review` for independent standards/specification reviews | Selected pstack type, boundary, behavior and shared-state principles |
| Performance claims | pstack `benchmark-checklist` with `principle-explain-the-number` | Existing execution/review workflow owns changes and integration |
| Clear English explanation | Matt `wait-what`, project glossary and user style | No second prose workflow installed |
| Repeated implementation defect | Current implementation ticket | pstack encode-lessons-in-structure, within authorized scope |
| Completion | Superpowers `verification-before-completion` | Check the actual delivered artifact |

## Selective pstack installation

Seven standalone skills were installed from [backnotprop/pstack](https://github.com/backnotprop/pstack/tree/3a604672c46cd8187d2b19980eae0a34f9f91138), pinned to commit `3a604672c46cd8187d2b19980eae0a34f9f91138`:

- `benchmark-checklist` and `principle-explain-the-number` form the required measurement pair.
- `principle-type-system-discipline`, with supporting `principle-boundary-discipline` and `principle-encode-lessons-in-structure`, reviews how types encode domain invariants.
- `principle-test-behavior-not-implementation` reviews meaningful module-level assertions.
- `principle-separate-before-serializing-shared-state` reviews independent worker ownership before adding locks.

The [installation record](pstack-installation.json) contains upstream paths and verified SHA-256 hashes. Upstream skill files were preserved byte for byte; MIT licenses and provenance records accompany the local installation. Existing skills were not overwritten. These skills have `disable-model-invocation: true`; select or read them explicitly. Installed skills are available to the skill catalog on the next turn.

The broad pstack mode, model routing, setup workflow, duplicate TDD skill, TypeScript-only workflows, `technical-writing` and `unslop` were not installed. The latter prose pair overlaps with existing writing instructions and Matt `wait-what`. OpenCode, global AGENTS and global configuration were not changed.

Explain-the-number contains an informational comparison link to `principle-prove-it-works`. That skill was not installed because the existing completion workflow owns verification. Its pinned upstream source remains in the local source cache; the comparison link in the installed copy is not a runtime dependency. The required benchmark pair and type supporting readings are installed.

## Application to this backlog

Use independent worktrees and one mutable workspace per solve/worker. A shared contract/schema has one integrator and a sequential integration point. Separate agent output files rather than letting workers update one mutable report. GitHub publication has one writer.

Before reporting a speed difference, check the timed work and failure count, use tuned release configurations on both sides, alternate at least five repetitions, report median/range and end-to-end relevance, and identify the limiter from profiling outside the reported run. Distinguish historical published timings from measured results. Windows counters/profilers may replace Unix command examples while measuring the same quantities.

Matt `wait-what` asks for a clear explanation with context and simple technical English. Use stable glossary terms and concrete statements.
