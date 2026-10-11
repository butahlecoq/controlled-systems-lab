# HiGHS reference LP adapter

`<csl/adapters/lp/highs.hpp>` provides `make_highs_registration(options)`.
Link `CSL::highs_lp`, add the returned registration to `Registry<LPPort>`, select
`csl.lp.highs`, then prepare, create, and run through the existing registry.
Registration returns `Diagnostics` for unsupported configuration. Selection uses
output representation `csl.program-result.v1`, binary64, numerical assurance.
The adapter version is `1.0.0+highs.1.11.0`. There is no automatic fallback.

```cpp
using namespace csl;
using namespace csl::registry;
auto registration = csl::adapters::lp::make_highs_registration();
Registry<LPPort> registry;
registry.add(std::get<Registration<LPPort>>(std::move(registration)));
Requirements required;
required.output.representation = {"csl.program-result.v1"};
// program is a published canonical LinearProgram.
auto plan = prepare_pipeline(select(registry, {{"csl.lp.highs"}, {}}, program, required));
auto [worker] = std::get<PreparedPipeline<LPPort>>(plan).create();
auto outcome = worker->run(context);
```

Applications must handle the documented variants and registration/preparation
rejections. This abbreviated example shows the successful path. LPDataResult
remains the canonical publication/evaluation result alias; no competing LP data
or evidence interface is introduced. See [linear programs](linear-programs.md)
for identity, row/bound, objective offset, residual, and evidence conventions.

## Native dependency and supported profile

The build uses the ADR 0002 HiGHS **1.11.0** archive:

- URL: <https://codeload.github.com/ERGO-Code/HiGHS/tar.gz/refs/tags/v1.11.0>
- SHA-256: `2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275`
- Upstream interface: [Highs.h at v1.11.0](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/Highs.h).
- License: MIT. Installation also includes the bundled file-reader MIT notice
  and pdqsort notice, preserving their relative paths beneath
  `share/CSL/notices/HiGHS-1.11.0`.

The adapter selects serial simplex, presolve off, parallel off, one native
thread, seed zero, and disallows an ambiguous unbounded-or-infeasible shortcut.
`HighsLPOptions::simplex_iteration_limit` is an optional nonnegative native
simplex iteration limit (including zero); an absent value selects the native
integer maximum. Values exceeding that width reject before native allocation.
The capability callback reads the immutable program without constructing HiGHS
or copying its numerical buffers.

Finite canonical values must retain their meaning across the boundary. The
native `infinite_bound`, `infinite_cost`, and `large_matrix_value` options are
set to infinity. A finite bound such as 1e21 remains finite. HiGHS removes tiny
nonzero matrix entries even when `small_matrix_value` is set to its supported
minimum 1e-12. The adapter therefore rejects nonzero coefficients with absolute
value <=1e-12 instead of silently dropping them. Explicit zero entries are
permitted. Native integer width is checked for rows, columns, their sum, and
stored entry count before indices are narrowed. Canonical publication already
checks dimensions, CSR structure, finite values, and interval ordering.

Absolute feasibility tolerance must be finite and >=1e-10, the native minimum;
smaller values are unsupported. Negative or nonfinite absolute/relative
policies are invalid input. Relative tolerance is used by the canonical CSL
residual checks; it is not a native relative stopping tolerance. Both native
primal and dual feasibility tolerances use the requested absolute tolerance.
Scaling and numerical failure remain possible; this is not validated arithmetic.

## Ownership, reuse, and stops

Each created workspace exclusively owns its native solver and mutable state.
Copies of registrations and prepared plans retain immutable configuration and
program snapshots. Destroying the caller's request, registry, or prepared plan
does not invalidate a created workspace. Concurrent callers use distinct
workspaces; concurrent calls on the same workspace are outside the contract.
The underlying NVI supplies the authoritative workspace identity and attempt
sequence, including unsupported, stopped, and exceptional calls.

A successfully loaded program is retained. Repeated calls with the same
ProgramIdentity may reuse native model and basis state; a different identity
reloads the model in the same private solver. As with canonical LP identity,
the caller must assign a new ProgramId to changed mathematical data. This is
not a public warm-start or native basis interface. Every result owns its copied
primal, residuals, and diagnostic text. Previous results and stamps survive
later calls. Unexpected exceptions clear the private solver and loaded state,
then propagate through the NVI's exceptional-attempt handling.

Per-attempt logs and stop state are local. Native clocks are reset before each
attempt and the time limit is reset to the remaining deadline or infinity.
A pre-requested cancellation returns cancelled/undetermined without a previous
candidate; an expired deadline similarly returns resource_limit/undetermined.
Checks also run after model loading. Synchronous simplex callbacks poll the
stop token and deadline, record the first observed cause, and request native
interruption. Cancellation is cooperative at these boundaries; translation,
factorization, or an already completed solve cannot be forcibly interrupted.
No watcher thread calls HiGHS concurrently.

Positive resource budgets are checked with `check_resources`; actual native
use is one thread. A supplied memory_bytes policy is unsupported because this
adapter cannot enforce its admission requirement. HiGHS has thread-local
scheduler handles. Independent workspaces can run on distinct caller threads
with the supported one-thread profile. The adapter never resets the global
scheduler or takes over another native client's scheduler. An incompatible
existing scheduler produces an honest native failure with its diagnostics.

