# OPT-07 grouped hull reduction contract revision

Status: implementation contract for PR #443, based on the accepted OPT-07
scope. This refines the ordered/grouped hull adapter row in the class-level
architecture spec; it does not add recursive divide-and-conquer.

## Source behavior and native boundary

The checked archival inventory identifies two different QLPHULL programs.
`Scientific Research/QLPHULL.m` sorts by `abs(max((p-d)./r))` and leaves its
proposed grouping block commented out. The Constrained variant sorts by
`max(abs((p-d)./r))`, streams appended candidates, activates a grouping stage
after ten consecutive redundant classifications, tests the remainder against
fixed `Ck` plus accumulated nearby `Cj`, restores `Ck`, and runs a final
reduction. The two scores are not interchangeable. The Constrained source's
`itrt` remains zero because pivot accumulation is commented out.

The C++ adapter is a hull-level reduction strategy, separate from LP pivot
selection and recursive QuickHull. It uses the Constrained score with stable
input-order ties and preserves original point IDs. It starts with the first two
ordered points and streams candidates against the current retained set. A
candidate is filtered only after the shared LP query yields a valid program
identity and an exact dyadic convex-combination certificate. Ten consecutive
certified removals trigger one grouped remainder pass. That pass rechecks the
tenth candidate and every later candidate against fixed streamed survivors plus
unique prior outside candidates within `0.05 * min(coordinate_widths)` Euclidean
distance. Outside or uncertain candidates are retained. A final shared LP
reduction runs over all survivors, and the common certificate-composition check
revalidates early removals against that final retained set.

The native implementation replaces both historical simplex tableaus with the
shared LP membership backend. It does not claim MATLAB tableau/runtime parity.
If score arithmetic is unsafe or any coordinate width is zero, it uses input
order, continues certified streaming, and skips the historical grouping
trigger. Empty/singleton/zero-dimensional and malformed inputs retain the
existing shared reducer behavior.

## Result metrics and evidence

`HullReduction::grouped` is present only for this strategy. It records the full
processing order, streamed candidate count, certified stream removals, whether
the ten-removal trigger ran, grouped remainder query count (including the
trigger candidate), unique nearby supports, zero-width coordinates and unsafe
ordering fallback. Shared `lp_calls` and `attempts` include stream, group and
final-reduction queries. LP pivots and recursive split counts are not reported.

Tests compare every permutation of bounded grouped and flat/duplicate fixtures,
exercise the trigger over every permutation of the square's four tied outer
points, check support values, and verify every removal certificate exactly.
Overflow fallback uses a stopping workspace to establish that original input
order reaches the shared reducer. These tests establish represented-binary64
hull preservation for the checked fixtures; they do not establish source
runtime parity or performance.
