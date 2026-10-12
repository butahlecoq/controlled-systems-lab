# H-polyhedron intersection and halfspace reduction

`<csl/geometry/polyhedral_intersection.hpp>` and `CSL::polyhedral` provide
single-set H operations. `intersect_h(left, right, id)` accepts native H data
with equal ambient dimensions and identical coordinate labels/order. It
concatenates the authored inequality rows and, separately, the authored affine
equality rows. It never converts an equality into two inequalities, infers
feasibility, or removes rows. Empty results remain valid H descriptions; for
example, `x <= 0` intersected with `x >= 1` is stored as contradictory rows.

To enumerate vertices created where faces cross, pass the returned H set to the
existing selected conversion provider and request `csl.polyhedron.v`. The
converter sees the full conjunction, so it does not rely on retaining vertices
from either input. Conversion currently supports its documented bounded
binary64 profile and may return `Unsupported` outside that profile. This
operation does not itself construct a V description.

`remove_redundant_halfspaces` visits inequalities in input order, solving an
implication LP for each candidate against all currently retained inequalities
and all affine equalities. To test `a_i*x <= b_i`, it minimizes `-a_i*x` over
the other constraints. A candidate is removed only when the completed result
belongs to the exact generated program, carries a supported finite lower bound
`L` for that program, and the computed upper bound `-L-b_i` is finite and
nonpositive. Both the outcome and bound must carry `NumericalCheck` support.
A primal witness, symbolic or certificate-reference metadata, optimal status
without a bound, unsupported evidence, infeasibility, unboundedness, a stopped
query, or malformed result never deletes a row. Rows whose implications are
unresolved remain in the output and make the reduction status `incomplete`. This includes all rows when
the selected LP adapter does not publish objective bounds (as the current
HiGHS adapter does).

The output preserves every equality unchanged and retains the original order of
all kept inequalities. Returned retained/removed indices refer to the original
inequality list. There are no implicit variable bounds. Each call handles one
state set; callers keep the model's `T+1` state entries, including the terminal
entry, and invoke the operation per entry when appropriate.

The implication check relies on the selected LP provider's supported lower
bound claim. The structural checker verifies identity, support metadata and
finite values, not the provider's proof or dual arithmetic. The final
nonpositivity comparison is strict binary64 arithmetic without tolerance
relaxation. This module therefore does not claim exact or validated geometry;
ill-conditioned computations and false provider claims remain outside its
assurance. A future validated provider can be substituted without changing the
operation interface.
