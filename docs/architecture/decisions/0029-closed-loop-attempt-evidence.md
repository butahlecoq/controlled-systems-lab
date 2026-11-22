# ADR 0029: Preserve closed-loop attempt evidence semantics

Date: 2026-11-23
Status: Accepted

## Context

The closed-loop runner persists stage records and an attempt summary in
separate writes. A worker can stop after a stage record is durable but before
the summary checkpoint catches up. Recovery must reconcile the durable stage
evidence before it writes terminal attempt state or coverage.

The runner also measures memory while stage telemetry grows. Python traced
allocations and process maximum resident memory cover different scopes and
carry different measurement noise. The tests need local allowances for those
measurements without presenting them as production limits.

Retry receipts are copied and can receive equal or reordered file modification
times. Their mtimes therefore cannot establish the order in which retries
occurred. The append event ledger provides the chronology for sequenced
retries; old retries without sequence evidence remain ambiguous.

## Decision

- On worker interruption, reconcile finalized stage/index evidence into the
  attempt summary before persisting terminal state and coverage.
- Keep Python traced allocation and process RSS as separate measurements. The
  retained-memory test allows 2 MiB of traced-allocation noise and 16 MiB of
  process-RSS noise for its fixture; these are test tolerances, not general
  resource guarantees.
- Derive retry chronology from sequenced append-ledger events, never receipt
  mtimes. Reordered or equal mtimes must preserve the event-derived result;
  legacy retries without sequence evidence stay explicitly ambiguous.

## Consequences

Attempt recovery tolerates interruption between durable writes without losing
an applied stage. Memory assertions distinguish Python allocations from
process-level resident memory, and their fixture tolerances cannot be cited as
runtime caps. Retry reporting remains stable when receipts are copied or have
equal timestamps, while incomplete historical ordering is not guessed.

## Evidence

`tests/reporting/test_closed_loop_runner_failures.py` covers recovery after
stage finalization, retained worker memory as stage telemetry grows, the
separate measurement scopes, retry ordering under reversed and equal receipt
mtimes, and explicit ambiguity for legacy unsequenced retries.
