# Research utilities

These scripts support archival analysis and independent numerical checks. They do not select the product language or implement the proposed general library.

Run from the repository root using a Python environment with PyMuPDF, NumPy and SciPy. The assessment environment used NumPy 2.3.2 and SciPy 1.16.3; a complete environment lock has not been recovered.

~~~text
python docs/research/tools/extract_archive.py
python docs/research/tools/extract_legacy_word.py
python docs/research/tools/characterize_legacy.py
python docs/research/tools/reference_b08.py
python docs/research/tools/check_b04.py
~~~

The first three require the local original papers and registration folders in their inventory paths. They are intentionally excluded from the public repository. Run both extraction scripts in order: the first handles PDFs/DOCX/source text; the second updates legacy Word entries with piece-table text. Extraction regenerates the inventory and raw text and should be run only when refreshing the source register intentionally.

Legacy Word recovery does not decode embedded Equation Editor objects or figures. PDF/DOCX extraction is not a faithful reconstruction of every formula.

The characterization script executes selected archived definitions, bypassing demonstration code, and writes legacy-characterization.json. The B08 reference is independent of archived Python source: it uses the transcribed four-step linear model, enumerates all finite controls and disturbance-box corner images, and writes reference-b08.json. It is a floating-point reference, not a validated rounding proof, nonlinear simulation or historical timing reproduction.

The [B08 displayed-data exact audit](../b08-displayed-exact-audit.md) adds an independent standard-library rational reference for those **printed** coefficients and action bounds. Run `python -B -O docs/research/tools/check_b08_displayed_exact.py --verify-record docs/research/evidence/b08-displayed-exact.json`. Its exact squared value and three minimizers are checked against literals, including under optimized Python; the saved record is recomputed and compared. It does not alter the older NumPy artifact or claim the unpublished MATLAB arrays.

The [L13 displayed-decimal criterion audit](../l13-displayed-criterion-audit.md) computes the printed Euclidean and A09 synchronization-augmented squared norms for all four non-reference Table 2 states with exact fractions. Run `python -B -O docs/research/tools/check_l13_displayed_criteria.py` and `python -B -O docs/research/tools/test_l13_displayed_criteria.py`. The literal tests check all four reported rows and an independent input. The A09 formula is a candidate comparison, not a reconstruction of the published run.

The [L13 rounding-box audit](../l13-rounding-box-audit.md) uses exact fractions to exclude the printed Eq. (16) Euclidean cost for all four Table 2 rows under nearest-decimal coordinate and criterion rounding, and supplies one in-box witness per row for compatibility with the A09-style candidate. Run `python -B -O -m docs.research.tools.check_l13_rounding_boxes` and `python -B -O -m unittest docs.research.tools.test_l13_rounding_boxes`. Optional `--l13-pdf` and `--a09-source` must be supplied together to hash-check the private originals before the same arithmetic. Compatibility does not establish a generating source or nonlinear reproduction.

The [A10 saved-workspace criterion trace](../l13-a10-saved-criterion-trace.md) checks a distinct, hash-identified private MAT file against the A08 reporting expression, A09 candidate, and L13 Eq. (16). Public tests run with an explicit private-source skip: `python -B -O docs/research/tools/test_l13_a10_saved_criterion.py`. Supply `--archive-root` to that test and to `check_l13_a10_saved_criterion.py` for a local read-only MAT check; NumPy and SciPy are then required. The saved workspace is not matched to L13's printed rows.

~~~text
python docs/research/tools/verify_docs.py
~~~

The B04 consistency utility uses only Python standard-library rational arithmetic. It reads the historical manifest, checks terminal invariants and computes an unrestricted terminal-plane lower bound; it does not solve missing historical constraints. Results are in [b04-consistency.json](../b04-consistency.json).

The [B04 parameter cross-check](../b04-parameter-crosswalk.md) uses `check_b04_parameter_crosswalk.py` to compare the published nonlinear law, displayed linear initial data, and the separately saved kernel with exact rational arithmetic. Run `python -B docs/research/tools/check_b04_parameter_crosswalk.py` and `python -B -m unittest docs.research.tools.test_b04_parameter_crosswalk`. It neither loads private originals nor reconstructs the historical T=16 run.

The verification utility checks document links, original hashes where originals exist, inventory coverage, Python syntax, and reference JSON consistency. It is documentation/research verification, not a product test suite.

The [L05 saved-figure checker](check_l05_saved_figures.py) requires SciPy only to read two hash-identified private MATLAB FIG files. Its hull, area and inclusion calculations are exact for the stored binary64 vertices. Run `python -B -O docs/research/tools/check_l05_saved_figures.py --figure "$privateL05/4.fig" --companion "$privateL05/1.fig"` and `python -B -O -m unittest docs.research.tools.test_l05_saved_figures -v`. The checked-in [summary record](../evidence/l05-saved-figures.json) contains no private plot coordinates or historical timing claim.