Callback registration is scoped to one synchronous call and is removed before
its borrowed context/log state is destroyed, including exception unwinding.
Pinned HiGHS 1.11.0 gates log callbacks on `log_to_console` when no log file is
open. Consequently the adapter sets this option true while an active logging
callback replaces the console output path. No native log file is opened.
This detail follows [HighsIO.cpp](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/io/HighsIO.cpp).
The callback captures native messages in the returned diagnostics. Tests check
that native model messages are captured; the executed test/client output was
also inspected for unexpected native console messages.

## Results and evidence

Termination and mathematical outcome are separate:

| Native model status | Neutral termination / mathematical report |
|---|---|
| Optimal | completed / optimal |
| Infeasible | completed / infeasible |
| Unbounded | completed / unbounded |
| UnboundedOrInfeasible | completed / undetermined |
| TimeLimit, IterationLimit, MemoryLimit | resource_limit / undetermined |
| ObjectiveBound, ObjectiveTarget, SolutionLimit | resource_limit / undetermined |
| Interrupt | recorded cancellation or resource limit / undetermined; otherwise numerical_failure |
| Notset, load/model/presolve/solve/postsolve error, unexpected ModelEmpty, Unknown | numerical_failure / undetermined |

A native API error does not erase a recognized resource model status: in
particular MemoryLimit can accompany `HighsStatus::kError`. Candidate and info
values from an API error are withheld. Other API errors remain numerical
failures. Native optimal/infeasible/unbounded reports carry **Unestablished**
outcome support. Native flags and tolerances do not constitute mathematical
certificates. No result supplies a justified objective lower or upper bound,
infeasibility certificate, unbounded ray, or optimizer family.

For a current valid finite native primal of the correct size, `evaluate_primal`
recomputes the original objective (including its offset), row residuals, and
variable-bound residuals. The original cost is included in raw diagnostics;
callers can reproduce it through the canonical evaluator. Nonfinite or invalid
primal/evaluation data causes numerical_failure/undetermined, with no candidate.
Residual context identifies the original ProgramIdentity and verifier
`csl.lp.highs.primal` version `1` with the caller's tolerances.

When native dual data is valid, finite, and correctly sized, signed row and
column duals are translated to canonical lower/upper multipliers. For two finite
endpoints, the positive part belongs to the lower endpoint and the negative
part (negated) to the upper. For a single endpoint, its signed multiplier is
retained, including a wrong sign that must remain observable as a violation.
A nonzero multiplier on a free interval cannot be assigned to an absent endpoint;
that dual check is unavailable and diagnostics explain why. `evaluate_dual`
reports stationarity and multiplier-sign residuals under verifier
`csl.lp.highs.dual` version `1`. Its Lagrangian constant is not promoted to a
bound. Complementarity is unavailable. Stopped results can carry only current
valid candidate/residual data and never imply optimality.

Zero-variable programs require a separate exact constant-row check: the pin
returns ModelEmpty before testing constant-row contradictions. If each interval
contains zero, the adapter returns an empty primal with its original offset;
otherwise it reports infeasible. These outcomes still use Unestablished support.
Diagnostics explicitly say `native_run=false` and
`wrapper.decision=constant_rows`; they do not invent a native solve.

Raw diagnostics retain adapter/native versions, native Git hash (which can be
`n/a` for the archive), archive pin, program identity, solver options, tolerance
roles, native load/call/model status codes and names, valid objective and
infeasibility information, iterations, model reuse, stop cause, and native logs.
Unavailable native info is labelled unavailable. Returned numerical structures
are checked against the canonical `check_program_result` contract in tests.

Basis diagnostics and pivots are unavailable: selection requiring them rejects
and an ordinary bound workspace has `basis()==nullptr`. Native internal basis
reuse does not implement the canonical ordered original-row basis contract.
Validated assurance, other scalar types, complete families, and unsupported
output representations reject at selection.

## Packaging and tests

`CSL::highs_lp` publicly links the neutral optimization and registry targets.
The native archive is private through a static `LINK_ONLY` dependency on the
exported implementation target `CSL::private_highs_native`. This target is CMake
link metadata, not a supported native API. The installed package carries the
archive and notices, with no native headers or native include directories.
The consumer uses only `find_package(CSL CONFIG)`; Threads is its platform
system dependency and no external HiGHS package is required.

Both public-header include-order fixtures include the neutral adapter header
while retaining numeric/contracts-only linkage. A separate copied installed
consumer links only `CSL::highs_lp` and performs a real registered offset LP
solve. Tests use independent literals: triangle optimum (0,1), cost -2 or 5
with offset7; equality solution (0.5,0.5); free/fixed solution (1,2), cost5;
contradictory rows; unbounded -x; zero dimensions; and finite fixed 1e21.
They also exercise capability rejection, real iteration-limit termination,
pre-stops, repeated/model-changing workspace calls, owning history, and
concurrent independent workspaces. Rare native errors such as MemoryLimit are
reviewed in the mapping, not claimed to have been induced by unit tests.
These fixtures do not establish general certificate validity, numerical
robustness across all LPs, a performance claim, or complete minimizer enumeration.
