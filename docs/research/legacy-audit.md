# Legacy implementation audit

Date: 2026-10-11. This records source inspection and isolated characterization, not repaired code or reproduced full experiments.

## Executed checks

[Machine-readable results](legacy-characterization.json) were produced with NumPy 2.3.2 and SciPy 1.16.3. The [characterization script](tools/characterize_legacy.py) loads selected function/class definitions through the AST to avoid executing top-level demonstrations. Prepared polytope data in the cost test bypasses unrelated H/V construction. These checks establish the listed local behavior, not reliability of the entire solver.

| Check | Observation | Consequence |
|---|---|---|
| L28 uniform grid, four-state fuel model, 11 steps over 100 s | Initial state (1192.5,119500,454,45300); zero-control next state (1192.5,-10840.9091,454,-4127.2727); matrix rank 2 | Mass diagonal is zero. Expected masses from the article recurrence are 108659.0909 and 41172.7273 |
| L28 explicit switching times | Matrix diagonal (1,1,1,1), rank 4 | The two grid branches do not implement the same mass update |
| L19 worst-case oracle, positive convex cost (x-1)^2 on [0,2] | Returns -0.0; true maximum at vertices is 1 | Function minimizes the supplied cost and negates the value; this is not the stated maximization |
| L26 parsed under Python 3 | SyntaxError at line 17 | Source includes Python 2 print syntax |
| L16 loaded as isolated reusable definitions | NameError for global T | Hidden horizon dependency; not proof that the original demonstration lacks T |
| L19 two actions, two steps | Four Cartesian control sequences | Enumeration works on this tiny case; counts grow to 2^16=65536 and 9^16=1853020188851841 |

Even if a caller supplied a negative cost to L19, a local solve of a nonconvex minimization would not establish the global worst-case value. Complete vertex evaluation or another justified global oracle is required.

## Static source findings

| Artifact and location | Finding | Status |
|---|---|---|
| L26 ReachableSet | Reads global U despite U1 argument; backward construction changes B and explicitly inverts A | Source finding; quantify impact in a restored environment |
| L26/L19 custom simplex and double description | Fixed tolerances, randomized basis selection; limited degeneracy/status handling; L19 simplex uses float32 | Numerical robustness risk; not a proven failure for every input |
| L19 feasible_actions, line 18 | Materializes a Cartesian product of all action sequences | Confirmed design bottleneck |
| L19 reachable_set, line 35 | Full fixed-plan propagation with containment checking; disturbance vertices supplied as one V1 | Good robust-feasibility intent, but general time-dependent uncertainty is not explicit |
| L19 optimize_on_rs, line 246 | No demonstrated global certificate or systematic solver success/residual checks | Requires replacement or repair before baseline acceptance |
| L19 minimax_openloop_control, line 4 | NaN scoring and nanargmin can fail when no plan is feasible | Explicit infeasible-result contract needed |
| L28 LinearSystem, line 13 | Specialized physical fitting; scalar/vector branches write control terms to different state indices | Semantic inconsistency to investigate; no universal bug claim for every intended convention |
| L16 ClosedLoopControl, line 5 | Depends on globals and absent standalone OpenLoopControl module | Full historical run not reconstructed |
| L14 PDF listing | Possible unbound time symbol in Snatch; indentation and formatting are extraction-sensitive | Verify against original editable source before classifying as an executable defect |
| L22–L24 | Hash-identical to L16–L18 | Missing distinct minimax adaptive implementation despite folder label |

Definitions and line positions are recorded in the JSON. Original source paths are in [source map](source-map.md); raw text is local-only in docs/research/extracted.

## Separation of scientific method and listing

The minimax formulation can be mathematically meaningful while a particular listing implements its inner optimization incorrectly. A successful numerical trajectory does not validate an exhaustive worst-case oracle. Conversely, an obsolete Python syntax issue says little about the underlying mathematics.

The report's modified reachability procedures should be assessed individually. L05 reports different output volumes; L07 reports acceleration on particular samples. Neither establishes universal modern performance or a uniform inclusion guarantee for every modification.

## Restoration policy proposed for later implementation

Keep original hashes and original results immutable. Maintain separate historical reproduction and corrected implementation tracks. Each correction should identify the source equation, changed behavior, resulting baseline difference, and verification evidence.

Replace incidental globals with explicit problem data. Isolate numerical backends from domain physics, plotting, file handling, and closed-loop execution. Use established LP/QP/conic/H/V libraries where suitable, retaining the historical algorithms for research comparison rather than making them the sole trusted backend.

Before public redistribution of the originals, establish the intended release scope and ownership of articles and registered listings. A public review repository can initially contain the new English research documentation without redistributing source files.
