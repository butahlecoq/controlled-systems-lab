"""Render a readable landing page for the published algorithm report archive.

The Pages root index is assembled from the immutable catalogue and from the
per-family staging scripts, each of which appends one list item. This module
turns that assembled list into a page a reader can navigate: every report gets
a plain-language title and summary, the scope and the evidence limits recorded
with that report, and direct links to the report page, its raw records, its
measured tables and its offline bundle.

The scope and the limits on a card are the ones recorded with the report in
its own staged bundle, not the wording of the script that staged it. The page
reuses the dark appearance of the saved report pages - the Gruvbox palette
used by the APP-02, APP-03, EXP-04 and GEO-08 reports - so the archive index
and those reports read as one site.

Every published report family needs a human-readable description here. A
family whose route does not match a registered pattern is an error, not a
silently cryptic list entry, so a newly published report cannot reach the
archive without an explanation.
"""
from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import NamedTuple


class Family(NamedTuple):
    """One report family: the routes it covers, where it belongs and what it is."""

    pattern: str
    group: str
    title: str
    summary: str


class Entry(NamedTuple):
    """One report as it appears on the landing page."""

    report_id: str
    scope: str
    limits: str
    commit: str
    links: tuple


# Reading order of the archive. Each entry is (key, heading, introduction).
GROUPS = (
    ("optimization", "Convex optimization",
     "Linear and convex references, feasibility search, hull construction and solver reuse. "
     "Each report states the adapter it measured and the comparisons it does not make."),
    ("geometry", "Geometry",
     "Set and polyhedron operations: conversion, intersection, affine maps and sums, "
     "projection, hull construction and lazy evaluation over small bounded fixtures."),
    ("synthesis", "Control synthesis",
     "Reachability, terminal minimizers and complete strategy families for discrete-time "
     "control, with the verifier that accepted each relation."),
    ("extensions", "Extensions and models",
     "Approximation, replay and extension profiles: boxes, zonotopes, ellipsoids, discretized "
     "and hybrid models, and sampled plant replays."),
    ("verification", "Verification and profiling",
     "Independent re-checks of saved witnesses and a diagnostic profile kept separate from the "
     "published latency statistics."),
)