The [L05 linear zonotope checker](check_l05_linear_zonotope.py) uses the same private `4.fig` plus the hash-identified `Volterra.m` candidate. Run `python -B -O -m docs.research.tools.check_l05_linear_zonotope --source "$privateL05/Volterra.m" --figure "$privateL05/4.fig"` and `python -B -O -m unittest docs.research.tools.test_l05_linear_zonotope -v`. Its [derived record](../evidence/l05-linear-zonotope.json) compares all 60 candidate linear stages and reports exact inclusion checks on saved plotted hulls without exposing vertices or claiming historical generator identity.

The [L05 four-state candidate checker](check_l05_dim4_candidate.py) hash-gates private `Dim4.m` and `2.1.fig`–`2.3.fig`, enumerates all seven-stage control corners and compares the candidate's 4D hull rows and saved 3D projections. Run `python -B -O -m docs.research.tools.check_l05_dim4_candidate --source "$privateL05/Dim4.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"`; the [derived record](../evidence/l05-dim4-candidate.json) contains no source vertices. The modified 4D row and generating revision are not recovered.

The [L05 four-state active-filter checker](check_l05_dim4_retention.py) additionally hash-gates `ConvSM_mod.m` and `Simplex_Hull_mod.m` and replays their ordered floating pivot/filter operations. Run `python -B -O -m docs.research.tools.check_l05_dim4_retention --source "$privateL05/Dim4.m" --convsm "$privateL05/ConvSM_mod.m" --simplex "$privateL05/Simplex_Hull_mod.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"` and `python -B -O -m unittest docs.research.tools.test_l05_dim4_retention -v`. Its [derived record](../evidence/l05-dim4-retention.json) distinguishes the active full 4D hull from the smaller saved linear projections without recovering the printed modified row or claiming a MATLAB run.

The [L05 four-state commented-reduction checker](check_l05_dim4_approx.py) hash-gates `Approx_mod.m` too and tests its `dS=0.001` call after each active hull filter. Run `python -B -O -m docs.research.tools.check_l05_dim4_approx --source "$privateL05/Dim4.m" --convsm "$privateL05/ConvSM_mod.m" --simplex "$privateL05/Simplex_Hull_mod.m" --approx "$privateL05/Approx_mod.m" --figure-123 "$privateL05/2.1.fig" --figure-234 "$privateL05/2.2.fig" --figure-124 "$privateL05/2.3.fig"` and `python -B -O -m unittest docs.research.tools.test_l05_dim4_approx -v`. The [aggregate record](../evidence/l05-dim4-approx.json) documents its mismatch with the printed modified 4D row and saved 3D linear patches. This is a translated, commented-path hypothesis, not a recovered MATLAB run.

## B04 saved-witness reference check

[check_b04_saved_witnesses.py](check_b04_saved_witnesses.py) reproduces the [curated B04 witness/replay checks](../b04-saved-witnesses.md). It requires Python 3, NumPy and SciPy (`loadmat` with `simplify_cells`); the recorded run used Python 3.13.5, NumPy 2.3.2 and SciPy 1.16.3. PyMuPDF, MATLAB, a solver and archived executable code are not required. These are documented dependencies and observed versions, not new project dependency pins.

Supply each private original explicitly. The following PowerShell example assumes you set `$privateB04` to the directory containing your registered originals, and `$checkOutput` to a separate writable JSON destination:

~~~powershell
python -O docs/research/tools/check_b04_saved_witnesses.py --figure "$privateB04/1st.fig" --kernel "$privateB04/program.m" --driver "$privateB04/ReachableSets.m" --article "$privateB04/Shorikov_Kalev_Article_v4.pdf" --image "$privateB04/1st.png" --output "$checkOutput"
~~~

The three mandatory flags verify A39 (FIG), A40 (kernel) and A01 (driver) against registered SHA-256 and byte counts. Optional `--article` and `--image` add A41/A42 identity checks; neither redoes the prior visual audit. Sources are read only, and an output path that aliases an input is rejected. The private path is never included in successful JSON. Omit `--output` to print JSON to stdout. Output contains source IDs/hashes, aggregate checks, endpoints, objectives, rounding-box results, replay events and environment versions. It contains no full trajectory/action arrays. All seven relevant saved histories are read directly from fixed graphics anchors.

