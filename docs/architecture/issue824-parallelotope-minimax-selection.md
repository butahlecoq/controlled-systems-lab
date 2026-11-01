# Parallelotope candidate selection for fixed-plan minimax

`finite_action_parallelotope_minimax` enumerates finite open-loop action plans,
propagates each plan through the fixed-frame four-state parallelotope
recurrence, and evaluates the terminal objective at all 16 frame-box corners.
It selects the smallest numerical candidate score and separately replays that
plan through all finite disturbance histories.

The score is an estimate over the represented enclosure. It is not a
validated objective bound, proof of minimax optimality, or realizable witness.
Only the selected finite-history replay supplies a realizable plan and its
worst disturbance witness. Candidate-search coverage says whether every plan
received a score; it does not establish optimizer-family completeness.

Each attempt is retained as scored, unsupported, or stopped. If an attempt
cannot be scored, the search is marked incomplete while any scored candidates
remain available. A cancellation, deadline, or candidate-attempt limit retains
the interrupted/next plan as a stopped attempt. Request-wide identity,
catalogue, dimension, and plan-count errors return `Unsupported`.

The initial profile supports only the existing four-state fixed frame,
bounded V or singleton initial/disturbance sets, universal state constraints,
finite action catalogues, and binary64 numerical assurance. There is no
orientation optimization, predecessor operation, ellipsoid path, feedback
policy, or two-dimensional parallelotope selector in this API. The TwoPoints
report records all candidate rows and the selected plan replay. Its figures
remain projections of the actual four-dimensional stage trace.

Candidate corner scoring is constant at 16 corners for this fixed four-state
frame. Plan enumeration, initial/disturbance vertex counts, replay histories,
and candidate attempts remain bounded by caller limits. An input vertex-count
refusal is retained as an unscored row for each affected plan. The selector does not add a
performance-winner claim; the report's repeated timings are descriptive and
lack a profiler-confirmed limiter.
