# MPC-08 exact region and predecessor evidence

**Goal:** Extend #604 with whole-domain checks, matched successor quantifiers and a first native capture, preserving the earlier pilots.

**Architecture:** Reuse the existing rational N=1 double-integrator region producer. Check its output independently by rational line-intersection enumeration and convex-hull predicates. Keep the N=2 terminal-velocity optimizer fiber separate from its minimum-norm selector. Native observations use the existing public ConvexPort/strategy client; candidate containment never becomes completeness authority.

**Spec:** Live #604, the comparison-program contract and `docs/research/mpc08-explicit-set-comparison.md`. The owner explicitly authorizes these runs and continuation without further questions. No shared Pages files or external runtime installation belongs to this unit.

## Fixed profiles

- Original N=1: A=[[1,1],[0,1]], B=(0,1), X=[-3,3]×[-2,2], U=[-1,1], terminal T={|p+v|≤1, |p+2v|≤1}, J=||x1||². Verify every critical region and its value/action, their full closed coverage and boundary agreement.
- Nominal predecessor: ∃u∈U: Ax+Bu∈T. Robust variant: ∃u∈U ∀w∈[-1/8,1/8]: Ax+Bu+(0,w)∈T_r. Let T_r={|p+v|≤3/4, |p+2v|≤1}; prescribed K=(-1,-2) preserves T_r for every w. Retain the original T's counterexample under this disturbance. Compare whole-successor inclusions, not sampled successors or swapped ∀w∃u.
- Target approximation diagnostic: axis-aligned inner and outer boxes of T_r have explicit containment directions. Their predecessors inherit those directions; neither box is called invariant without a separate proof.
- Nonunique terminal-velocity family: N∈{1,2,4,8,12,16}, ui∈[-1,1], J=vN². At v0=0 the full zero-cost control fiber is the cube slice Σui=0. Save facet/vertex counts and explicit budget refusals. Constant selector-region count is not exponential critical-region growth.

## Verifiable units

1. Add a fixture-specific exact checker using pairwise rational H-row intersections, independently of the producer's clipping. Check containment, exact area, empty interior overlap, affine boundary agreement and scalar KKT/value identities on all region vertices. Add real mutation tests.
2. Construct/check the nominal and robust predecessors, invariant terminal sets and inner/outer target comparisons. Export a labelled shared-style 2D figure, exact H/V data and construction/check/location costs.
3. Check nonunique fibers algebraically over the full parameter domain; retain actual enumeration cost/counts under a vertex budget. No general mpQP or duplicate set-comparison engine is introduced.
4. Commit the executable source and perform a fresh bounded first capture with existing public solver routes, recording source/library/binary/input hashes, compiler, resources, setup/run scopes, failures and sample-only evidence limits. A reused native library receives its actual build identity, never a fictitious clean current-source rebuild.
5. Independently recheck raw outputs, publish a reviewable local HTML/raw bundle and request separate standards/specification reviews. Pages wiring and issue closure remain later gates.

## Research and delivery limits

The author-hosted 2002 paper's positive-definite mpQP result does not establish uniqueness for singular terminal-only multistep problems. Its 2003 corrigendum corrects Example 7.1's terminal P; this synthetic fixture is not that example. Official MPT3 documentation still states GPL and MATLAB prerequisites. No MPT3/PPOPT execution, MATLAB purchase, acados run, ordinary LQR running-cost substitution or external solver installation is claimed.

This optional source/report unit adds no public API or required dependency and needs no standalone library release. A general critical-region growth study and complete original-quadratic CSL family proof remain explicit residuals unless actual delivered evidence establishes them.
