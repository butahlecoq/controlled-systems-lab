# MPC comparison: primary sources and admissible task mappings

Date: 2026-10-23. Status: research and planning only; no benchmark, solver invocation, or dependency change. Companion planning issues were published separately, as indexed below. Sources were accessed on this date unless an existing repository evidence record supplies its own date. Recommendations below are judgments about **task fit**, not citation-count or state-of-the-art rankings.

## Executive recommendation and repository boundary

There is no single fair "our methods versus MPC" experiment. MPC is a receding-horizon deployment scheme; reachability/backward recovery, direct trajectory optimization, minimax policy search, and QP solvers occupy different layers. First match the mathematical problem and requested output, then compare algorithms or implementations within that overlap.

- For the existing nominal affine planning tasks, a convex LP/QP formulation is the natural outside reference. OSQP and HPIPM are implementable solver candidates, **not robust-control algorithms**. Neither an ordinary QP solve nor an explicit MPC controller supplies this repository's requested complete optimal-plan family.
- For the current finite fixed-plan minimax track, retain exhaustive catalogue semantics and independent complete checking. Do not replace it with a feedback tree, tube controller, continuous-action relaxation, or sampled uncertainty experiment and call that parity.
- For a separately approved continuous full-state robust-control extension, study rigid tube MPC and affine disturbance-feedback MPC first; add contemporary SLS-MPC as a policy/uncertainty-approximation research candidate. Distinguish feasible robust policies and cost upper bounds from globally optimal causal minimax synthesis.
- do-mpc is a useful implemented scenario-tree reference, but its documented robust multi-stage objective is a **weighted sum**, not automatically worst-case cost. Its robust horizon also changes the represented uncertainty histories.
- **acados is researched background only, not a selected executable comparator.** The owner's final [#513 disposition](https://github.com/butahlecoq/controlled-systems-lab/issues/513#issuecomment-6353231831) accepts B04 `ACADOS_MAXITER` as optional/inconclusive and authorizes no further acados run, tuning, benchmark, pairing, or reproduction claim. Any future acados proposal requires a distinct owner decision; this note does not reopen the spike. See the [recorded cross-check](acados-stage3-single-witness-cross-check.md).

Grounding: [README](../../README.md), [comparison-program contract](../architecture/comparison-program.md), [linear-system contract](../architecture/linear-system-contract.md), and [framework composition](../architecture/framework-composition.md). The first workflow is nominal continuous-action planning with complete optimal families; reviewed T-S01/T-S02 profiles do not establish general coverage. The fixed-plan minimax module is exhaustive, caller-limited and numerical. The finite-feedback port establishes finite-table winning/safety actions, not cost-optimal continuous feedback. Controller callbacks provide sampled replay, not a synthesized robust estimator/controller; hybrid fixed-path capabilities do not establish global mode selection.