# Report family -> description. The pattern matches the whole published route,
# so a new route shape has to be registered here on purpose.
FAMILIES = {
    "mpc08-explicit-pilot": Family(
        r"mpc08-explicit-pilot-v1", "synthesis", "Explicit MPC feasible domain and critical regions",
        "Presents an exact rational one-step double-integrator fixture with its feasible initial-state "
        "domain, nine control critical regions, separate terminal invariant set, and fixed-initial "
        "candidate and online-QP observations. It is a bounded pilot and does not complete issue #604."),
    "mpc03-open-loop-pilot": Family(
        r"mpc03-open-loop-pilot-v1", "synthesis", "Open-loop robust minimax formulation pilot",
        "Cross-checks one synthetic two-stage scalar fixed-plan minimax case with an exhaustive "
        "finite-action oracle, a shared-selector MILP and its continuous selector relaxation. "
        "The report measures no performance and does not complete issue #599."),
    "mpc03-b08-miQCP": Family(
        r"mpc03-b08-l04-miQCP-v1", "synthesis", "B08 robust minimax MIQCP",
        "Solves the four-step L04 displayed-data finite-action minimax model with a shared-selector "
        "MIQCP, checks it against exact rational enumeration, and records a numerical convex-hull "
        "relaxation bound. This is not a historical reproduction or solver-speed comparison."),
    "mpc05-causal-tree": Family(
        r"mpc05-causal-tree-[0-9a-f]{20}", "synthesis", "Finite causal minimax scenario-tree comparison",
        "Compares a dependency-free Bellman solver with an independent HiGHS extensive-form tree on "
        "finite fixtures and a three-stage TwoPointsOnParallelLines adaptation. The report shows "
        "forward reachable sets, terminal sets, backward-winning intersections, and a replayed "
        "worst-case path in both player phase planes; it makes no continuous RL or performance claim."),
    "mpc09-output-feedback": Family(
        r"mpc09-output-feedback-[0-9a-f]{20}", "synthesis", "TwoParticleGame output-feedback MPC",
        "Compares finite-prior certainty-equivalent and set-based receding minimax controllers on a "
        "noisy-observation adaptation of the RL differential-game environment. Every listed row is "
        "independently replayed, and a complete finite observation-history minimax reference is "
        "included. The result is finite-catalogue evidence, not a continuous-noise or RL reproduction."),
    "exp03-two-points-approx-publication": Family(
        r"exp03-two-points-approx-publication-v[12]", "synthesis",
        "TwoPoints finite-action reachability and approximation report",
        "Shows stagewise forward reachable geometry, terminal sets, backward-winning intersections, "
        "open-loop and feedback worst-case paths, and exact/approximate set outlines in both player "
        "phase planes for the three-stage TwoPointsOnParallelLines adaptation. The v2 bundle adds "
        "an exact finite-catalog minimax reference and inclusion-gated objective bounds. These are "
        "saved pilot results, not a reproduction of the continuous-action RL task or a performance claim."),
    "exp06-geometry-pilot": Family(
        r"exp06-[0-9a-f]{16}", "geometry", "Bounded exact-hull geometry pilot",
        "Presents bounded exact-hull comparisons on a nine-point dyadic square. Reports include "
        "the A29/A30 Python reference, C++ QuickHull, and in the ITIS'17 follow-up, separate safe "
        "A43, paper-derived A43 tie variants, and a separately identified A44 incremental LP row. An independent exact "
        "checker validates each returned hull; cross-runtime timing is inconclusive and these "
        "single-fixture pilots do not establish a general speedup or complete the geometry ladder."),
    "lp": Family(
        r"lp-\d{8}T\d{6}Z-[0-9a-f]{12,64}", "optimization", "Linear programming reference run",
        "Runs the registered HiGHS linear-programming adapter on five small analytic "
        "microfixtures and records the solved objective, the solver status and the timing of "
        "every call. It is a single-adapter reference measurement and states no comparator, "
        "application-scale or certification claim."),
    "convex": Family(
        r"convex-\d{8}T\d{6}Z-[0-9a-f]{12,64}", "optimization", "Convex optimization reference run",
        "Runs the registered HiGHS convex adapter on nine small analytic microfixtures and "
        "records the returned optimum, the solver status and the timing of every call. Like "
        "the linear reference run it measures one adapter and states no comparator claim."),
    "opt04": Family(
        r"opt04-\d{8}T\d{6}Z-[0-9a-f]{12,64}", "optimization", "Phase-one feasibility search",
        "Searches for a feasible point of equality- and nonnegativity-constrained problems "
        "with an internal phase-one method, then checks the returned witness against an "
        "independent HiGHS reference. The report records feasibility outcomes and timing; a "
        "witness is not a description of the complete feasible set."),
    "opt05-hull": Family(
        r"opt05-hull-\d{8}-[0-9a-f]{8,64}", "optimization", "Convex hull construction",
        "Builds the convex hull of square lattices of points and compares the result with an "
        "independently checked hull. The recorded trials cover small lattices only, and the "
        "checks are numerical rather than exact."),
    "opt06": Family(
        r"opt06-basis-reuse-\d{8}-[0-9a-f]{8,64}(?:-[0-9a-f]{8,64})?", "optimization", "Basis reuse across linear programs",
        "Measures a paired workflow in which the solver basis of one linear program is reused "
        "for the next, over three small two-dimensional point clouds. The numbers are "
        "descriptive paired timings; they do not establish a general speedup."),
    "opt07": Family(
        r"opt07-[0-9a-f]{16,64}", "optimization", "Ordered hull construction with exact certificates",
        "Runs measured batches of the ordered-hull builder over three fixed small point clouds "
        "and independently checks each produced hull with exact dyadic deletion certificates. "
        "The timings are single-adapter observations on one host."),
    "opt11": Family(
        r"opt11-[0-9a-f]{16,64}", "optimization", "Recursive hull construction",
        "Compares a recursive hull construction with a baseline hull on the same three fixed "
        "binary64 point clouds, alternating baseline and recursive batches. The comparison is "
        "descriptive and specific to the recorded backend and host."),
    "opt12": Family(
        r"opt12-warm-start-[0-9a-f]{12,64}", "optimization", "Warm-start transfer cost",
        "Measures how much work can be saved when a solved linear program is reused as a warm "
        "start for the next one, over three synthetic linear programs with seven alternating "
        "repetitions per side. The observed transfer-cost ranges overlap, so the report keeps "
        "its performance interpretation inconclusive."),
    "geo02": Family(
        r"geo02-\d{8}T\d{6}Z-[0-9a-f]{12,64}", "geometry", "Affine maps and Minkowski sums",
        "Applies affine maps and independent Minkowski sums to small point clouds and checks "
        "the returned geometry against literal expected values. The published record states the "
        "certificate coverage of the run it belongs to."),
    "geo03": Family(
        r"geo03-\d{8}-[0-9a-f]{12,64}", "geometry", "Vertex and half-space conversion",
        "Converts small bounded two-dimensional fixtures between the vertex and half-space "
        "representations in both directions and checks the results. The report covers contract "
        "fixtures only, with no workload-size baseline and no inner conversion phase timing."),
    "geo04": Family(
        r"geo04-\d{8}T\d{6}Z-[0-9a-f]{12,64}", "geometry", "Polyhedral intersection",
        "Intersects small analytic polyhedra and records the returned representation and the "
        "timing of every attempt. The HiGHS-based reduction remains incomplete and retains all "
        "rows, and no comparator or speedup claim is made."),
    "geo05": Family(
        r"geo05-[0-9a-f]{16,64}", "geometry", "Projection and predecessors",
        "Projects small bounded two-dimensional fixtures and computes their predecessor sets, "
        "recording the outcome of every attempt. Support for the half-space relation remains "
        "unestablished, and the checks are numeric samples rather than exact set equality."),
    "geo06": Family(
        r"geo06-[0-9a-f]{16,64}", "geometry", "QuickHull hull construction",
        "Runs measured batches of a thousand QuickHull calls over three small analytic point "
        "clouds and verifies every produced hull against a literal oracle. The timed interval "
        "includes index copies and the oracle comparison itself."),
    "it17-hull-adaptations": Family(
        r"quickhull-it17-paper-adaptations-\d{8}-r\d+", "geometry",
        "QuickHull and ITIS17 paper-informed LP reducers",
        "Compares geometric QuickHull with five separately identified LP reducers on three "
        "small exact 2D clouds. A43 and A44 are paper-informed adaptations, not faithful paper "
        "or Pascal ports; the performance conclusion is inconclusive."),
    "exp02-it17-dyadic": Family(
        r"exp02-it17-(?:dyadic-interior|a44-paper-order|dyadic-250)-\d{8}-r\d+", "geometry",
        "Repeated ITIS17 dyadic hull pilot",
        "Compares six separately identified hull reducers on deterministic interior-heavy 2D "
        "square clouds, with one 250-point continuation. r1 labels A43/A44 as adaptations; r2 "
        "adds the k+1 farthest-seeded Euclidean A44 interpretation; r3 separates exact hull "
        "validity from reducer classification completeness. Incomplete reductions remain "
        "visible and the performance conclusion is inconclusive."),
    "exp02-it17-hull-3d": Family(
        r"exp02-it17-hull-3d-(?:simplex|halton-cloud)-\d{8}-r\d+", "geometry",
        "ITIS17 three-dimensional hull reducer pilot",
        "Reports one tetrahedron with exact dyadic interior redundancy plus its preserved initial "
        "pure-Halton attempt. Three of five LP reducers completed on the informative fixture; "
        "QuickHull is unsupported in 3D, incomplete outcomes remain visible, and no speedup is claimed."),
    "exp02-it17-hull-4d": Family(
        r"exp02-it17-hull-4d-simplex-\d{8}-r\d+", "geometry",
        "ITIS17 four-dimensional hull reducer pilot",
        "Reports one 250-point 4-simplex fixture with 245 exactly representable interior points. "
        "Three of five LP reducers completed; two exact but incomplete outputs have withheld timings, "
        "QuickHull is unsupported in 4D, and no speedup is claimed."),
    "geo07-generator-sets": Family(
        r"geo07-generator-sets-[0-9a-f]{16,64}", "geometry", "Generator-set evaluation",
        "Evaluates generator-set requests over three bounded public generator-set fixtures, "
        "with five thousand fresh calls per measured batch. These are exploratory "
        "single-adapter timings without a comparator or a limiter profile."),
    "geo07-registered-ports": Family(
        r"geo07-registered-ports-[0-9a-f]{16,64}", "geometry", "Registered geometry and conversion ports",
        "Drives the registered geometry and conversion ports over three bounded public "
        "fixtures, five thousand fresh calls per batch. The observations are exploratory and "
        "inconclusive."),
    "geo07-dependent-registered": Family(
        r"geo07-dependent-registered-[0-9a-f]{16,64}", "geometry", "Dependent Minkowski sums",
        "Measures dependent-sum requests through the registered ports over two bounded public "
        "fixtures, with two thousand checked calls per batch. Only single-adapter observations "
        "on the recorded host are reported."),
    "geo08": Family(
        r"geo08-lazy-[0-9a-f]{16,64}", "geometry", "Lazy geometry",
        "Checks a planar set expression that is evaluated only when a support query asks for "
        "it, and then materializes the native vertex form. It shows that a lazy set can be "
        "queried and materialized consistently on a small example."),
    "syn01": Family(
        r"syn01-[0-9a-f]{64}", "synthesis", "Nominal forward reachability",
        "Propagates reachable states forward for two authored scalar analytic fixtures over a "
        "two-step discrete horizon and checks the bounds of the returned row. The reachability "
        "relation is numerical and is not a validated certificate."),
    "syn02": Family(
        r"syn02-[0-9a-f]{64}", "synthesis", "Terminal minimizers",
        "Optimizes a supplied terminal objective over a supplied terminal slice and returns the "
        "candidate minimizers together with a sampled relation. This is a terminal subproblem "
        "rather than a complete control synthesis, and one shifted fixture returns an "
        "undetermined numerical failure."),
    "syn03-strategy-a-ts01": Family(
        r"syn03-strategy-a-ts01-[0-9a-f]{8,64}", "synthesis", "Strategy A on the T-S01 profile",
        "Runs the registered Strategy A synthesis path on the exact two-step scalar integrator "
        "profile and verifies the produced relation with the registered analytic verifier. The "
        "seven measured trials describe one strategy, not a comparison."),
    "syn03-strategy-a-ts02": Family(
        r"syn03-strategy-a-ts02-[0-9a-f]{8,64}", "synthesis", "Strategy A on the T-S02 profile",
        "Runs Strategy A on the constant-integrator profile: forward reachability and terminal "
        "optimization through the registered HiGHS provider, followed by reconstruction and "
        "verification of the full history relation."),
    "syn04-strategy-b-ts01": Family(
        r"syn04-strategy-b-ts01-[0-9a-f]{8,64}", "synthesis", "Strategy B on the T-S01 profile",
        "Runs the registered Strategy B synthesis path on the exact two-step scalar integrator "
        "profile and verifies the resulting complete-family relation with the registered "
        "analytic verifier. A separate diagnostic profile is excluded from the reported "
        "statistics."),
    "syn04-strategy-b-ts02": Family(
        r"syn04-strategy-b-ts02-[0-9a-f]{8,64}", "synthesis", "Strategy B on the T-S02 profile",
        "Runs Strategy B on the constant-integrator profile, where the admitted path constructs "
        "and verifies the full feasible relation analytically. The registered linear and convex "
        "providers are prepared but their numerical solve operations are not invoked."),
    "syn04-strategy-b-ts03": Family(
        r"syn04-strategy-b-ts03-[0-9a-f]{8,64}", "synthesis", "Strategy B on the T-S03 profile",
        "Runs the registered Strategy B path on the singular-A integrator profile, invokes the "
        "production HiGHS convex solver, and numerically verifies the full optimal-history "
        "relation. The report covers one fixture and makes no generic completeness or speedup claim."),
    "syn07-ts01": Family(
        r"syn07-ts01-[0-9a-f]{8,64}", "synthesis", "Exact optimal relation for the T-S01 profile",
        "Records the analytic theorem for the strict two-step scalar integrator profile: the "
        "exact optimal relation together with exact membership examples. Completeness is "
        "established only for that admitted profile, and the outer API still reports numerical "
        "assurance."),
    "syn-ts01-paired": Family(
        r"syn-ts01-paired-[0-9a-f]{64}", "synthesis", "Paired Strategy A and B comparison on T-S01",
        "Runs one paired experiment that alternates Strategy A and Strategy B on the same "
        "exact-profile fixture, with one excluded warmup and seven measured pairs. The timing "
        "distributions overlap, so no winner is claimed."),
    "issue3-finite-catalogue": Family(
        r"issue3-finite-catalogue-[0-9a-f]{16,64}", "synthesis", "Finite-action minimax over a catalogue",
        "Evaluates a finite catalogue of control actions with a minimax rule over eight checked "
        "fixtures and records batch timings with fixture-specific call counts. All winning flags "
        "and the selected action cells are checked; the remaining cells of the action tensor are "
        "not."),
    "issue6-b06-reference": Family(
        r"issue6-b06-reference-[0-9a-f]{64}", "synthesis", "Owner-confirmed B06 fuel reference",
        "Exhaustively searches the five-stage finite action catalogue over 1,024 disturbance "
        "corners per plan, with an independent integer oracle and 2D terminal-set projections. "
        "The disturbance box is owner-confirmed rather than printed in L09, so this is a distinct "
        "reference case, not a historical reproduction."),
    "issue6-b06-manifest-correction": Family(
        r"issue6-b06-manifest-correction-[0-9a-f]{64}", "synthesis", "B06 scenario manifest correction",
        "Publishes a corrected, dimension-valid B06 scenario and a source-level audit of the "
        "immutable measured report. The original malformed manifest, report bytes and ZIP remain "
        "unchanged; no solver rerun or new numerical certification is claimed."),
    "issue6-b07-reference": Family(
        r"issue6-b07-reference-[0-9a-f]{64}", "synthesis", "Owner-approved B07 fuel reconstructions",
        "Compares eight owner-approved five-stage fuel reconstructions and includes 2D flow and stock "
        "projections of the computed 4D terminal sets. These are not historical reproductions; the "
        "modeled horizon is 10 seconds while the paper states 100 seconds."),
    "issue6-b09-reference": Family(
        r"issue6-b09-reference-[0-9a-f]{64}", "synthesis", "A08 source-reference fuel minimax",
        "Exhaustively searches four-stage finite action plans and publishes flow and stock projections "
        "of the four-state terminal reachable set for two objective variants."),
    "issue3-validated-minimax": Family(
        r"issue3-validated-minimax-[0-9a-f]{64}", "synthesis", "Validated finite-action minimax bounds",
        "Measures three fixed fixtures through the validated API. The B08 row checks 625 plans and "
        "160,000 disturbance histories for saved binary64 inputs; timings are descriptive."),
    "finite-feedback-registered": Family(
        r"finite-feedback-registered-[0-9a-f]{16,64}", "synthesis", "Finite feedback games",
        "Plays authored finite games through the registered feedback port and checks every "
        "winning flag and selected action cell across four games. Concurrent work is not "
        "quantified, and no global causal minimax claim is made."),
    "b08-displayed-exact": Family(
        r"b08-displayed-exact-[0-9a-f]{64}", "synthesis", "Printed B08 model with an exact plan search",
        "Searches 625 control plans over the 256 corners of the printed rounded B08 linear model "
        "and checks the selected plan. The printed rounded model is used as printed; the "
        "historical 67.12 value, the unrounded arrays and the nonlinear plant remain "
        "unresolved."),
    "app01-plan": Family(
        r"app01-plan-\d{8}-[0-9a-f]{64}", "extensions", "State-plan check and trajectory verification",
        "Runs the registered inner state-plan check and then verifies the produced trajectory "
        "against the original problem statement over three literal scalar fixtures."),
    "app02-box": Family(
        r"app02-box-[0-9a-f]{16}", "extensions", "Box and parallelotope approximations",
        "Approximates a small diamond by axis-aligned and by rotated parallelotopes, and by "
        "inner boxes, checking every stored inclusion relation on exact binary64 examples. A "
        "two-dimensional example shows the shapes."),
    "app03-zonotope": Family(
        r"app03-zonotope-[0-9a-f]{16}", "extensions", "Zonotope reduction and outer cover",
        "Reduces a planar zonotope to an outer cover that keeps selected generator factors and "
        "replaces the omitted ones with independent coordinate-axis generators, verified from the "
        "stored coefficients. A two-dimensional example shows the cover."),
    "app04-ellipsoid": Family(
        r"app04-ellipsoid-[0-9a-f]{16}", "extensions", "Directional ellipsoid approximation",
        "Approximates a small convex set by a directional ellipsoid over three planar cases and "
        "checks the returned parameters against the stored values. A two-dimensional example "
        "shows the ellipse and the set."),
    "ext01-fixed-plan": Family(
        r"ext01-fixed-plan-[0-9a-f]{16,64}", "extensions", "Fixed-plan worst-case evaluation",
        "Evaluates a fixed control plan against worst-case disturbances over four native "
        "fixtures using the convex provider. The result is a numerical worst-case value for the "
        "displayed rounded model, not a validated enclosure."),
    "ext04-observed-replay": Family(
        r"ext04-observed-replay-[0-9a-f]{64}", "extensions", "Observed replay of sampled systems",
        "Replays sampled, explicitly observed system trajectories through the public replay path "
        "and checks the recorded outcomes. The observations are exploratory and cover one path "
        "only."),
    "ext04-continuous": Family(
        r"ext04-continuous-[0-9a-f]{16}", "extensions", "Continuous affine policy evaluation",
        "Checks a caller-supplied affine observation policy over one two-state joint initial set, "
        "retaining each supplied generator's trajectory and safety margin. This is a descriptive "
        "single-adapter measurement; it does not synthesize policies or certify arbitrary "
        "disturbances."),
    "ext04-affine-synthesis": Family(
        r"ext04-affine-synthesis-[0-9a-f]{16}", "extensions", "One-stage affine policy synthesis",
        "Synthesizes one affine action from a pre-decision noisy observation over a caller-authored "
        "joint initial-state/error V-hull. Evidence uses numerical binary64 arithmetic, assumes "
        "the supplied hull is complete, and does not prove infeasibility or cost optimality."),
    "ext04-h-policy": Family(
        r"ext04-h-policy-[0-9a-f]{16}", "extensions", "Joint H-domain policy evaluation",
        "Evaluates a caller-supplied affine observation policy over one authored correlated H-domain "
        "using numerical feasibility and dual support witnesses. The report makes no validated-arithmetic, "
        "policy-synthesis, or universal-disturbance claim."),
    "ext05-discretization": Family(
        r"ext05-discretization-[0-9a-f]{16}", "extensions", "Continuous-model discretization",
        "Discretizes a continuous double integrator into a discrete model and checks the discrete "
        "transition against the continuous one. A two-dimensional example shows the sampled "
        "trajectory."),
    "ext07-hybrid-two-parameter": Family(
        r"ext07-hybrid-two-parameter-[0-9a-f]{16}", "extensions", "Hybrid system with two control parameters",
        "Checks a one-step hybrid system with switched dynamics and two control parameters, and "
        "records the measured calls of the registered hybrid path."),
    "ext07-hybrid": Family(
        r"ext07-hybrid-[0-9a-f]{16}", "extensions", "Hybrid one-step verifier",
        "Checks a one-step hybrid system with switched dynamics and a piecewise linear state "
        "update, and records the measured calls of the registered hybrid path."),
    "ext03-transform": Family(
        r"ext03-transform-[0-9a-f]{64}", "extensions", "Temporal memory transform microbenchmark",
        "Measures a fixed two-step scalar memory lift and history recovery. It does not run or "
        "compare a control solver."),
    "opt10-smooth": Family(
        r"opt10-smooth-[0-9a-f]{16}", "extensions", "Declared smooth-convex adapter",
        "Runs the declared smooth-convex adapter on a two-dimensional box-quadratic problem and "
        "checks the returned optimum and iterates against the stored values. A two-dimensional "
        "example shows the problem."),
    "issue4-volterra": Family(
        r"issue4-volterra-[0-9a-f]{16}", "extensions", "Candidate Volterra model-error bound",
        "Records a sixty-stage validated two-dimensional bound on the same-control deviation "
        "between the candidate Volterra model and the reference model. It is a candidate bound "
        "for one model pair, not a general model-error certificate."),
    "exp04-replay": Family(
        r"exp04-replay-[0-9a-f]{16}", "extensions", "Independent plant replay",
        "Replays chosen controls on the public exact-discrete plant map over four analytic "
        "histories and checks every trajectory and terminal objective. The timings are "
        "exploratory single-adapter observations."),
    "env717-simple-control": Family(
        r"env717-simple-control-[0-9a-f]{20}", "synthesis",
        "SimpleControlProblem finite-action pilot",
        "Exhaustively evaluates 81 four-step control sequences for one source-attributed "
        "discrete environment adaptation, checks the ten near-minimizing plans independently, "
        "and includes a labelled time/state trajectory plot. The pilot changes the upstream "
        "initial state and horizon, omits running reward, and makes no general environment or "
        "performance claim."),
    "env717-two-points": Family(
        r"env717-two-points-[0-9a-f]{20}", "synthesis",
        "TwoPointsOnParallelLines finite-action differential-game pilot",
        "Exhaustively evaluates 27 open-loop control sequences against every disturbance-vertex "
        "history, with independently replayed forward reachable phase-plane polytopes and a "
        "finite-vertex backward feedback graph. The source continuous-action 10-second task is "
        "adapted to three stages; this makes no claim about continuous or full-horizon control."),
    "env717-unequal-game": Family(
        r"env717-unequal-game-[0-9a-f]{20}", "synthesis",
        "UnequalGame finite-action minimax pilot",
        "Exhaustively evaluates 27 fixed control sequences against 27 disturbance-vertex histories "
        "per sequence, with independent replay of the scalar forward reachable intervals, robust "
        "backward nodes and a worst-case trajectory. The source continuous-action 2-second task is "
        "adapted to three stages; this is not a reproduction of the RL run."),
    "env717-air-to-air": Family(
        r"env717-air-to-air-[0-9a-f]{20}", "synthesis",
        "AirToAirInterception finite minimax pilot",
        "Exhaustively evaluates 125 fixed plans against 125 disturbance histories per plan, with "
        "independent full-state replay, forward reachable projections, open-loop and causal "
        "feedback-winning layers, and a selected worst-case path in relative position-velocity "
        "planes. This is a three-stage finite-catalogue adaptation, not a reproduction of the RL "
        "run. Timing is one observation with zero warmups; no performance comparison is claimed."),
    "env717-multipoint": Family(
        r"env717-multipoint-[0-9a-f]{20}", "synthesis",
        "MultiPointCostGame finite-action minimax pilot",
        "Compares exhaustive fixed-plan minimax and exact-state causal Bellman values for a "
        "source-attributed position-velocity environment adaptation. The figure shows all "
        "forward reachable states and selected worst-case paths. It omits the source checkpoint "
        "costs, uses four one-second finite-catalogue decisions, and defines no target or backward "
        "winning set; it is not a reproduction of the RL run."),
    "env717-broken-triangle": Family(
        r"env717-broken-triangle-[0-9a-f]{20}", "synthesis",
        "BrokenTriangleGame finite minimax and reachability pilot",
        "Compares exhaustive fixed open-loop plans with a finite observed-state causal Bellman "
        "policy using the source RL example's initial state, dynamics and terminal polygon. The "
        "figure overlays forward states, finite robust backward-winning intersections and both "
        "worst-case paths. Four decisions and two-point action/disturbance catalogues form a finite "
        "adaptation; no RL training reproduction, continuous boundary or performance comparison "
        "is claimed."),
    "env717-max-coordinate": Family(
        r"env717-max-coordinate-[0-9a-f]{20}", "synthesis",
        "MaxCoordinateGame finite-action differential-game pilot",
        "Exhaustively evaluates eight fixed control plans against eight disturbance-vertex histories "
        "per plan, with independently replayed oscillator phase-plane reachability and a worst-case "
        "trajectory. The source 4-second continuous-action task is adapted to three stages; this "
        "is not a reproduction of the RL run. Timing is one descriptive observation with zero "
        "warmups; it is not a performance comparison."),
    "env717-sphere-game": Family(
        r"env717-sphere-game-[0-9a-f]{20}", "synthesis",
        "SphereGame finite-action minimax pilot",
        "Exhaustively evaluates 27 fixed control plans against 27 disturbance-vertex histories per "
        "plan, with independently replayed phase-plane reachability and a worst-case trajectory. "
        "The source 8-second continuous-action task is adapted to three stages; the report separates "
        "the open-loop minimax value from its finite-state feedback geometry. One timing observation "
        "is recorded with zero warmups and no performance comparison."),
    "env717-point-on-plane": Family(
        r"env717-point-on-plane-[0-9a-f]{20}", "synthesis",
        "PointOnThePlane finite-action minimax pilot",
        "Exhaustively evaluates 125 open-loop plans against 125 disturbance histories per plan. "
        "A source-equation replay independently checks the four-state time-varying Euler map and "
        "plots finite forward states, backward-winning intersections and a worst-case trajectory "
        "in the position (x1,x2) and velocity (x3,x4) planes. The continuous-action 4-second source "
        "task is adapted to three stages; no RL reproduction or performance comparison is claimed."),
    "env717-time-sphere": Family(
        r"env717-time-sphere-[0-9a-f]{20}", "synthesis",
        "TimeOptimalSphereGame nominal finite-feedback reachability pilot",
        "Replays the source's ten explicit-Euler substeps per outer action and exhaustively builds "
        "the finite state graph for controls {-1,0,1}. A backward finite-feedback sweep finds the "
        "first horizon whose winning set contains the initial point, with forward states, unit-disk target "
        "intersections and a selected capture path in the (x1,x2) plane. The source's adversarial "
        "input is fixed at zero for this nominal reachability slice; it is not the continuous "
        "two-player RL optimum or a performance comparison."),
    "env717-time-sphere-minimax": Family(
        r"env717-time-sphere-minimax-[0-9a-f]{20}", "synthesis",
        "TimeOptimalSphereGame adversarial finite-catalogue minimax",
        "Preserves the source's ten held-action Euler substeps and lets both players choose from "
        "the finite catalogue {-1,0,1}. Reports the first robust capture horizon and a causal "
        "minimax capture time, with forward states, backward-winning intersections and a "
        "worst-case path overlaid in the position–velocity plane. The exact finite nodes are "
        "available in the figure data; displayed convex-hull envelopes are visual guides only. "
        "The adaptation also lets the disturbance observe the controller's current action, unlike "
        "the source state-feedback policies; its value is for this sequential-response game. It is "
        "not an RL reproduction or continuous-boundary claim."),
    "env717-two-particle-minimax": Family(
        r"env717-two-particle-minimax-[0-9a-f]{20}", "synthesis",
        "TwoParticleGame finite reachability and minimax",
        "Builds the source-derived four-state RK4 game on a quantized finite reachable graph, "
        "then checks finite-feedback capture and finite causal minimax against independent replay. "
        "Forward states, backward-winning intersections, and a selected worst-case trajectory are "
        "shown in position (x1,x2) and velocity (v1,v2) projections. The pilot changes the initial "
        "state and shortens the horizon; the finite solver gives the disturbance player a stronger "
        "within-stage information pattern. This is not a continuous-action RL reproduction."),
    "env717-homicidal-chauffeur": Family(
        r"env717-homicidal-chauffeur-[0-9a-f]{20}", "synthesis",
        "HomicidalChauffeur finite reachability and minimax",
        "Applies finite-feedback reachability and causal minimax to a quantized source-derived "
        "pursuit-evasion game. The figure shows forward states, projected convex envelopes, "
        "backward-winning intersections and a worst-case path in pursuer and evader position "
        "planes. Five fresh-process runtime observations describe this adapter on one machine. "
        "The four-stage action catalogues, capture radius, sequential response and zero-sum payoff "
        "signs are explicit analysis adaptations; this is not a continuous-action RL reproduction "
        "or a performance comparison."),
    "syn06-verifier": Family(
        r"syn06-verifier-\d{8}-[0-9a-f]{64}", "verification", "Trajectory verification",
        "Re-checks two literal two-stage integrator witnesses against the original saved input "
        "data and confirms the published trajectories numerically."),
    "perf03-ts01": Family(
        r"perf03-ts01-single-process-correlation-\d{8}-[0-9a-f]{16}", "verification",
        "Process-scoped CPU profile for T-S01",
        "A diagnostic CPU profile of the T-S01 path, kept apart from the published latency "
        "statistics and exported with symbol and paired-timing tables."),
}


