# EXT-07 process CPU observation design

## Problem

EXT-07 stores operation evidence at path, solver-branch, and verification-phase boundaries, but CPU values are only captured for a whole report process. The default timing collector has no CPU clock, and the existing process memory observer belongs to experiments and measures snapshots rather than operation peaks. The next increment should expose what the coordinator can measure without calling it provider-only CPU or implying memory attribution.

## Usage (caller's view)

The caller continues to execute the prepared request and reads each value next to its path/branch identity:

```cpp
auto execution = execute_hybrid_request(std::move(prepared), context);
for (const auto& branch : execution.branches) {
    if (const auto* observed = std::get_if<ProcessCpuDuration>(&branch.process_cpu))
        write_branch_cpu(branch.path, observed->nanoseconds);
}
```

Reachability attempts expose the process CPU delta for that path's staged execution. Verifier evidence exposes the delta for the full verification phase, including coordinator checks and path enumeration. Callers do not create timing spans or correlate results through a second table.

## Shape

The synthesis domain owns one typed observation:

```cpp
struct ProcessCpuDuration {
    std::uint64_t nanoseconds;
};
struct ProcessCpuUnavailable {
    enum class Reason { not_measured, unsupported_platform, clock_read_failed, clock_regressed } reason;
};
using ProcessCpuObservation = std::variant<ProcessCpuDuration, ProcessCpuUnavailable>;
```

`HybridReachabilityAttempt`, `HybridBranchExecution`, and `HybridVerifierResourceEvidence` each own one `ProcessCpuObservation`. The containing record fixes the interval identity. Their comments describe the existing wall-time interval and state that the CPU clock sums all process threads and may include unrelated concurrent work.

A private sampler in `src/synthesis/hybrid_path_program.cpp` reads a process CPU clock before and after the existing operation scope. Use `GetProcessTimes` on Windows and `clock_gettime(CLOCK_PROCESS_CPUTIME_ID)` where available. Clock conversion, overflow, failure, unsupported platforms, and a regressing interval resolve to an explicit unavailable reason. The synthesis module does not depend on experiments and does not expose the operating-system clock to callers.

The EXT-07 drivers serialize one typed observation per call and path/branch. Collectors validate shape and values and preserve raw rows in new content-addressed reports. Renderers identify the scope as process CPU during the operation and retain the concurrency caveat. Existing saved reports and whole-process resource bundles remain immutable. Process resident memory remains whole-process evidence; this design adds no per-operation heap claim.

This keeps the public interface shallow: callers inspect one result value and do not manage clocks, spans, or provider callbacks. Unavailability is explicit rather than encoded as zero or an empty optional.

## Synthesis decision

Both candidates place measurement at the coordinator-owned path, branch, and verifier intervals and keep the OS clock private to synthesis. Candidate A uses optional nanoseconds directly on each result. Candidate B uses a `ProcessCpuObservation` variant with explicit unavailable reasons. Candidate B is the base because a plain optional cannot distinguish a clock failure from an unsupported platform or a stage that was never called. Candidate A's smaller coordinator-local sampler and direct attachment to existing identity records are retained. Its extra optional behavior is not.

The cross-judge phase was skipped: the configured cross-judge pool contains only `gpt-6-luna`, in the same model family as the candidate runners and parent.

## Tradeoffs accepted

- We accept process-wide CPU contamination from concurrent work in exchange for including CPU used by backend worker threads without adding provider-specific hooks.
- We accept optional platform support through an explicit unavailable value; this does not claim that every platform supplies the same clock.
- We accept three fields on existing records in exchange for preserving their existing path, branch, and phase ownership.
- We accept that heap use and provider-only CPU remain unmeasured; process CPU is a diagnostic interval, not proof of provider consumption or enforcement.

## Alternatives considered

- **Raw optional nanoseconds on each result record:** shorter at the call site, but collapses unsupported, failed, and not-measured states. The typed variant has a slightly larger value shape and makes those states distinguishable.
- **Extend `TimingCollector` with dynamic hybrid spans:** reuses clock infrastructure, but requires planned span identities and correlation back to path records. Its process CPU metric currently applies only to the root span, so the generic collector would need a wider lifecycle change for a hybrid-specific requirement.
- **Provider CPU callbacks:** could provide stronger attribution for a backend that supports them, but each adapter would need its own semantics, and worker-thread accounting would vary. This remains a later path to provider-specific evidence.

## Open questions and risks

- Captures must run without unrelated background work if their per-operation process CPU values are compared. Reports retain the caveat and do not label the value provider CPU.
- A future provider-specific CPU observation needs a separate source and must not overwrite or silently redefine process CPU.
- Existing heap observations remain scoped to whole-process fixtures; no per-transition allocation or peak-memory evidence follows from this change.

## Next implementation step

Add the domain observation type and a private platform process CPU sampler at the three existing coordinator boundaries, then serialize the per-call values in both EXT-07 report pipelines.