Exit 0 means all declared witness/replay checks passed, including detection of the frozen discrepancy; it does not mean full historical reproduction. Exit 1 means a numerical check failed (inspect the JSON `checks` object). Exit 2 reports missing/changed sources, unavailable dependencies or invalid input/output. Checks remain active under `python -O`. The archived kernel is implemented as authored Python formulas after source identity verification, not executed or dynamically translated. The [evidence JSON](../evidence/b04-saved-witnesses.json) records derivations, source anchors, regression tolerances and a five-source run's aggregate output. Regeneration produces the `observed_checks` portion; editorial provenance/conventions remain authored separately.

Run public boundary tests without private files:

~~~text
python docs/research/tools/test_b04_saved_witnesses.py
~~~

That command tests actionable missing-source errors, integrity rejection and input preservation, and explicitly **skips archival numerical reproduction**. To execute all tests against the originals:

~~~powershell
python docs/research/tools/test_b04_saved_witnesses.py --figure "$privateB04/1st.fig" --kernel "$privateB04/program.m" --driver "$privateB04/ReachableSets.m"
~~~

The tests run the checker subprocess under optimized Python and compare actual computed values with literals from the prior independent audit. They do not validate complete stage feasibility, constrained optimality, full families, frozen-controller generation or a corrected 100-second replay. No full archive search or native rebuild is needed for this focused reference utility.

## Proof-audit literal reference checks

The separate [finite policy-class reference](../finite-policy-class-reference.md) uses standard-library exact rational arithmetic to enumerate the reviewed two-step counterexample's fixed plans, remaining-plan replanning, executed whole-history costs and globally causal recursion. Run `python -B -O docs/research/tools/test_finite_policy_classes.py`; its seven behavioral checks include the strict causal gap, strict replanning improvement in a second scalar fixture, interior disturbance, current-action timing, whole-successor safety and nominal equality. Its finite catalogues are audit examples, not continuous or historical solvers.

[check_proof_counterexamples.py](check_proof_counterexamples.py) requires Python 3 and its standard library only. It needs no private source, product solver or numeric package and writes no files.

~~~text
python -O docs/research/tools/check_proof_counterexamples.py
python -O docs/research/tools/verify_docs.py
~~~

The checker prints nine named passes for exact rational hull/clipping, support-gap, nonlinear endpoint and finite-action policy examples in the [reachability](../reachability-proof-audit.md) and [adaptive-policy](../adaptive-policy-proof-audit.md) reports. A failed comparison raises an error and returns a nonzero exit code even under optimized Python. Squared costs avoid irrational floating arithmetic. The continuum bounds, causal lower bound and tie analysis remain analytical proofs in the reports; checking finitely many literal points is not sampling-based certification.

The documentation verifier also checks registered source/hash and anchor references, the ordered antecedent version/review disposition chains, report-section targets, and consistency with all 18 public literal checks in schema-2 [proof provenance](../proof-audit-provenance.json). It does not recover missing sources or re-audit the proofs. As before, it writes `docs/research/verification.json`; retain that generated snapshot only when intentionally publishing it.

## Temporal-lift reference and provenance checks

[check_temporal_lift.py](check_temporal_lift.py) uses Python 3 and the standard library only. It runs nine exact rational checks from the [reviewed temporal audit](../temporal-lift-source-audit.md), writes no files, and executes no archived code or optimizer:

~~~text
python -B -O docs/research/tools/check_temporal_lift.py
python -B -O docs/research/tools/test_temporal_lift.py
~~~

The literals cover both affine LTV transitions, inverse recovery, the no-first-slew convention, changing absolute-input bounds, positive elapsed-time rate scaling, the fixed-one homogeneous slice, uncoupled recurrence error, terminal memory fibres, marginal-coverage insufficiency and four-state embedding. Analytic proofs own the continuous-history statements; finite reference checks are not full-family certification.

The ten focused tests execute the optimized checker, reject an injected arithmetic error under `-O`, validate all three provenance chains, test LF/CRLF report identity, and reject content tampering, stale hashes, missing hash coverage, unsupported digest conventions, invalid code extensions and corrupted source/review/reference records. Corruptions affect deep-copied in-memory data only. The test loads the verifier's imports and validator definition through its AST so the snapshot-writing script entrypoint never runs during negative tests. Reports are never edited for a rejection test.

Schema 2 retains the existing source IDs, anchors and review/fix/recheck records. It adds registered Python/Pascal line anchors, the nonblocking `clarification_requested` disposition, and a separate public-report digest map. The required `utf8-lf` convention hashes curated UTF-8 reports with CRLF/CR normalized to LF, matching committed LF blobs across platform checkouts. Original-source, navigation-extract and private antecedent/review digests remain raw byte identities. A matching public-report hash proves identity only. The provenance file and generated verification snapshot have no self-hash; updating a curated report requires refreshing its explicit digest.
