# Finite and mixed action families

## Problem

The finite-history cursor preserves catalogue-row identity, and the fixed-plan minimax solver evaluates every finite control plan against all admitted disturbance histories. Neither returns the nominal joint trajectory family required by `StrategyPort`. Strategy B builds such a family for supported continuous-control profiles, but it rejects `FiniteDomain` and `MixedDomain` inputs.

EXT-02 needs one complete relation for all optimal finite histories. A mixed-control history also needs the entire continuous optimal family for that history. The union of those branch relations can be nonconvex, so one ordinary H-polyhedron cannot represent it without changing the control domain.

## Target use

The caller uses the existing `StrategyPort` request to synthesize a complete family. The family names a finite-branch-union representation. A page reader returns the catalogue-index history and the original-coordinate relation for each branch.

```cpp
auto outcome = strategies.solve(request, context);
const auto& family = require_complete_family(outcome);

auto page = finite_branch_page(family, FiniteBranchCursor{}, 32);
for (const auto& branch : page.branches())
    render(branch.history(), branch.relation());
```

The fixed-plan robust minimax call remains separate. It returns scalar plan values and minimizing catalogue indices. It does not publish a nominal trajectory family.

## Relation shape

Use one immutable `JointRelation` payload for the nonconvex union. The payload stores one entry per complete `FiniteActionHistory`. Each entry contains a branch relation in the parent problem's canonical coordinates.

```cpp
struct FiniteBranchEntry {
    FiniteActionHistory history;
    sets::SetData relation;
};

class FiniteBranchUnionPayload final : public JointRelationPayload {
public:
    std::span<const FiniteBranchEntry> branches() const noexcept;
    const sets::SetData* h_relation_for_recording() const noexcept override;
};

struct FiniteBranchCursor { std::size_t next_index; };
struct FiniteBranchPage {
    std::span<const FiniteBranchEntry> branches;
    std::optional<FiniteBranchCursor> next;
};

std::variant<FiniteBranchPage, Diagnostics> finite_branch_page(
    const OptimalFamily&, FiniteBranchCursor, std::size_t page_size);
```

`JointRelation::coordinates` and every branch relation use the original order `[x0, ..., xT, u0, ..., u(T-1)]`. For a mixed domain, each `u[t]` is ordered `[continuous, discrete]`, as declared by `MixedDomain`. A branch relation fixes every discrete coordinate to the selected catalogue value. It retains every state and continuous-control point in that branch's optimal family.

To build a branch, split each dynamics matrix as `B[t] = [Bc[t] Bd[t]]`. For discrete action `d[t]`, solve the continuous subproblem with matrix `Bc[t]` and offset `b[t] + Bd[t] d[t]`. Lift the resulting relation back to the parent coordinates by inserting the fixed discrete values and their equality rows. The lift preserves stage dependencies. It does not take a convex hull across branches.

The relation representation ID identifies a finite union, not an H-polyhedron. `h_relation_for_recording()` returns `nullptr`. A writer that accepts only one H-relation must refuse this family. A multi-branch archive format needs its own contract before publication.

## Completeness and limits

The strategy uses `FiniteActionHistoryCursor` to cover the full ordered catalogue product, including duplicate-valued rows and the single empty history at horizon zero. The first implementation enumerates every history. It does not prune histories or merge search nodes.

The registered complete-family verifier checks the parent request and catalogue identity, the full history inventory, each branch's source-to-parent coordinate lift, each continuous family, and the global optimum across branches. It publishes through the existing `StrategyRegistry` and `FamilyPublisher` authority. It adds no verifier port or second family outcome.

The verifier cannot use a tie tolerance alone to prove that a branch is mathematically optimal. It needs an independent result for each branch and sound evidence that every omitted branch is strictly worse or infeasible. If objective bounds overlap, the result remains incomplete or unsupported. A finite prefix never becomes a complete family.

The first profile should admit only the nominal, discrete-time, known-initial, no-external-input cases whose branch solver and verifier support complete continuous families. It should reject unsupported temporal constraints, dynamics, objectives, and set representations at capability admission. The finite-action minimax solver continues to use its global disturbance maximum and its own result type.

## Alternatives

One relaxed H-polyhedron would admit fractional catalogue choices. It does not preserve a finite control domain. A separate public portfolio result would duplicate family publication, identity, and verification rules. One mixed-integer solve would depend on backend support for every optimal discrete assignment and every continuous face, which the current providers do not guarantee.

## Implementation order

1. Build one mixed branch and verify that its lifted H-relation matches the source equations in canonical coordinates.
2. Add the registered StrategyPort implementation and verifier for a small analytic profile.
3. Check duplicate action rows, tied branches, continuous ties within a branch, empty catalogues, zero horizon, cancellation, and unsupported profiles with independent oracles.
4. Add multi-branch persistence before publishing this representation in reports.