def stylesheet() -> str:
    return Path(__file__).with_name("landing.css").read_text(encoding="utf-8")


def family_for(report_id: str) -> str:
    """Return the family whose registered pattern covers a published route."""
    matches = [key for key, family in FAMILIES.items() if re.fullmatch(family.pattern, report_id)]
    if not matches:
        raise ValueError("no landing description for report route: " + report_id)
    if len(matches) > 1:
        raise ValueError("ambiguous landing description for report route: " + report_id)
    return matches[0]


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def links_html(links) -> str:
    """Render a list of (label, href) pairs as separated links."""
    return " &middot; ".join('<a href="' + escape(href, quote=True) + '">' + escape(label) + "</a>"
                             for label, href in links)


def card(entry: Entry, number: int, heading: str) -> str:
    """Render one report card from its entry data and its family description."""
    family = FAMILIES[family_for(entry.report_id)]
    parts = ['<li><p class="eyebrow">' + escape(heading) + " &middot; " + f"{number:02}" + "</p>"]
    parts.append('<h3><a href="' + escape(entry.report_id, quote=True) + '/index.html">'
                 + escape(family.title) + "</a></h3>")
    parts.append('<p class="summary">' + escape(family.summary) + "</p>")
    if entry.scope:
        parts.append('<p class="card-scope"><strong>What was measured.</strong> '
                     + escape(entry.scope) + "</p>")
    if entry.limits:
        parts.append("<details><summary>Evidence limits</summary><p>" + escape(entry.limits) + "</p></details>")
    if entry.links:
        parts.append('<p class="card-links">' + links_html(entry.links) + "</p>")
    parts.append('<p class="card-provenance">Report ID<code>' + escape(entry.report_id) + "</code>")
    if entry.commit:
        parts.append("source commit<code>" + escape(entry.commit) + "</code></p></li>")
    else:
        parts.append("</p></li>")
    return "".join(parts)


