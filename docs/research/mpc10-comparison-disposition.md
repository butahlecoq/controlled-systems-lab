# MPC-10 comparison acceptance and delivery disposition

Issue [#606](https://github.com/butahlecoq/controlled-systems-lab/issues/606)
requests separate finite, mixed and hybrid comparisons. Its historical no-run
sentence was superseded by the user's explicit benchmark authorization.
Prerequisites #596/#83/#76/#156 were closed at the claim/refetch checkpoint.
This bounded source/report unit preserves every attempted outcome and keeps
publication/closure pending independent review and current CI.

| Acceptance requirement | Concrete evidence and boundary |
| --- | --- |
| Reuse domain/branch semantics and short enumeration | `benchmarks/reporting/mpc10/bridge.cpp` uses public finite-history and branch-specialization APIs, the public Strategy B joint builder, registered native LP execution, and public hybrid portfolio/path construction. Finite controls use the exact zero-dimensional continuous embedding. `oracle.py` independently enumerates catalogue-index or mode/edge histories. |
| Flow/invariant/guard/reset/terminal timing | `check.py` independently reconstructs each native joint LP, including source invariant at the current and pre-reset state, guard before reset, destination invariant after reset and terminal-mode objective. Failure fixtures isolate each boundary. Common-dimension affine functional resets are admitted; declarations of dimension change and general relational resets are retained as external-encoding unsupported. |
| One-hot/indicator formulation | `scip_reference.py` uses catalogue/mode/edge one-hot variables, exact graph adjacency and native linear indicators, with equalities split into two inequalities. Finite variable bounds are authored bounds or mode unions. No guessed-M or action/mode convexification is used. |
| Parallel identity, ties and continuous-family scope | Duplicate catalogue rows and parallel edge IDs remain distinct. Exact minima/tie inventories and all native rows are checked. Actual exact-H family verification establishes the one-step hybrid/flat cases. Longer T=2/3 native family proofs remain unsupported when exact inclusion cannot be decided; the independent candidate-face row checks remain separate. SCIP incumbents/bounds are numerical and never treated as a complete continuous family. |
| Refusals and interrupted search | Saved cases include forbidden transitions, failing source/pre invariants, guards and destination invariants, tied/worse terminal modes, T=0, empty catalogue/all-infeasible histories, a partial history budget, transactional hybrid path-budget refusal, cancellation and actual SCIP node-limit termination. Unknown bounds/gaps remain unavailable, not zero-cost successes. |
| Costs, counts, example and qualification | The evidence contains per-case counts, native registration/enumeration/formulation/LP-load/LP-run/family-check clocks, SCIP unrestricted setup/solve and extra fixed-history costs, process CPU/RSS and raw failures. Two saved SVG/PNG figures show the actual two-dimensional path and parallel edge labels using the shared Matplotlib style. These single configured observations make no speed ranking. |

The clean capture commit is `525871ea`; its immutable raw archive includes 26
fixtures, 119 native fixed-branch LPs, 24 unrestricted SCIP models, 131 additional
fixed-history SCIP solves and one deliberately interrupted SCIP model. The
independent checker validates all supplied branch rows/values and preserves
prefix/refusal/unsupported statuses. Source snapshots match capture digests and
Git objects; the current reviewing tools and figure producer are fingerprinted
separately. Renewing an inventory cannot make changed copied source or a stale
verification receipt valid. Impossible nested clock spans are rejected.

The comparison exposed the exact-H coverage aggregation bug tracked in
[#910](https://github.com/butahlecoq/controlled-systems-lab/issues/910), fixed in
[PR #912](https://github.com/butahlecoq/controlled-systems-lab/pull/912).
The original T=3 result reported global coverage refuted while its branch
coverage proofs were unsupported. That raw result remains literal and unchanged.
The qualified capture contains the corrected unsupported status. A later
core-only refinement preserves known suboptimal-branch refutations across an
unknown objective; its new predicate is false on every saved family report.
The measured records remain observations of their original capture source,
with no claim of remeasuring the later core revision.

The qualified local environment is Linux x86-64, GCC 16.2.1 Release/C++20,
existing pinned HiGHS 1.11.0, Python 3.14 and existing PySCIPOpt 6.3.0 / SCIP
10.0.2. No dependency installation or native dependency build was performed.
Native memory admission is unavailable and is not requested; the worker's
actual 90-second CPU, 120-second wall and 2-GiB address-space limits are POSIX
process limits. SCIP also receives per-model limits. Requested and observed
thread/resource evidence retain their actual scope; cumulative child maximum
RSS is not simultaneous tree memory or native heap accounting.

The installed PySCIPOpt metadata/license is
[MIT](https://github.com/scipopt/PySCIPOpt/blob/v6.3.0/LICENSE); the SCIP project
publishes its [Apache-2.0 license](https://www.scipopt.org/doc/html/LICENSE.php).
The environment receipt fingerprints the wrapper, native SCIP and bundled
runtime libraries. This source/report artifact redistributes no solver/runtime
binary. Existing HiGHS notices/pins remain applicable. Windows/macOS capture
qualification and binary redistribution are not claimed. No acados, MATLAB or
MPT3 runtime is used.

No core API, required dependency or installation artifact is added by the
comparison. The separate #910 patch corrects proof-status reporting within
existing types. No standalone library release is required for this optional
source/report consumer. Root owns managed Pages augmentation/catalog changes;
this unit does not edit them or deploy. Exact-head independent standards and
specification review, current CI, publication contract checks and a verified
live route remain before any #606 closure. A completion audit must assess the
bounded admitted profile and its explicit proof limits; this document does not
silently broaden them into general hybrid control or a timing winner.

## Publication adapter

The unique `scripts/reports/stage_mpc10_comparison.py` hook stages the two saved
figures and all26 complete minimal fixtures beside the unchanged original
archive. A separately versioned current receipt/metrics reading layer records
checker strengthening without rewriting measured records or their original
source provenance. The complete offline ZIP includes a minimal authentic Git
object store, not a full checkout or fabricated history. Current helper identity
uses the last first-parent helper change, including merges, so unrelated commits
preserve its route. Every actual helper byte must match the selected commit.

Standard-library staging/offline validation checks all source/raw/receipt and
metrics bindings. Full saved mathematical/model checking outside the checkout
uses the existing qualified PySCIPOpt6.3.0/SCIP10.0.2 environment to reconstruct
indicator models and compare raw records; it performs no optimization or native
execution. No environment installation is required for staging, and no native
or solver binary is redistributed. The main-only cumulative integration remains
root-owned. The live immutable route, deployed hashes and completion audit are
pending; this source adapter alone does not complete #606 delivery.

The [local publication qualification](evidence/mpc10-local-publication-11c3fe96.json)
records the staged route/source/object and ZIP identities, six passing publication
boundary tests, and the full saved26-case recheck in an extracted directory outside
a Git checkout. Its source and receipt checks use a sanitized Git environment;
all119 native LPs,24 unrestricted SCIP models,131 fixed-history models and the
node-limit outcome recheck without optimization/native execution. This is local
verification evidence, not a published URL or completion claim.
