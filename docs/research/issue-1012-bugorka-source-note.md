# Issue #1012: source note for the four-state scalar-control example

## Source identity and copy check

The user-supplied paper is V. V. Bulaev, A. Yu. Goranov, and V. I. Kalev, “The Optimal Open-Loop Control Construction of Complex Mechanical Plants Motion,” *Bulletin of the South Ural State University. Ser. Computer Technologies, Automatic Control, Radio Electronics*, 17(4), 20–28 (2017), DOI [10.14529/ctcr170403](https://doi.org/10.14529/ctcr170403). The journal’s [article record](https://vestnik.susu.ru/ctcr/article/view/6924) links the [publisher PDF](https://vestnik.susu.ru/ctcr/article/download/6924/5803). This publisher PDF is the primary publication and the authority for the published example below.

The supplied files are not two revisions of one article. I extracted their text with LibreOffice 26.8.1.1; the NPOA file title/abstract match the publisher fuel-control paper, while the UralENIN file is a different paper titled “Modification of the General Recursion Algebraic Method of the Linear Control Systems Reachable Sets Computation,” with a different abstract and sections 1–4. The equation-level contents were not compared: text extraction omits embedded equation objects, so this does not establish whether any model equations recur in both files. Hashes:

- `Статья бугорка.doc` under `НПОА 2017`: SHA-256 `a8ed876c8a34d4eb798c031c6ede02a662e771b73cbead65cc42be8ff6132dc0` (19 pages per OLE metadata; title/abstract match confirmed by LibreOffice text extraction).
- `Статья бугорка.doc` under `УралЭНИН 2017`: SHA-256 `565ae84cf2c2661df47ce98a7a3d6c2ffa5cc9f220bf81a54f3b8a64c73a1c2a` (14 pages per OLE metadata; different title/abstract/section structure confirmed by LibreOffice text extraction).

The NPOA `.doc` is the matching supplied source; the UralENIN `.doc` is a separate article, not a counterpart revision. The publisher PDF is authoritative for what was published. The initial state and printed terminal result below follow the PDF. The normalized vector is suitable for an explicitly article-derived scaled case; reproducing the local Word draft additionally requires checking its embedded equation objects.

## Published example: source-stated model

The paper’s final numerical example is §4, “Численный пример” (“Numerical example”), journal pp. 23–25 (publisher-PDF pages 4–6, counting the first article page as PDF p. 1). It explicitly concerns terminal control of fuel consumption of the third stage of a launch vehicle. Equation (1), §1, p. 20 gives the general recurrence; §4, p. 24 specializes it to

\[
 x(t+1)=A x(t)+B u(t),\qquad t=0,\ldots,9,
\]

with

\[
A=\begin{bmatrix}1&0&0&0\\-1&1&0&0\\0&0&1&0\\0&0&-1&1\end{bmatrix},\qquad
B=\begin{bmatrix}5/12\\0\\-1/3\\0\end{bmatrix}.
\]

Thus, explicitly,

\[
\begin{aligned}
x_1(t+1)&=x_1(t)+(5/12)u(t), &x_2(t+1)&=x_2(t)-x_1(t),\\
x_3(t+1)&=x_3(t)-(1/3)u(t), &x_4(t+1)&=x_4(t)-x_3(t).
\end{aligned}
\]

The state is \(x=(x_1,x_2,x_3,x_4)\): oxidizer mass flow, oxidizer tank mass, fuel mass flow, fuel tank mass. The single scalar action satisfies \(u(t)\in[-1,1]\) on stages 0–9. The initial state printed on p. 24 is \(x(0)=(25.14,\;247,\;19.915,\;199.92)^T\). This normalizes the Russian decimal commas in the printed four-vector; whitespace separates its four components. The terminal point is likewise normalized from decimal-comma notation below.

The only explicit state constraints in the example are engine reliability flow bounds (the text says they are for engine reliability; the natural stage range is t=0,…,10, but the example does not restate the quantifier): \(x_1(t)\in[24.167,25.833]\) and \(x_3(t)\in[19.33,20.66]\) (printed with locale commas in Russian text). No numerical bounds on tank masses \(x_2,x_4\) are given. The general setup in §1, assumptions 1–3 (pp. 20–21) allows constrained initial, intermediate and final states and bounded controls; the example itself supplies a singleton initial condition and the scalar action interval above. It does not state units or a physical duration per discrete step. It says the numerical parameters are scaled for visual presentation (p. 24), and cites [8] for fuller model derivation. Consequently, physical units, conversion back to dimensional fuel/flow values, and a time-step interpretation are unknown from this example.

The terminal time is \(T=10\) (p. 24), corresponding to ten controls and eleven state samples. The printed convex terminal objective is

\[
\Phi(x(T))=(25-x_1(T))^2+x_2(T)^2+(20-x_3(T))^2+x_4(T)^2+(x_2(T)-x_4(T))^2.
\]

The paper describes the first and third terms as final flow deviations, the second and fourth as remaining oxidizer/fuel reserves (seeking zero), and the fifth as unsynchronized consumption (p. 24). It reports minimum \(\Phi(T)=4.6608\) at terminal point

\[
X_{\Phi^e}(T)=(25.013,\;-1.4669,\;20.016,\;-1.5798)^T
\]

(p. 24; signs are shown as minus in the publisher PDF). Negative terminal tank masses are therefore part of the printed result under this scaled model and are not ruled out by the stated constraints. Figure 1 on p. 25 shows 2D projections of forward/backward reachable sets and their intersections; Figure 2 shows a bundle of optimal trajectories. The paper says the corresponding controls are optimal and convex combinations of those controls remain optimal (p. 25), but it does not print numeric control sequences or a tabular trajectory. Those exact sequences are unavailable from text and should not be reverse-engineered from the plotted curves.

## Printed method and evidence limits

Sections 2–3 (pp. 21–23) describe an exact reachable-set construction/analysis workflow: forward reachable sets via a general algebraic recurrence; convex terminal minimization (using Zoutendijk as an example); backward reachable sets from the minimizing terminal set; intersections that form the feasible trajectory tube; then recovery of the set of optimal open-loop controls as an LP. The paper also uses Chernikova’s conversion between vertex and facet descriptions. In the example, the reported output is the terminal objective/state plus reachable-set and trajectory plots—not runtime, vertex counts, numeric controls, or a machine-readable certificate. Its conclusion (p. 25) calls exact reachable-set growth a computational limitation, notes possible parallelization and polyhedral approximation, and frames real-time use as a possibility, not a measured capability.

## Relationship to existing lab cases and C++ fit

This is a distinct *source profile*, not an additional name for existing fuel, orbit, or Lotka–Volterra cases. It is a 4-state, one-input, linear discrete fuel-flow/remaining-mass model with ten scalar actions and a quadratic terminal criterion. The repository’s current B04 fuel reference is a separate 16-step profile with different initial values, coefficients, stage duration, and an affine-residual norm objective (`docs/research/evidence/b04-reference-v1/canonical-case.json`); the repository already treats historical B04 as unresolved and makes no reproduction claim. The orbit profile is a separate orbital model; Lotka–Volterra is a nonlinear population model. This paper contributes a distinct short-horizon, exact-polyhedral terminal-control case. A new run should identify the published scaled model as its source and must not add unprinted physical units or constraints.

For a C++ baseline, the equations are small and affine, the action set is an interval, the flow constraints are linear slabs, and the terminal objective is convex quadratic: these permit a direct QP/LP-based trajectory formulation and an independent small-horizon verification path. Capability gaps relative to the paper’s claims are substantial: matching its method requires forward and backward constrained reachability, exact polytope representation/conversion and intersections, minimizing over a reachable terminal set, and recovery of *all* optimal controls (not just one optimizer). A direct optimizer returning one sequence would only reproduce a feasible/optimal witness, not the paper’s full optimal-control set or exact reachable geometry. The stated terminal masses are negative and the units/scaling are not defined, so physical-consistency claims are out of scope. The published scaled task can still be used as an article-derived case with its source, assumptions, and limits recorded.

## Unknowns and follow-up evidence

- Whether the matching NPOA `.doc` equation objects agree with the publisher’s printed initial vector and matrices; plain-text extraction omits embedded equation objects. This is needed only to claim correspondence with that draft, not to define an article-derived case from the publisher PDF.
- Physical units and discrete step duration; the article says values are scaled and does not declare either.
- Numeric optimal controls, full stage-by-stage state sequence, reachable-set vertex/facet data, and computational resource/results.
- Whether negative tank masses are an accepted artifact of the scaled demonstration or a modeling convention/translation issue.

The publisher PDF supports the section/page claims and is directly linked above. In it, equation (1) is on p. 20; the example’s matrices, state labels, constraints, initial state, objective, terminal time and reported optimum are in §4 on p. 24; figures and the convex-combination statement are on p. 25.