def page(entries, extras=None) -> str:
    """Render the complete landing page for the given report entries."""
    groups = {}
    for entry in entries:
        family = FAMILIES[family_for(entry.report_id)]
        groups.setdefault(family.group, []).append(entry)
    cards = []
    number = 0
    for key, heading, introduction in GROUPS:
        items = groups.get(key)
        if not items:
            continue
        cards.append("<li><h2>" + escape(heading) + '</h2><p class="blurb">'
                     + escape(introduction) + "</p></li>")
        for entry in items:
            number += 1
            cards.append(card(entry, number, heading))
    extra_links = ""
    if extras:
        extra_links = ('<p class="hero-links" id="visual-examples-link">'
                       + links_html(extras) + "</p>")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>CSL algorithm reports</title><style>\n" + stylesheet() + "\n</style></head><body>"
            '<p class="eyebrow">Controlled Systems Lab &middot; research archive</p>'
            "<h1>Algorithm reports</h1>"
            '<p class="lede">This is the published archive of measured algorithm results. Every '
            "entry names the algorithm family, explains in plain language what the report "
            "measures, repeats the scope and the evidence limits recorded with the report, and "
            "links to the report page, its raw records, its measured tables and its offline "
            "bundle.</p>"
            '<p class="meta">' + f"{len(entries)}" + " published reports &middot; versioned and "
            "reproducible &middot; numerical observations, not mathematical certificates</p>"
            + extra_links +
            '<div class="note"><p><strong>Read the evidence, not just the numbers.</strong> '
            "Measurements do not imply cross-method performance, application-scale results or "
            "mathematical certification. Each report states its own measured scope and its own "
            "limits; open a report before drawing a conclusion from it.</p></div>"
            '<div class="section"><h2>How to read this archive</h2><dl>'
            "<div><dt>Plain-language summary</dt><dd>What the algorithm family does and what this "
            "report measures, written for a reader who has not read the report yet.</dd></div>"
            "<div><dt>What was measured</dt><dd>The scope recorded with the report: the fixtures, "
            "the calls and the outcomes it covers.</dd></div>"
            "<div><dt>Evidence limits</dt><dd>What the report states it does not establish. These "
            "limits are part of the result, not a disclaimer attached to it.</dd></div>"
            "<div><dt>Links</dt><dd>The report page, the raw JSON record, the measured tables, the "
            "offline bundle and, where they exist, the visual examples and figures.</dd></div>"
            "<div><dt>Report ID and source commit</dt><dd>The exact published route and the source "
            "commit that produced it, so any number can be traced back to one code state.</dd></div>"
            "</dl></div>"
            '<div class="section"><div class="cards"><ul>' + "".join(cards) + "</ul></div></div>"
            '<div class="footer"><p>Controlled Systems Lab &middot; Numerical observations are '
            "not mathematical certificates.</p></div></body></html>")


