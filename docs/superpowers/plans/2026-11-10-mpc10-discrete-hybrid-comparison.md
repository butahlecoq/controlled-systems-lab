# MPC-10 finite, mixed and hybrid comparison

Continue #606 from main 0ba04946. Live prerequisites #596/#83/#76/#156 are
closed; the current user authorization includes benchmark execution. Reuse
public finite/mixed and hybrid portfolio/path APIs, not a second CSL solver.

## Products and mathematical boundary

Keep three authored products: finite actions in one affine model, continuous
plus finite actions in one affine model, and explicit mode/edge automata.
Start with the supported two-dimensional hybrid example: initial (-1,0),
source flow (x+u,y), u=1, explicit switch edge with identity reset, terminal
(0,0) and linear x objective. Extend bounded short horizons with parallel
edges, nontrivial guards/resets and forbidden/worse terminal branches. Every
fixture records initial, pre-reset and post-reset invariant timing explicitly.
Dimension-changing and general relational resets remain unsupported by this
external encoding unless separately proved.

The independent formulation uses mode/edge one-hot variables, exact adjacency
and linear indicator rows for flow, source invariant, guard, functional reset,
destination invariant and mode-specific terminal costs. Encode an equality as
two inequalities. Native indicators avoid guessed big-M constants. If a
relaxation is included, derive every finite row bound from authored variable
bounds and label it a relaxation. Check T=0 without synthetic transitions.

Enumerate all bounded short discrete histories independently. Exact rational
branch oracles/checks establish feasibility, objective and tied branch identity;
SCIP incumbent/best bound/gap remain numerical observations. Recovering one
incumbent does not prove complete continuous-family parity. Compare actual CSL
branch-labelled families only in their admitted scope, preserving refusals.

## Software and evidence

The existing optional environment reports PySCIPOpt 6.3.0 / SCIP 10.0.2; no
installation is needed. Recheck executable/package hashes, source provenance,
licenses and available parameters before capture. The versioned official
[PySCIPOpt API](https://pyscipopt.readthedocs.io/en/v6.3.0/api/model.html)
specifies linear inequalities for addConsIndicator; the
[SCIP constraint-handler reference](https://scipopt.org/scip/doc-10.0.2/html/group__CONSHDLRS.php)
describes the corresponding native indicator interface. This is an independent
encoding inspired by the classical mixed-logical-dynamical formulation, not an
adoption of author MATLAB code or a general hybrid-game solver.

1. Build the authored fixtures and independent exact oracle with boundary tests.
2. Exercise public CSL construction/solve through a small optional consumer;
   retain branch relations, witnesses, objective bounds and exact model identity.
3. Run bounded SCIP indicator formulations and compare branch feasibility,
   values and ties. Include failed guards, source/destination invariants,
   parallel edges, empty/all-infeasible, T=0 and interrupted-search outcomes.
4. Capture initial dimension/horizon/branch-budget points and retain every raw
   failure. Separate enumeration/formulation/setup/solve/check intervals,
   variable/constraint/path counts and process CPU/RSS. Make no causal timing
   ranking without repeated matched measurements and limiter evidence.
5. Generate a labelled two-dimensional mode/edge trajectory and branch diagram
   from saved records with the shared plot style. Bind all data/source identities.
6. Independent exact-head reviews, current CI, dependency/platform/release
   disposition and managed Pages/live verification precede issue closure.

No new core API or required library dependency is planned. Optional report
consumers require no library release. No acados execution, MATLAB purchase or
unlicensed source adoption. Shared publication integration remains root-owned.

## Bounded publication follow-up

Stage a unique report/gallery hook without editing root-owned shared integration.
Preserve comparison-525871ea byte-for-byte. Add a separately versioned current
checker/metrics receipt after the source-binding correction, validate it before
publication, and reuse the two saved figures. Include all26 complete fixture
inputs, counts, actual proof/refusal statuses and descriptive cost scopes.
Export the minimal authentic Git objects required by capture/current helper
checks, selecting a stable last-helper-touch first-parent commit. The complete
ZIP must check outside a checkout: Python/Git for source/receipt/metrics binding,
and the existing qualified PySCIPOpt environment for full saved oracle/model
rechecking without optimization. Test forgery, renewed empty receipt inventories,
unsafe archives, unrelated commits/merged helper changes, and failure before site
writes. Review/CI/main-only staging/live hash inspection remain separate gates.
