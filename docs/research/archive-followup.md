# Follow-up search of the larger PhD archive

Date: 2026-10-11. Requested location: D:/work/PhD/PhD. Search purpose: recover B04 experiment inputs and missing algorithm sources. This is a targeted follow-up, not a claim to have read all archive contents.

A recursive file-name scan found 8,982 files, including bundled dependencies, saved web pages, teaching material and scientific sources. A path-based filter retained 175 non-library .m/.py/.pas source candidates for numeric/model searches; this is a heuristic, not an authorship determination. Four nominal article PDFs and ten relevant legacy Word documents were extracted locally. Selected MATLAB scripts were read; saved MATLAB variable tables were inspected with SciPy. Original code was not executed.

The [selected-source register](archive-selected-sources.json) assigns A01–A23, relative archive paths and SHA-256 hashes. These IDs supplement the original L01–L31 inventory, which remains unchanged. Raw originals, full directory listings, extracted text and administrative documents are not added to the public repository.

## What was recovered

| Sources | Finding | Consequence |
|---|---|---|
| A11–A14 | B04 Word tables, additional PDF drafts, and a byte-identical L11 copy | Tables are now available locally; drafts retain the displayed model/result discrepancy |
| A01 | Nominal forward/backward fuel-control example, state constraints and continuous interval [-1,1] | A useful separate candidate scenario, with T=12, different initial state and B |
| A02–A03 | T=16 adaptive driver and OpenLoopControl.m | Recover the algorithm pipeline, but do not substitute its inputs/objective for B04 |
| A08–A10 | Distinct minimax adaptive implementation and saved results.mat | The previously missing workflow exists in MATLAB; its numerical version is not yet matched to B09 |
| A04, A21–A22 | Zonotope experiment, local paper p13.pdf and editable English paper source | The owner's zonotope publication is now located locally, supplementing R29 |
| A05, A23 | Ellipsoidal-enclosure example and study notes | Confirm historical interest/use; the executable ellipsoidal library dependency was not located in the scanned tree |
| A06–A07 | 1,076-line Pascal module and MATLAB variant | Preserve older algorithm interfaces for a later comparison; missing Pascal dependencies are not assumed recovered |
| A15–A20 | Hull/simplex routines, conversion adapters, transition calculation and a six-state orbital example | More replaceable algorithm seams and a second application beyond fuel management |

## B04: source gaps narrowed, canonical project still unresolved

The recovered tables document the same linear terminal point and reported cost as L11/R40. Article revisions show the same displayed A, B and initial state. Recovery therefore corroborates the transcription rather than repairing the invariant contradiction in the [B04 audit](b04-restoration.md).

A01 has initial state (1220.3,119500,440,45300), T=12, B=(2208/110,0,-1152/110,0), continuous interval [-1,1], the familiar flow bounds, and a synchronization term in the squared objective. This is distinct from B04.

A02 also declares T=16 and [-1,1], but computes the initial flows from a nonlinear model with a different initial mixture error and uses that same different B. A03's terminal objective omits the synchronization term; A02's reporting expressions multiply that term by zero. The nonlinear driver accumulates control increments. Those details must be explicit in any future scenario; they are not evidence that B04's canonical data have been recovered.

No matching B04 numerical source was found in the searched loose code, inspected workspaces or selected ZIP contents. This is not proof of absence from all compressed archives or embedded Office/Simulink objects. Legacy Word extraction does not decode Equation Editor objects. Several RAR package directories were listed read-only; a complete extraction/audit of every archive was not performed.

## Adaptive minimax: useful new evidence, with version limits

A08 is a genuine distinct Minmaxclosedloop.m, rather than the optimal adaptive Python file duplicated in the earlier supplied folder. It uses nine finite actions over four steps. A09 explicitly includes the synchronization residual (2.5*x4-x2)^2 in the terminal norm. This identifies a concrete implementation difference from L13's printed plain Euclidean criterion.

For the displayed B09 original adaptive state (60,20.3,24,4.5), the plain norm is 20.792787211; adding that residual gives 22.676915575, near the reported 22.657. This suggests a criterion convention behind the discrepancy; it is not an exact reproduction from rounded coordinates. A08's nonlinear reporting formulas also contain an unsquared fuel-flow deviation, while A09 squares it. Treat that as a code-review concern, not a correction applied silently.

A09 uses a local nonlinear solve of a negated convex objective, but also checks every retained terminal vertex and replaces the value when the vertex result exceeds it by eps. This safeguard distinguishes it from the audited Python minimax routine. The vertex comparison uses eps without an explicit tolerance argument; tolerance handling and standalone execution/edge cases still need checking. Do not transfer the Python oracle characterization wholesale to this MATLAB version or claim a complete validated certificate.

The saved A10 workspace contains A with 75-second stock integration, B approximately (1.064285714,0,-0.534285714,0), and X0 approximately (59.437493249,18100,24.260201326,7150). Saved adaptive controls are (0.75,0.75,-0.5,-0.5); initial open-loop controls are (0.75,1,-1,0.25). The final saved adaptive stocks are about (14.589974321,3.250299380), differing from the published (20.3,4.5). This is valuable run evidence, not the canonical published run.

## Architectural implications and next source work

Keep separate ports for forward reachability, predecessor construction, terminal optimization, witness recovery, hull reduction, representation conversion, LTV discretization and approximation. Several independently saved implementations now support comparison of these boundaries before product implementation.

The zonotope script mixes propagation, generator reduction and visualization. Its reduction branch contains a two-dimensional construction while the active example is three-dimensional; it requires review before reuse. The ellipsoidal script encloses polytope vertices and references external functions such as ell_enclose; do not label its output an exact reachable-set implementation.

Next priorities: identify a B04-matching driver/run; audit saved objective versions against publication rows; extract coherent dependency graphs from the recovered algorithms; review the local zonotope source and older Pascal assumptions. Public artifacts should continue to separate historical versions, independently verified claims and corrected scenarios.