class Node:
    def __init__(self, tag: str, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list = []


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

# Separators used by the staging scripts between the parts of an index entry.
SEPARATORS = re.compile(r"^[\s\u00b7\u2014\u2013\-,;.:]+|[\s\u00b7\u2014\u2013\-,;.:]+$")


class Tree(HTMLParser):
    """Minimal HTML tree builder used to read an assembled index page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def elements(node: Node, tag: str | None = None, cls: str | None = None):
    for child in node.children:
        if isinstance(child, Node):
            if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get("class", "").split()):
                yield child
            yield from elements(child, tag, cls)


def text(node: Node) -> str:
    parts = []
    for child in node.children:
        parts.append(child if isinstance(child, str) else text(child))
    return "".join(parts)


def entry_of(item: Node) -> Entry:
    """Read one assembled index item into a landing entry."""
    anchors = [(node.attrs.get("href", ""), collapse(text(node))) for node in elements(item, "a")]
    reports = [anchor for anchor in anchors if re.fullmatch(r"[^/]+/index\.html", anchor[0])]
    if not reports:
        raise ValueError("index item without a report link")
    report_id = reports[0][0][: -len("/index.html")]
    codes = [collapse(text(node)) for node in elements(item, "code")]
    commits = [code for code in codes if re.fullmatch(r"[0-9a-f]{7,40}", code)]
    link_items = next(iter(elements(item, "p", "card-links")), None)
    if link_items is not None:
        links = tuple((collapse(text(node)), node.attrs.get("href", "")) for node in elements(link_items, "a"))
    else:
        links = tuple((label, href) for href, label in anchors if href != reports[0][0])
    scope_node = next(iter(elements(item, "p", "card-scope")), None)
    details = next(iter(elements(item, "details")), None)
    if scope_node is not None:
        scope = collapse(" ".join(child if isinstance(child, str) else text(child)
                                 for child in scope_node.children
                                 if not (isinstance(child, Node) and child.tag == "strong")))
        limits = collapse(" ".join(text(node) for node in elements(details, "p"))) if details is not None else ""
    else:
        parts = []
        for child in item.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag in ("a", "code"):
                continue
            else:
                parts.append(text(child))
        description = SEPARATORS.sub("", collapse(" ".join(parts)))
        description = re.sub(r"\s*source$", "", description)
        scope, _, limits = description.partition("; limits: ")
        limits = SEPARATORS.sub("", limits)
        if not scope and reports[0][1] and reports[0][1] != report_id:
            # Some staged routes carry their description in the link label itself.
            scope = reports[0][1]
    return Entry(report_id=report_id, scope=scope, limits=limits,
                 commit=commits[-1] if commits else "", links=links)


def parse_index(html: str):
    """Read an assembled index page into landing entries and extra page links."""
    tree = Tree()
    tree.feed(html)
    lists = list(elements(tree.root, "ul"))
    if not lists:
        raise ValueError("published index has no report list")
    entries = []
    for item in elements(lists[0], "li"):
        if any(isinstance(child, Node) and child.tag == "h2" for child in item.children):
            continue
        entries.append(entry_of(item))
    extras = []
    for node in elements(tree.root, "p"):
        if node.attrs.get("id") != "visual-examples-link":
            continue
        for anchor in elements(node, "a"):
            extras.append((collapse(text(anchor)), anchor.attrs.get("href", "")))
    return entries, extras


def recorded(site: Path, report_id: str) -> dict:
    """Read the scope, the limits and the source commit recorded with a report."""
    for name in ("report-envelope.json", "records.json", "record.json", "publication-manifest.json"):
        path = site / report_id / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        found = {}
        for field in ("measured_scope", "scope", "evidence_scope"):
            value = data.get(field)
            if isinstance(value, str) and value:
                found["scope"] = value
                break
        for field in ("evidence_limits", "limits"):
            value = data.get(field)
            if isinstance(value, str) and value:
                found["limits"] = value
                break
            if isinstance(value, list) and value:
                found["limits"] = " ".join(str(item).strip() for item in value)
                break
        value = data.get("source_commit")
        if isinstance(value, str) and value:
            found["commit"] = value
        if found:
            return found
    return {}


def validate(page_html: str, site: Path) -> None:
    """Reject links that leave the staged site or point at missing files."""
    tree = Tree()
    tree.feed(page_html)
    for anchor in elements(tree.root, "a"):
        href = anchor.attrs.get("href", "")
        if not href or href.startswith("#"):
            continue
        if href.startswith("https://github.com/butahlecoq/controlled-systems-lab/"):
            continue
        if href.startswith(("http://", "https://", "//")):
            raise ValueError("landing page links outside the staged site: " + href)
        target = (site / href).resolve()
        if site.resolve() not in target.parents or not target.is_file():
            raise ValueError("landing page links to a missing staged file: " + href)


def build(site: Path) -> None:
    """Replace the assembled index with the readable landing page."""
    site = Path(site)
    index = site / "index.html"
    entries, extras = parse_index(index.read_text(encoding="utf-8"))
    detailed = []
    for entry in entries:
        details = recorded(site, entry.report_id)
        detailed.append(Entry(report_id=entry.report_id,
                              scope=details.get("scope", entry.scope),
                              limits=details.get("limits", entry.limits),
                              commit=details.get("commit", entry.commit),
                              links=entry.links))
    pilot = "mpc03-open-loop-pilot-v1"
    if (site / pilot / "index.html").is_file():
        detailed = [entry for entry in detailed if entry.report_id != pilot]
        details = recorded(site, pilot)
        detailed.append(Entry(
            report_id=pilot,
            scope=details.get("scope", "One synthetic two-stage scalar formulation cross-check"),
            limits=details.get("limits", "Numerical outcomes only; no timing or comparison claim"),
            commit=details.get("commit", ""),
            links=(("Full result record", pilot + "/record.json"),
                   ("Raw executable output", pilot + "/pilot-output.json"),
                   ("Build provenance", pilot + "/build-provenance.json"))))
    b08 = "mpc03-b08-l04-miQCP-v1"
    if (site / b08 / "index.html").is_file():
        detailed = [entry for entry in detailed if entry.report_id != b08]
        details = recorded(site, b08)
        detailed.append(Entry(
            report_id=b08,
            scope=details.get("scope", "Four-step B08 displayed-data MIQCP and convex-control bound"),
            limits=details.get("limits", "No historical reproduction or solver-speed claim"),
            commit=details.get("commit", ""),
            links=(("Full result record", b08 + "/record.json"),
                   ("Raw solver output", b08 + "/solver-output.json"),
                   ("Independent exact oracle", b08 + "/independent-oracle.json"))))
    for report_dir in sorted(site.glob("mpc05-causal-tree-[0-9a-f]*")):
        report_id = report_dir.name
        if (report_dir.is_symlink() or not report_dir.is_dir()
                or not re.fullmatch(r"mpc05-causal-tree-[0-9a-f]{20}", report_id)
                or not (report_dir / "index.html").is_file()):
            continue
        detailed = [entry for entry in detailed if entry.report_id != report_id]
        details = recorded(site, report_id)
        detailed.append(Entry(
            report_id=report_id,
            scope=details.get("scope", "Finite Bellman and full scenario-tree comparison on strict-gap and TwoPoints fixtures"),
            limits=details.get("limits", "Three-stage finite-catalogue adaptation; no continuous RL or performance claim"),
            commit=details.get("commit", ""),
            links=(("Full result record", report_id + "/result.json"),
                   ("Phase-plane data", report_id + "/figure-data.json"),
                   ("Offline report bundle", report_id + ".zip"))))
    rendered = page(detailed, extras)
    validate(rendered, site)
    index.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    build(args.site)


if __name__ == "__main__":
    main()
