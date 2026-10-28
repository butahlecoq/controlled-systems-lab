# MPC-06 tube-MPC architecture work

## Architect phases

- [x] Ground: map existing robust reachability, set inclusion, optimization, reporting and validation modules.
- [x] Sketch: compare distinct placements for tube construction and robust checks; record caller usage, data types and invariants.
- [x] Agree: proceed without a human checkpoint; the live issue and owner authorization establish execution scope.
- [x] Implement: build the smallest useful initial exact low-dimensional study against the selected shape.
- [ ] Scrap: reconsider the shape if implementation requires repeated escape hatches or duplicates ownership.

## Arena phases

- [x] Frame: produce a design package for a small, auditable exact tube-MPC comparison slice.
- [x] Fan out: create independent, read-only architecture and design candidates.
- [x] Cross-judge: independently score candidates against the shared rubric.
- [x] Pick: select the candidate with the deepest interface and clearest mathematical invariants.
- [x] Graft: incorporate only the strongest compatible ideas from the other candidates.
- [x] Verify: check the synthesized sketch against repository contracts and issue #602.

## Grounding question

Where should an initial tube-MPC study sit so that RPI-set construction, tightened constraints, exact robust feasibility evidence, and the existing comparison/report pipeline have clear ownership without exposing duplicated stage-by-stage geometry logic?

## Arena artifact and rubric

Each candidate returns caller usage, a module map, core types and signatures, implementation ownership, mathematical invariants, and a one-page rationale. Score candidates on: (1) sound RPI/tightening semantics, (2) reuse of existing CSL geometry/LP facilities without creating duplicate comparison infrastructure, (3) small caller surface that separates feasibility/safety from costs, (4) reproducible saved evidence and figure generation, and (5) extension path for outer approximations without unsupported guarantees.

## Current evidence

- Issue #602 is open, assigned to the current session, and has no open implementing PR.
- Native prerequisites #596, #3 and #83 are closed.
- The current issue's outer approximation extensions remain gated by #99/#100.
- A first feasibility-only driver constructs the nilpotent double-integrator profile, derives the fixed zonotope tube and support tightenings, and verifies `(A+BK)Z+EW ⊆ Z` with the existing exact H-relation inclusion engine.
- An independent Python `Fraction` oracle checks the exact dyadic tube identity, state/input supports, the eight disturbance-vertex paths for the fixed zero nominal plan, an empty-tightening case, and an unsafe nominal-input witness.
- The first configured Release build and focused CTest pass with HiGHS and Qhull disabled, confirming the feasibility slice has no new solver dependency.
- A saved-data SVG/HTML renderer shows `Z`, `X⊖Z`, `X`, `U⊖KZ`, and the rejected unsafe input. The rendered preview has been visually inspected.
- The result is captured with driver, checker, scenario, and source-commit identities and saved under `reports/algorithm-results/mpc06-nilpotent-tube-pilot-v1`.
- A dedicated staging adapter now validates saved checksums, replays the exact result, regenerates HTML/SVG from saved data, creates a content-addressed immutable Pages route and offline ZIP, and adds a link after the archive landing page is rendered.
- The renderer is registered in the visual-route inventory and assigned to control/witness visualization follow-up #686. Publication tests verify the landing link, route manifest hashes, checksums, and ZIP contents.

## Grounding summary

`fixed_plan_disturbance` provides bounded numerical forward propagation for one open-loop control sequence and rejects unsafe successors without clipping; it does not synthesize a feedback tube. `finite_feedback` solves safety/winning on an indexed finite graph; it does not carry continuous set geometry or cost optimality. `finite_action_minimax` enumerates fixed finite plans; it is not a continuous-control MPC solver. CSL's geometry operations and generic LP/QP workspaces expose provider and evidence contracts but do not own tube-MPC semantics. `SetData` covers H/V and trivial sets; constrained generator sets are a separate dependent representation. No public Pontryagin-difference operation was found. Existing plot/report capture should freeze actual computed sets and evidence; renderers must not run solvers or strengthen claims.

## Candidate record

- Candidate A (`/tmp/arena-mpc06-tube/candidate-a/design.md`): synthesis-side study API, exact nilpotent error dynamics (`F^m=0`) so a finite Minkowski sum has an exact zero tail, exact support-based tightening and a bounded exact joint-relation feasibility reference. It separates optimizer evidence and study/report code from solver semantics.
- Candidate B (`/tmp/arena-mpc06-tube/candidate-b/design.md`): a control/tube analyzer that accepts a proposed RPI set and verifies it, plus support tightenings, initial error inclusion and nominal-plan feasibility. It proposes an internal bounded 2D checker and optional cost solver.
- Both reject using generic QP success as a robust-safety certificate, keep approximation variants behind #99/#100, and freeze report data before rendering.
- Cross-judge rubric scores (A/B): RPI/tightening 5/4; infrastructure reuse 4/4; small separated safety interface 5/4; report and 2D plot 4/5; approximation path 4/4. The judge recommends A because it derives a zero-tail RPI set and uses the repository's exact H relation engine; B has better explicit saved-report alignment but a less grounded dedicated checker boundary.

## Synthesis decision

Use Candidate A's synthesis-side, optimizer-free study analyzer and exactly nilpotent error dynamics. Do not add a generic MPC strategy provider or general geometry provider. Graft B's explicit use of saved computed plot data, exact/numerical/inconclusive labels, and strict separation between safety results and optional nominal objective results. Report integration must reuse the existing immutable run/report conventions where feasible; do not establish a parallel canonical comparison schema. Only add the public surface needed by this study; leave generic stable-tail certificates, outer approximations and general causal optimality out of scope.

## Synthesis risks / first implementation gate

Before adding the proposed API, inspect the actual exact H relation helper and published-result/delivery contracts. The key gate is whether existing internal exact arithmetic can support the exact nilpotent RPI, support functions, and joint fixed-policy feasibility check without introducing an unreviewed second geometry engine. If it cannot, reduce or reshape the case and return an explicit unsupported/inconclusive result rather than claim exactness.

## Implementation evidence and next gate

The feasibility-only exact profile is implemented in `benchmarks/reporting/mpc06_tube/driver.cpp`; the pinned scenario and independent oracle are `benchmarks/scenarios/mpc06-nilpotent-tube-v1.json` and `scripts/reports/mpc06/check_tube.py`. Focused Release build/CTest, publication tests, visual-route inventory test, checksums, and visual inspection pass. One Release analysis timing observation is saved (n=1, no warmups), with zero errors and all work verified; it is explicitly inconclusive, has no limiter profile, and makes no comparison claim. Full local site generation was attempted but stopped because the local Python environment lacks report-only `jsonschema`; CI installs `scripts/reports/requirements.txt`. Before treating this as a complete #602 slice, run exact-head CI, post independent review evidence, and verify the deployed URL. No objective optimization or performance comparison has run.