**Live-state correction:** [#5](https://github.com/butahlecoq/controlled-systems-lab/issues/5#issuecomment-6245014055) is **closed for its stated review acceptance**, not an open implementation gate. Older comparison-contract wording that says "after #5 closes" is historical planning text, not evidence that continuous or output-feedback synthesis now exists. Those capabilities still need separate contracts, implementation and evidence. [#422](https://github.com/butahlecoq/controlled-systems-lab/issues/422) already owns finite fixed-plan paired records; the parent session reports [#3](https://github.com/butahlecoq/controlled-systems-lab/issues/3) actively claimed for the global oracle. Do not duplicate either effort. Tracker status is a dated observation, not authorization.

## 1. Quantifiers and outputs that must not be conflated

Use the repository's affine dynamics

\[
x_{t+1}=A_tx_t+B_tu_t+E_tw_t+a_t.
\]

The following are distinct even when they share matrices, constraints and a horizon. Here the disturbance is realized **after** the current control, and the initial state is known unless explicitly stated otherwise.

| Task/policy | Decision and uncertainty semantics | What a successful solve establishes |
|---|---|---|
| Nominal fixed-horizon planning | Choose the whole sequence \(\mathbf u\), with no unknown disturbance | One optimum, an optimal value, or a complete argmin relation, depending on the algorithm/output contract |
| Fixed-plan robust/minimax | \(\min_{\mathbf u}\max_{\mathbf w\in\mathcal W}J\); constraints hold for the **same** \(\mathbf u\) for every \(\mathbf w\): \(\exists\mathbf u\,\forall\mathbf w\) | A robust plan and, only with adequate global evidence, its fixed-plan minimax optimum |
| Causal multi-stage minimax | \(u_t=\pi_t(I_t)\); under full-state observation the alternating feasibility order is \(\exists u_0\forall w_0\exists u_1(x_1)\forall w_1\cdots\) | A nonanticipative policy; optimality only over the declared policy class and uncertainty tree/set |
| Affine disturbance feedback | \(u_t=v_t+\sum_{j<t}M_{tj}w_j\), with strictly causal disturbance dependence | A restricted policy class, convexly parameterizable under the additive full-state assumptions of [P5] |
| Tube MPC | Nominal trajectory plus ancillary feedback, e.g. \(u_t=v_t+K(x_t-z_t)\), with a sound error enclosure | Robust constraint satisfaction under the tube assumptions; not unrestricted causal minimax optimality [P3] |
| Sampled scenario optimization | Enforce constraints on sampled uncertainty histories | Sample feasibility; a violation-probability bound only if an applicable scenario theorem's assumptions/sample bound hold [P8] |
| Receding horizon / replanning | Solve a planning/policy problem, apply its first action, observe, repeat | An executed feedback law; repeated fixed-plan optima do not make it globally causal-optimal [P1, P5] |

### Classify each comparison row

Give every comparison row one of these four kinds. The kind states what the row
can establish; it does not replace the model, output, or evidence fields.

| Comparison kind | Required match or declared difference | Claim allowed by the result |
|---|---|---|
| `matched-problem-single-witness-value` | Match the model, grid, information, domains, objective, horizon, and constraints. An external solver may return one witness. | Compare independently checked witness feasibility and objective values. Do not infer complete-family coverage from one witness. |
| `discrete-to-continuous-relaxation-bound` | Keep the objective and policy class fixed, and state the action-set inclusion that makes one problem a relaxation of the other. | Report the justified bound direction and gap. Do not call the relaxed result an equivalent discrete optimum. |
| `restricted-policy-conservatism` | Keep the dynamics, uncertainty, cost, and constraints fixed. State the restricted policy class and prove that its returned policy is feasible in the broader class. | A verified policy gives an upper bound on the broader optimum. Call the difference a class conservatism gap only when both class optima have adequate evidence. |
| `closed-loop-controller-experiment` | Declare the controller, observation timing, replanning schedule, simulator, disturbances, and run protocol. | Compare executed trajectories and declared closed-loop metrics. Simulation alone does not prove robust safety or global optimality. |

Keep an external solver result outside `StrategyPort` unless a separately
reviewed interface proves that its evidence meets the port contract. Store its
problem identity, effective request, solver and version, configuration,
termination, mathematical outcome, witness, independent checks, and run
provenance in a separate external-result record linked to the comparison
record. Reuse the saved-record contracts in [#83](https://github.com/butahlecoq/controlled-systems-lab/issues/83)
and [#84](https://github.com/butahlecoq/controlled-systems-lab/issues/84).
Report time to first witness separately from time to complete an optimal
family. A one-trajectory result cannot stand in for the complete-family output
requested by CSL.

### Proposed external result record (contract for review; no adapter authorized)

The following versioned JSON shape is a concrete proposal to take to the
separate #83/#84 record review. It is deliberately an evidence record, not a
`StrategyPort` result: `comparison_id` links the paired comparison; `run_id`
and the `problem` digest identify the external execution; `request` preserves
what was asked and what the adapter actually sent; and `outcome` states the
limited claim the record supports. A future adapter must not write this format
until the #83/#84 owners approve its schema and migration/compatibility plan.

```json
{
  "schema": "csl.external-control-result/1",
  "run_id": "<stable unique id>",
  "comparison_id": "<#83/#84 comparison record id>",
  "problem": {
    "case_id": "<fixture id>",
    "model_sha256": "<digest of canonical model, grid, domains, costs and constraints>",
    "information_pattern": "<open-loop | causal-full-state | other declared contract>",
    "policy_class": "<declared policy class>",
    "horizon": 0
  },
  "request": {
    "comparison_kind": "<one of the four kinds above>",
    "requested_output": "<witness | bound | policy | controller-run>",
    "effective_problem_sha256": "<digest after adapter translation>",
    "translation_notes": "<lossless mapping or each declared change>"
  },
  "solver": {
    "name": "<solver/framework>",
    "version_or_commit": "<immutable version/commit>",
    "stack": [{"name": "<dependency>", "version_or_commit": "<pin>"}],
    "platform": "<OS, architecture, compiler/runtime>",
    "configuration_sha256": "<digest of effective options>",
    "license_manifest": "<record or link for full dependency/license inventory>"
  },
  "execution": {
    "status": "<completed | infeasible | unbounded | max-iterations | timeout | cancelled | error | unsupported>",
    "termination_detail": "<solver-native status/message, including cancellation source when cancelled>",
    "started_at_utc": "<timestamp>",
    "wall_time_seconds": 0.0,
    "setup_time_seconds": 0.0,
    "online_time_seconds": 0.0,
    "resource_protocol_id": "<published budget/protocol id>",
    "threads": 1,
    "seed": null
  },
  "outcome": {
    "claim": "<feasible-witness | objective-value | lower-bound | upper-bound | policy | trajectory | none>",
    "objective_value": null,
    "bound": null,
    "bound_direction": "<lower | upper | none>",
    "gap": null,
    "witness_sha256": null,
    "policy_sha256": null,
    "complete_family_coverage": "not-provided"
  },
  "verification": {
    "checker_id_and_version": "<independent checker or none>",
    "original_data_feasibility": "<pass | fail | not-checked>",
    "objective_recomputed": "<pass | fail | not-checked>",
    "claim_specific_certificate": "<artifact digest/reference or none>",
    "notes": "<limitations; never infer family coverage from a witness>"
  },
  "artifacts": [{"role": "<log | input | output | plot | other>", "sha256": "<digest>", "path_or_uri": "<immutable artifact reference>"}]
}
```

Fields with `null` or `none` are explicit absence, not success. A failed,
unsupported, timed-out, or maximum-iteration run remains a record with its
native termination details and logs. `effective_problem_sha256` must differ
from the canonical problem digest when translation changes the mathematical
problem; the notes then identify the change so a relaxation or restricted
policy cannot be mislabeled as a matched result. A `pass` in replay checks only
the stated witness; it is not a global optimality, robust-safety, or
complete-family certificate. `complete_family_coverage` is always
`not-provided` for this external one-witness contract. The #83/#84 review must
decide digest canonicalization, artifact storage, schema evolution, and whether
any existing record should embed or reference this object.

An exhaustive finite-support scenario tree is not "sampling" if it covers the entire declared finite uncertainty model. Conversely, a handful of extreme parameter choices in a nonlinear model is not automatically a sound enclosure of continuous uncertainty. Nonanticipativity ties controls with the same **available information**, not merely histories that happen to look similar in one simulation. Partial observation may merge different physical states into one information node. A tree that reveals hidden parameters too early solves an easier, different problem. [P4–P6; repository linear-system contract]

For identical dynamics, uncertainty, objective and admissibility, fixed plans form a subset of causal policies; therefore \(V_{\rm causal}\leq V_{\rm fixed}\) for minimization. A restricted feedback policy class gives an upper bound on unrestricted causal cost when it is soundly feasible; an approximation of its cost may add another upper bound. With the **same policy class**, replacing a finite action catalogue by an interval containing it is a relaxation and can lower the optimum. These are mathematical inclusion arguments, not paired algorithm victories. No direction follows after simultaneously changing objective, uncertainty or information.

Safety requires **whole-successor-set containment**, not nonempty intersection with a safe set. For fixed affine trajectories, convex stage constraints and convex terminal cost, complete disturbance-polytope vertex evaluation can be justified by convexity. That shortcut does not automatically evaluate an optimized feedback/replanning value function: the repository's [adaptive-policy audit](adaptive-policy-proof-audit.md) and [finite-policy reference](finite-policy-class-reference.md) exhibit the relevant policy gap and interior-disturbance caveat.

## 2. Foundational papers: what they contribute, and what they do not

These papers are selected for foundational relevance and the user's requested coverage; no numerical influence ranking is asserted.

| Primary work | Mathematical contribution and guarantee boundary | Comparison use |
|---|---|---|
| **Mayne, Rawlings, Rao, Scokaert (2000), constrained MPC stability/optimality** [P1] | Review of finite-horizon optimization implemented by applying the first input and resolving. Stability and finite/infinite-horizon equivalence require the appropriate design hypotheses; they are not properties of any feasible QP or any horizon by default. | Vocabulary and checklist for nominal/receding-horizon tasks. Terminal penalties/sets and stage costs must not be silently added to the repo's terminal-only task. |
| **Bemporad, Morari, Dua, Pistikopoulos (2002), explicit constrained LQR** [P2] | Multiparametric QP produces a piecewise-affine state-feedback law over polyhedral regions for the stated constrained linear-quadratic problems. Transfers computation offline; region construction/storage can grow substantially. The standard strictly convex setting selects a unique optimizer, unlike flat-cost family tasks. | Small-dimensional explicit-policy/geometric reference. A partition indexed by initial state is **not** the complete set of all optimal trajectories at one state; nominal explicit MPC does not itself add disturbance robustness. |
| **Mayne, Seron, Raković (2005), bounded-disturbance tube MPC** [P3] | Optimizes nominal initial state as well as the control sequence; couples a nominal QP with ancillary feedback and a disturbance-invariant error set. Establishes robust exponential stability of the disturbance-invariant set under its assumptions, rather than convergence of every persistently disturbed trajectory to the origin. | Particularly useful bridge between this repo's set operations/reachability and optimization. It solves a designed robust-control problem, not the original finite-catalogue fixed-plan minimax problem. |
| **Scokaert, Mayne (1998), min–max feedback MPC** [P4] | Foundational feedback-aware min–max formulation with fixed/variable-horizon variants. Planning future actions conditional on information is the central distinction from a single open-loop sequence; unrestricted feedback representations can incur tree/combinatorial growth. | The right conceptual comparator for **future** causal minimax, not current fixed-plan parity. This review did not retrieve readable full text from IEEE, so it does not transplant a specific theorem or assert its hypotheses are met here. |
| **Goulart, Kerrigan, Maciejowski (2006), disturbance-feedback parameterization** [P5] | Proves equivalence between admissible affine state-history feedback and affine past-disturbance feedback for the stated additive linear model. Uses robust counterparts for mixed polytopic state/input constraints. Its nominal quadratic-cost formulation yields a QP for polytopic disturbance or SOCP for a 2-norm bound. Robust constraint satisfaction and ISS use the paper's terminal/design conditions. | Tractable continuous feedback candidate with an explicit class restriction. The paper's cost is quadratic on disturbance-free predictions, **not automatically** the repo's maximum terminal cost. General nonlinear policies and noisy partial-state information are not covered by the equivalence. |

### Tube implementation obligations

For the standard additive model, choose a stabilizing \(K\) and a sound robust positively invariant error set \(Z\) satisfying

\[
(A+BK)Z\oplus EW\subseteq Z.
\]

The nominal state/input constraints become \(z_t\in X\ominus Z\) and \(v_t\in U\ominus KZ\), with the correct initial tube membership and terminal design. This is an attractive *research mapping* because it exposes support, Minkowski-sum, Pontryagin-difference and inclusion-oracle responsibilities. A sampled/error-volume check cannot certify the displayed inclusion. Offline set construction and its proof cost must not disappear from a later online-time comparison. The 2005 source also contains a supported 2D double-integrator example, but importing it would require a separately identified article-derived fixture rather than pretending it is the repository's horizon-3 demonstration. [P3; comparison contract]

### Disturbance feedback implementation obligations

Strict lower-triangular \(M\) prevents seeing current/future disturbances before acting. The full-state additive setting lets the controller recover the realized additive residual from past transitions; it need not separately identify every component of a noninjective disturbance channel. This is **not** available without qualification under noisy partial observations or unknown dynamics. Robust dualization, cost representation and terminal design must be independently checked; a convex program over affine policies is not a proof of optimum over every causal policy. [P5]

## 3. Contemporary candidates, with substantive caveats

### SLS and SLS-MPC: worthwhile policy research, not a drop-in backend

Chen, Preciado, Morari and Matni's **2024 Automatica** paper has an accessible author preprint [P7]. Finite-horizon System Level Synthesis uses causal response matrices satisfying

\[
[I-\mathsf Z\mathsf A\quad-\mathsf Z\mathsf B]
\begin{bmatrix}\Phi_x\\\Phi_u\end{bmatrix}=I.
\]

This affine identity parameterizes the nominal LTV state-feedback response class; it does not by itself solve robust constraints. The paper jointly designs responses and a filtered additive uncertainty **over-approximation**, giving a tractable tightened convex problem and an option to minimize a worst-case-cost **upper bound**. Distinguish exact response parameterization from conservative robust feasibility/cost approximation. Its polytopic model uncertainty is also richer than independent additive disturbance data and needs a model-family contract here. [P7, §§2–5]

**Important limitation:** §5.3 explicitly says ordinary fixed-horizon recursive feasibility is challenging and is not established by the paper's usual shifting argument. Its closed-loop guarantee route uses shrinking-horizon/safe backup policies and terminal invariant-set machinery, including an exact one-step problem after reaching that set. Do not advertise its main convex OCP as automatically fixed-horizon recursively feasible/stable. The paper's numerical comparisons are evidence for its reported cases, not a universal SOTA ranking or evidence about CSL. [P7, §5.3 and §6.3.1]

The authors' repository contains MATLAB implementations and tube/uncertainty-overapproximation baselines. It requires YALMIP and MPT3 and uses **MOSEK by default**. A public code repository is not necessarily an open-source licensed distributable: no license was visible in the inspected repository root and `main/LICENSE` returned 404. This is an unresolved permission check, not proof that no license exists anywhere. Do not copy/port it until rights are established. No release/CI maintenance commitment was established; treat it as paper research code, not a supported native C++ package. [S6]

### zoRO: implemented uncertainty tightening, not exact minimax

Frey et al.'s 2023 preprint / ECC-2024 implementation work [P6] describes zoRO in acados: alternate uncertainty propagation/backoff computation outside the reduced OCP with nominal-variable optimization; integrate with SQP/real-time iteration. The paper separates robust ellipsoidal and stochastic interpretations. Its robust uncertainty model is a **joint horizon ellipsoid**, not automatically the Cartesian product of independent per-stage ellipsoids or the repo's finite disturbance catalogue.

The paper discusses convergence to a suboptimal feasible solution of the **formulated uncertainty-aware problem**, with local/small-uncertainty and underlying-SQP assumptions. Nonlinear uncertainty propagation/constraint backoffs are approximate; feasibility of that formulation is not a global enclosure proof for arbitrary nonlinear plant disturbances. A single RTI step does not inherit an "at convergence" claim. Precomputed feedback gains are not unrestricted optimized feedback. This is more precise than saying zoRO has no mathematical analysis, and much weaker than claiming exact robust causal minimax. [P6, §§II–IV]

It remains **literature only under the current acados stop decision**. No zoRO experiment, acados retry, or tuning is proposed as executable work here.

### Sampling: justify only a separate probabilistic/heuristic track

Campi–Garatti scenario optimization [P8] provides probabilistic feasibility results for uncertain **convex** programs under its sampling and solution assumptions. A finite sampled experiment without that theorem's conditions establishes no all-disturbance guarantee. Repeated MPC solves additionally need a closed-loop probability/feasibility argument; a one-shot sample bound is not automatically an infinite-horizon guarantee. Sampling control sequences (as in MPPI-style search) is also different from sampling uncertain **constraints** in the scenario theorem. No sampling-MPC implementation was qualified here as a certified minimax comparator. Such a candidate is justified only if the owner explicitly wants a stochastic or heuristic track with separate outcomes, not as the first robust parity baseline.

## 4. Implementable tools: functionality, licenses, maintenance evidence

"Mature" here means documented interfaces, examples, and release or test evidence. This review did not install, test, or certify the tool. Pin mutable upstream pages to exact versions or commits before any separately authorized integration. The license notes below cover the named project. Audit dependencies, solver plugins, generated code, and distribution separately.

| Tool / primary evidence | Actual functionality and intended role | License and observed maturity limitations |
|---|---|---|
| **OSQP** [S1] | Convex PSD QPs with linear bounds; sparse ADMM, warm starts, code generation and C/C++ interfaces. Natural nominal QP or already-dualized/tightened robust-QP engine. Does not build a tube, enforce universal disturbance quantifiers automatically, solve finite action disjunctions, or return all minimizers. | Apache-2.0. Official release page exposes v1.0.0 and migration-relevant API/backend changes; maintained docs and releases are stronger evidence than popularity. Residual tolerances, inaccurate/max-iteration statuses and infeasibility certificates need independent interpretation; floating-point solver output is not an exact proof. |
| **HPIPM** [S2] | C interior-point engine for dense, OCP- and tree-structured convex QPs/QCQPs; BLASFEO dependency, condensing and language interfaces. Tree sparsity is useful for a separately built uncertainty tree, but the user still owns its nonanticipativity and objective. | BSD-2-Clause. Source/examples/interfaces are inspectable and used by acados. The inspected `Changelog.txt` stops at 2020, so it is inadequate evidence of current release freshness; inspect commit/test history when pinning. BLASFEO target/CPU mismatch can cause illegal instructions. No native control theorem or complete-family API follows from QP support. |
| **acados** [S3, P6] | C OCP/NLP framework, SQP/RTI, integrators, condensing, HPIPM and Python/MATLAB interfaces; zoRO extension is separate from nominal solving. "Multi-stage/multi-phase" in the general OCP docs does not by itself mean a nonanticipative uncertainty tree. | BSD-2-Clause core; dependencies separately licensed. Official docs show named Freiburg maintainers, CI links and a build dated 2026-10-22. Repository spike pinned v0.6.0; recorded native MSVC evidence is host/configuration-specific. **No further use authorized**; B04 max-iteration remains inconclusive, not repaired by this literature review. |
| **do-mpc** [S4] | Python/CasADi controller, simulator and MHE framework; robust multi-stage scenario trees. Shares decisions before branching and permits future recourse. Documented objective sums weighted scenario costs. Its docs explicitly say tube-based MPC is not currently implemented. | LGPL-v3 license text. Official releases show v5.1.2, CasADi compatibility fixes and testing; v5.1.0 adds integer variables/BONMIN and fixes multi-stage move-penalty scaling. Those changes make version pinning important. NLP/MINLP functionality is not a global certificate; MATLAB is not required, but CasADi/solver-stack licensing and numerical behavior still matter. |
| **MPT3** [S5] | MATLAB parametric optimization/polyhedral geometry, online-to-explicit MPC conversion, invariant-set tools, PWA/MLD models. Strong conceptual reference for geometric and explicit-policy tasks. | Official license page says **GPL**; it does not settle an exact version in the inspected text. MATLAB and optional optimization tools impose separate access/license constraints. The inspected home/control pages carry 2019/2013 timestamps: useful established functionality, but not proof of recent maintenance or current installation compatibility. Not a frictionless open native C++ dependency. |
| **Drake (optional)** [S7] | C++/Python `MathematicalProgram` and simulation/optimization ecosystem; useful later for nonlinear or mixed-integer formulations with explicitly selected solver. It is not a ready-made robust minimax policy synthesizer. | BSD-3-Clause core with dependency exceptions. Official docs explicitly distinguish open and commercial solvers and identify coverage gaps; the basic open branch-and-bound is described as suitable only for small problems. Active-development documentation is evidence, not a tested CSL adapter. Heavy framework/dependency footprint relative to a small QP reference. |
| **Author SLS-MPC code** [S6] | Inspectable reproduction/reference formulations and contemporary tube baselines; not a general supported solver library. | License permission unresolved; MATLAB/YALMIP/MPT3 plus default MOSEK prevent calling its supplied stack fully open-source. No deployment/maintenance qualification established. |
| **SCIP** [S8] | C/C++ MIP/MINLP engine, including mixed-integer quadratically constrained formulations. Candidate for one-hot finite-action or hybrid extensive forms; continuous robust norm/quadratic epigraph constraints need an appropriate formulation, not an ordinary OSQP QP. | Apache-2.0; official documentation identifies SCIP 10.1.0 and explains solver/build dependencies. No CSL build or adapter was tested. Numerical global bounds and termination gaps require independent interpretation; the numerical engine is not a complete-family or robust-controller implementation. |

**FORCESPRO excluded:** it is not an open-source comparator in this requested shortlist. No access, license, installation or execution assumption is made for it. A free academic entitlement, if available, would not be an open-source license. The same distinction excludes silently using MOSEK/Gurobi defaults to claim an entirely open stack.

### Candidate qualification register

The entries below make the issue's release/commit, dependency-stack, platform,
and maintenance questions explicit. “Documented” means an upstream source
states it; “unknown” means this research did not establish it. No row is a
qualified CSL dependency. Pin every transitive version and verify the exact
target toolchain before an adapter proposal or run.

| Candidate | Release/commit pin for a future review | Transitive solver stack identified by upstream evidence | Platform evidence and gap | Maintenance evidence and gap |
|---|---|---|---|---|
| OSQP | v1.0.0 is the inspected release candidate [S1]; not selected or installed | QDLDL is bundled with the default build; optional linear-system backends must be separately named and pinned [S1] | Official docs describe C builds/interfaces and shared-library loading for Linux, macOS, and Windows; exact compiler/architecture combinations still need CI qualification [OSQP platform docs](https://osqp.org/docs/get_started/linear_system_solvers.html) | Official release history, docs and tests are visible [S1]; exact maintenance cadence is not asserted |
| HPIPM | No immutable release/commit chosen; resolve before integration [S2] | BLASFEO is required; any adapter language/runtime and BLASFEO target configuration add to the stack [S2] | Repository build instructions exist, but this review did not establish a versioned OS/compiler support matrix; qualify each target directly | Source, examples and changelog are available; inspected changelog ends in 2020, so current release freshness/maintenance must be established from a pinned commit's CI/history |
| acados (literature/background only) | v0.6.0 / commit `503364817c872d474ab5bed219c26760ac267769` is the existing CSL spike pin [S3]; no execution authorized | HPIPM/BLASFEO and other configured integrators/interfaces must be captured from that exact build; the stack is not fully pinned by this dossier | Existing native MSVC evidence is host/configuration-specific; no general platform qualification is claimed | Official docs/CI and a 2026-10-22 build observation are recorded [S3]; this does not reopen the stop decision |
| do-mpc | v5.1.2 inspected release candidate [S4] | Python + CasADi plus the selected NLP/QP solver and its native libraries; the actual solver/backend must be pinned per run [S4] | Official installation docs provide a Python package path; this review did not verify an OS/Python/solver compatibility matrix | Official releases and tests are visible [S4]; no CSL compatibility or support commitment is inferred |
| MPT3 | No exact version/commit established by inspected pages [S5]; not ready for pinning | MATLAB and optional optimization solvers/toolboxes; exact solver/toolbox versions are task-dependent and unresolved | MATLAB release and supported OS/architecture matrix were not established here; record both for any proposed environment | Official pages provide feature and license descriptions but include 2013/2019 timestamps; current maintenance and compatibility remain unverified |
| Drake (optional) | No immutable release selected [S7] | MathematicalProgram backend is selected from Drake's solver integrations; pin Drake, solver, and all native dependencies together [S7] | Official solver docs identify solver availability, not a qualification of every solver/platform combination; select and verify a specific tuple | Official docs/source and ongoing development are visible [S7]; no CSL adapter or support guarantee is implied |
| Author SLS-MPC code | No release/tag; source branch is mutable [S6] | MATLAB, YALMIP, MPT3 and default MOSEK; versions and license permissions unresolved [S6] | MATLAB-dependent; no tested OS/version matrix found | No license, release, or maintenance commitment established in the inspected repository; research-code-only |
| SCIP | 10.1.0 documented version candidate [S8]; pin source/package and build options before integration | Build/plugin dependencies and optional LP/NLP backends need an explicit manifest; they were not fully enumerated in this review [S8] | Official docs describe interfaces/examples; an exact supported OS/compiler matrix was not established here | Versioned 10.1.0 documentation was generated 2026-09-25 [S8]; this is recent documentation evidence, not CSL build qualification |

The register intentionally records missing evidence instead of converting a
repository URL into a compatibility claim. Before selecting a row, attach the
exact upstream release/commit, lock or build manifest for the complete solver
stack, supported OS/architecture/compiler evidence, and dated maintenance
evidence (release, CI, or support policy). An `unknown` entry is a blocker to
integration qualification, not a blocker to this planning issue.

### do-mpc robustness is conditional on the tree

The official theory page guarantees satisfaction for the scenarios actually represented and discusses special linear-system extreme-value coverage. For a new adapter, prove the relevant affine/convex vertex or interpolation argument; do not generalize that statement to arbitrary nonlinear parameter uncertainty, hidden constant parameters, or arbitrary correlations. `N_robust < N` stops further branching and holds parameter values along the remaining branches: it does not enumerate every independently varying disturbance history to the horizon. A constant unknown parameter is likewise not interchangeable with an independently redrawn parameter; observation of state need not identify the branch's parameter. Scenario-weighted cost must be replaced by a justified worst-case epigraph formulation before making minimax claims, and that customization would require its own review. [S4]

## 5. Task matrix for this repository

The "next gate" column identifies research/contract work, not newly authorized implementation or runs.

| CSL task | Honest outside mapping | Next gate / prohibited inference |
|---|---|---|
| Nominal terminal optimization: reach/back versus direct joint | Same immutable affine LP/QP, same original terminal norm or justified squared form; OSQP/HPIPM are candidate engines | A one-witness solver cannot fulfill complete-family output. Preserve ties and flat-cost profiles. No acados pairing/retry. |
| Complete optimal families | Parametric/face geometry can inform an independent argmin representation; MPT3 is relevant research | Initial-state partition or one active-set solution does not certify every optimal history; requires value and family soundness/completeness evidence. |
| Finite-catalogue fixed-plan minimax, stage constraints | Exhaustive control plans against all declared disturbance histories, or a proven equivalent formulation | Existing #422 owns paired-record work; #3's active oracle work must not be duplicated. A continuous QP relaxation or feedback tree is not parity. |
| Causal finite-game safety | Explicit nonanticipative finite tree/backward winning sets | Current finite-feedback port is safety only; needs a separate cost/value contract before a causal minimax ranking. |
| Continuous full-state bounded-disturbance control | Tube MPC [P3], affine disturbance feedback [P5], later SLS-MPC [P7] | New policy, invariant/terminal-set and independent robust-checking contracts; closed #5 is not delivery evidence. Report restricted-policy conservatism and bound direction. |
| Temporal coupling, slew, total-resource constraints | Lift previous input/resource state or use explicit coupled linear constraints in a direct problem | Recheck lift equivalence, initial memory, robust/terminal invariance and policy timing. General program expressivity does not extend a stagewise proof. See [temporal-coupling research](temporal-coupling.md). |
| Mixed actions / hybrid modes | MPT3 PWA/MLD or explicitly encoded mixed-integer optimization; do-mpc integer support [S4–S5] | Finite action choices, integer variables and guard/reset hybrid dynamics differ. Fixed-mode-path optimization is not global mode search. Check relaxations, big-M bounds, solver global gap, reset/guard and robust branch semantics. |
| Nonlinear model or replay | do-mpc/Drake are formulation/simulation references; acados/zoRO literature only | Beyond initial comparison contract. Needs discretization, linearization-validity region and residual bounds; replay samples do not prove all-disturbance safety or continuous-time constraint satisfaction. |
| Noisy/partial observation and output feedback | MHE/EKF components in do-mpc are engineering references; explicit information-state/controller design remains separate | An estimator API is not a robust estimation-error enclosure or output-feedback minimax optimizer. Need measurement timing, uncertainty coupling, observability/information, estimator-error and closed-loop checks. State-feedback theorems cannot simply be inherited. |
| Sampled uncertainty or MPPI-style search | Separate stochastic/chance-constrained or heuristic track, if wanted [P8] | Not fixed-plan robust parity, not universal safety, not optimality evidence. No sampling-MPC package is selected by this note. |

## 6. Recommended decision sequence and evidence checklist

1. **Finish existing semantics/evidence paths first.** Reuse #422 and coordinate with #3 rather than opening replacement implementations. Specify one-plan versus policy versus full-family output for every future comparison row.
2. **For nominal outside references, assess OSQP and HPIPM independently of MPC branding.** A future approved proposal should identify exact supported cost/constraint classes, licenses, versions, non-success statuses and an independent checker. The existing acados stop remains binding.
3. **If extending robust control, begin with additive full-state tube and affine disturbance-feedback specifications.** They expose understandable policy restrictions, set operations and tractable optimization. Include offline preprocessing in accounting and retain unsupported or inconclusive outcomes. Do not add terminal/stage costs merely to make a classical theorem apply without labeling a new task.
4. **Add SLS-MPC as a contemporary research branch**, with its exact response identity, conservative uncertainty enclosure, upper-bound objective, shrinking-horizon/backup caveat and code-license/dependency blockers explicit. Investigate homothetic/parameterized tubes via [P7]'s primary bibliography after the rigid-tube contract; "newer" alone is not a selection criterion.
5. **Defer full scenario-tree, output-feedback, nonlinear and mixed/hybrid pairings** until information/domain/solver contracts match. do-mpc can inform the tree design, but weighted scenarios and shortened branching must not masquerade as all-history minimax.

Before any separately authorized experiment, freeze the model and time grid, initial-state information and quantifier, action domain, disturbance set and temporal coupling, observation timing, policy class, cost units and aggregation, every stage constraint, horizon and terminal design, solver and version, tolerances, offline and online allocation, and requested result object. Preserve B04 controls `[-1,1]`, L05 controls `[-0.3,0.3]`, and the finite B06/B07 control catalogues as distinct case definitions. Use the shared comparison contract's resource budgets. Record cold or warm starts, workspace reuse, worker and solver thread counts, repetitions, seeds, and whether memory limits were enforced or only observed. Separate setup and code-generation time from online controller time. Validate constraints against original data. Check robust soundness and minimax or optimality separately from witness replay. Preserve refusals, timeouts, and maximum-iteration failures. Follow the [published-results gates](../architecture/published-algorithm-results.md) and comparison contract. This note authorizes no execution or winner claim.

For each future adapter proposal, record release and package impact, optional
dependencies, and their license boundaries. If the selected task has a
supported two-dimensional case, include a labelled plot and the data needed to
recreate it.

## 7. Published tracker handoff

The companion issues below keep each future study separate. Check live tracker
state before starting work because assignments, labels, and dependencies change.
Native blocking dependencies preserve existing delivery ownership. No issue
authorizes benchmarks or overrides the acados stop decision.

| Issue | Scope |
|---|---|
| [#596](https://github.com/butahlecoq/controlled-systems-lab/issues/596) | External-result/evidence contract and roadmap; must not weaken complete-family APIs |
| [#597](https://github.com/butahlecoq/controlled-systems-lab/issues/597) | Nominal open-loop LP/QP/OCP reference, including unconstrained cases |
| [#598](https://github.com/butahlecoq/controlled-systems-lab/issues/598) | Stage and temporal constraints / exact memory lifts |
| [#599](https://github.com/butahlecoq/controlled-systems-lab/issues/599) | Equivalent finite fixed-plan minimax optimization and continuous-action relaxation bounds; extends #422 |
| [#600](https://github.com/butahlecoq/controlled-systems-lab/issues/600) | Executed full-state shrinking/receding-horizon loops |
| [#601](https://github.com/butahlecoq/controlled-systems-lab/issues/601) | Nonanticipative finite causal minimax trees and cost-policy contract |
| [#602](https://github.com/butahlecoq/controlled-systems-lab/issues/602) | Tube MPC, robust feasibility and set-representation conservatism |
| [#603](https://github.com/butahlecoq/controlled-systems-lab/issues/603) | Affine disturbance feedback and contemporary SLS-MPC assessment |
| [#604](https://github.com/butahlecoq/controlled-systems-lab/issues/604) | Explicit MPC, invariant/feasible sets and optimal-relation distinctions |
| [#605](https://github.com/butahlecoq/controlled-systems-lab/issues/605) | Partial/noisy observation and output-feedback studies |
| [#606](https://github.com/butahlecoq/controlled-systems-lab/issues/606) | Finite/mixed and hybrid planning versus mixed-integer formulations |
| [#607](https://github.com/butahlecoq/controlled-systems-lab/issues/607) | Nonlinear replay versus NMPC with separate model/guarantee identities |

The contract issue closes on its own reviewed contract, not completion of every
study; studies depend on that contract rather than creating a dependency cycle.
Existing #3/#422 own the global fixed-plan oracle/comparison, #73 owns temporal
support, #68 observation workflows, #76/#156 mixed/hybrid support, #83/#84 saved
comparison evidence, and #94/#99/#100 sweep/approximation infrastructure. Historical
restoration is not a blanket blocker for new shared synthetic cases.

## 8. Source register and reading limitations

### Primary papers

- **[P1]** D. Q. Mayne, J. B. Rawlings, C. V. Rao, P. O. M. Scokaert, *Constrained model predictive control: Stability and optimality*, Automatica 36(6), 789–814 (2000). DOI: <https://doi.org/10.1016/S0005-1098(99)00214-9>. Coauthor institution's abstract/bibliography inspected: <https://experts.illinois.edu/en/publications/constrained-model-predictive-control-stability-and-optimality/>. Publisher full text was not retrievable in this session; no new theorem-level audit claimed.
- **[P2]** A. Bemporad, M. Morari, V. Dua, E. N. Pistikopoulos, *The explicit linear quadratic regulator for constrained systems*, Automatica 38(1), 3–20 (2002). DOI: <https://doi.org/10.1016/S0005-1098(01)00174-1>. Author-hosted paper downloaded/text-read: <https://cse.lab.imtlucca.it/~bemporad/publications/papers/automatica-mpqp.pdf>. Any algorithm port must additionally check the publication's corrigendum and degeneracy assumptions; this note does not validate its region-enumeration implementation.
- **[P3]** D. Q. Mayne, M. M. Seron, S. V. Raković, *Robust model predictive control of constrained linear systems with bounded disturbances*, Automatica 41(2), 219–224 (2005). DOI: <https://doi.org/10.1016/j.automatica.2004.08.019>. Author institution: <https://openresearch.newcastle.edu.au/articles/journal_contribution/Robust_model_predictive_control_of_constrained_linear_systems_with_bounded_disturbances/29028086>. Metadata/abstract retrieved through <https://api.figshare.com/v2/articles/29028086>; deposited author PDF: <https://ndownloader.figshare.com/files/54426554>. PDF text encoding is damaged; the rendered example/conclusion page was inspected, and the institution's readable abstract supports the stability/QP claims. Not a complete independent proof audit.
- **[P4]** P. O. M. Scokaert, D. Q. Mayne, *Min-max feedback model predictive control for constrained linear systems*, IEEE Transactions on Automatic Control 43(8), 1136–1142 (1998). DOI: <https://doi.org/10.1109/9.704989>. Official record: <https://ieeexplore.ieee.org/document/704989>. Readable full text was not returned; [P5]'s author text also explicitly discusses this feedback formulation and its complexity. Bibliographic/conceptual use only here.
- **[P5]** P. J. Goulart, E. C. Kerrigan, J. M. Maciejowski, *Optimization over state feedback policies for robust control with constraints*, Automatica 42(4), 523–533 (2006). DOI: <https://doi.org/10.1016/j.automatica.2005.08.023>. Institutional record: <https://spiral.imperial.ac.uk/entities/publication/4e679e4b-2d5f-47bc-a3d0-95e9cf5a4882>. Author-version PDF downloaded/text-read: <https://spiral.imperial.ac.uk/server/api/core/bitstreams/62a4cf5a-e63a-4488-b4de-e5d0943f6c04/content>.
- **[P6]** J. Frey et al., *Efficient Zero-Order Robust Optimization for Real-Time Model Predictive Control with acados*, author preprint submitted 2023, ECC implementation work (2024): <https://arxiv.org/abs/2311.04557>; full text inspected: <https://arxiv.org/html/2311.04557v1>. Reproduction repository identified by paper: <https://github.com/FreyJo/zoro-NMPC-2021>. The paper's own timings are not measurements or ranking evidence for CSL.
- **[P7]** S. Chen, V. M. Preciado, M. Morari, N. Matni, *Robust model predictive control with polytopic model uncertainty through System Level Synthesis*, Automatica (2024); inspected author preprint: <https://arxiv.org/html/2203.11375v3>, especially §§3.1, 5.2–5.3 and Appendix A.3. Publisher record: <https://www.sciencedirect.com/science/article/abs/pii/S0005109823005988>. General SLS background linked by the authors: <https://arxiv.org/abs/1904.01634> (not independently theorem-audited here).
- **[P8]** M. C. Campi, S. Garatti, *The exact feasibility of randomized solutions of uncertain convex programs*, SIAM Journal on Optimization 19(3), 1211–1230 (2008). Author-hosted PDF downloaded/text-read: <https://garatti.faculty.polimi.it/Publications/Journals/2008_campi-garatti.pdf>. MPC-specific author chapter for follow-up: <https://marco-campi.unibs.it/pdf-pszip/Handbook%20MPC.pdf> (discovered, not fully read).

### Official software/documentation

- **[S1] OSQP:** <https://osqp.org/docs/>; source <https://github.com/osqp/osqp>; inspected release history <https://github.com/osqp/osqp/releases>. Official docs state Apache-2.0 and the supported QP form. Reference version candidate: <https://github.com/osqp/osqp/releases/tag/v1.0.0>, not installed here.
- **[S2] HPIPM:** <https://github.com/giaf/hpipm>; license <https://raw.githubusercontent.com/giaf/hpipm/master/LICENSE.txt>; historical changelog <https://raw.githubusercontent.com/giaf/hpipm/master/Changelog.txt>. Framework paper linked by maintainers: <https://arxiv.org/abs/2003.02547>. README, license and changelog inspected; no fresh upstream build/CI qualification performed.
- **[S3] acados:** <https://docs.acados.org/>; <https://github.com/acados/acados>; license <https://raw.githubusercontent.com/acados/acados/main/LICENSE>. Existing CSL cross-check pins <https://github.com/acados/acados/releases/tag/v0.6.0> / commit `503364817c872d474ab5bed219c26760ac267769`. Current documentation observations do not amend the owner execution prohibition.
- **[S4] do-mpc:** theory <https://www.do-mpc.com/en/latest/theory_mpc.html>; repository <https://github.com/do-mpc/do-mpc>; release notes <https://github.com/do-mpc/do-mpc/releases>; license <https://raw.githubusercontent.com/do-mpc/do-mpc/master/LICENSE.txt>; maintainer/stack description <https://raw.githubusercontent.com/do-mpc/do-mpc/master/README.md>. Version-specific source candidates: <https://github.com/do-mpc/do-mpc/releases/tag/v5.1.2> and <https://github.com/do-mpc/do-mpc/releases/tag/v5.1.0>. Release evidence is not an integration test.
- **[S5] MPT3:** <https://www.mpt3.org/>; license <https://www.mpt3.org/Main/License>; MPC <https://www.mpt3.org/UI/Control>; hybrid models <https://www.mpt3.org/UI/Systems>. These pages were inspected. Detailed filters page fetch timed out; no claim of exhaustive current feature support follows.
- **[S6] Author SLS-MPC implementation:** <https://github.com/ShaoruChen/Polytopic-SLSMPC>; README <https://raw.githubusercontent.com/ShaoruChen/Polytopic-SLSMPC/main/README.md>. Root listing and README inspected; no license displayed, no usable release/maintenance guarantee established. Its claimed experimental coverage is not adopted as a general method ranking.
- **[S7] Drake:** solver coverage <https://drake.mit.edu/doxygen_cxx/group__solvers.html>; source <https://github.com/RobotLocomotion/drake>; license <https://raw.githubusercontent.com/RobotLocomotion/drake/master/LICENSE.TXT>. Solver documentation and license inspected; no Drake MPC integration or benchmark performed.
- **[S8] SCIP:** official problem classes and C/C++ examples/interfaces <https://www.scipopt.org/doc/html/WHATPROBLEMS.php>; Apache-2.0 text <https://www.scipopt.org/doc/html/LICENSE.php>. Both pages inspected by the parent session; the documentation identifies version 10.1.0 and is generated 2026-09-25. Build/plugin dependencies must be pinned separately. No solver was installed or executed.

GitHub REST metadata fetches did not yield usable repository/release metadata through the generic HTTP route in this session. Accordingly, no exact "last commit" date, release cadence or unsupported maintenance assertion is inferred from those calls. Official visible release notes/docs provide the bounded evidence stated above. Public availability of a paper is not permission to redistribute it or its implementation; downloaded reading copies remained outside the repository.
