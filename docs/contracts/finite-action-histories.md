# Finite action history cursor

`CSL::finite_action_histories` provides a bounded-prefix cursor over the ordered
catalogue-index histories of a `FiniteDomain`.

The cursor validates catalogue row dimensions and finite binary64 values when
prepared. It emits tuples in lexicographic order, with the final stage changing
fastest. Each tuple stores catalogue indices rather than action coordinates, so
equal-valued duplicate rows remain distinct choices. A zero-stage problem has
one empty history; a positive-stage problem with an empty catalogue has no
histories.

`take_prefix(max_histories)` returns at most the requested number of histories
and reports whether the complete inventory has been emitted. A zero-size
request does not advance the cursor. A prefix is only enumeration progress; it
does not establish feasibility, objective value, optimality, or completeness of
an optimal family. Callers must account for every page before making those
claims. Cursor order is deterministic for a fixed ordered catalogue and
horizon.

The cursor does not perform branch pruning, merging, optimization, or
verification. Future EXT-02 branch search must preserve each emitted history's
identity and use a separate verifier before publishing a complete family.
