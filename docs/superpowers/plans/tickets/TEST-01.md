# TEST-01: Expand native buffer, ownership and build-boundary tests

GitHub: [#19](https://github.com/butahlecoq/controlled-systems-lab/issues/19).

## Purpose and scope

Test C++20 owning values/views, storage/stride conventions and native module boundaries (RUN-01/02, ALG-07). Limit: memory-safety tooling and compile probes support declared platforms; they do not establish a portable C++ ABI.

Requirements: REV-02. Test oracles: T-N01 (proposed), T-M02, T-R01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Use a fixed nonsquare matrix [[1,2,3],[4,5,6]] and vector [7,11,13]: each supported row/column-major or strided view yields [68,161] against a hand-calculated oracle; malformed stride/shape is diagnosed.
- [ ] Exercise copy/move and retained-owner asynchronous paths; destroy source owners at controlled points and check documented retention or rejection rather than relying on incidental object lifetime.
- [ ] Compile a backend-neutral public-client fixture without matrix/solver private include paths; verify installed headers contain no selected backend container dependency.
- [ ] Run supported sanitizer/debug-iterator checks with recorded toolchain; zero-length ports have defined behavior and no invalid access.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [CORE-02 #12](https://github.com/butahlecoq/controlled-systems-lab/issues/12), [CORE-03 #13](https://github.com/butahlecoq/controlled-systems-lab/issues/13), [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
