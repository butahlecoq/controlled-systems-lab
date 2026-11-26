# ADR 0028: Separate terminal-relation recovery from optimization

Date: 2026-11-22
Status: Accepted

## Context

`recover_joint_history` receives a resolved problem and a caller-supplied
terminal-state relation. The resolved problem includes an objective, but this
operation constructs the feasible history preimage of the supplied relation;
it does not optimize the objective or determine whether the terminal relation
is a minimizer set. Treating recovery as an optimizer would blur the boundary
between the strategy that selects a terminal relation and the operation that
lifts it into state/control coordinates.

## Decision

- Keep terminal-relation selection outside `recover_joint_history`. The caller
  supplies the relation to embed at the final state coordinates; recovery
  combines it with the initial point, state/control constraints, and dynamics.
- If a caller needs optimal histories, it must supply the terminal minimizer
  relation established by its optimization step. Recovery preserves the
  feasible preimage of that relation without claiming to establish optimality.
- Describe finite witness tests as sampled membership checks. A collection of
  feasible histories does not by itself prove that the returned relation is
  complete or is the full minimizer family.

## Consequences

The API composes a terminal-relation producer with a history-lifting
operation. Optimality and completeness claims must be supported by the
producer's evidence and the applicable relation checks, rather than inferred
from successful history recovery.

## Terminal minimizer completeness (2026-11-26)

`terminal_minimizers` records a program's bounds and mathematical outcome but
does not infer that the selected terminal slice is the complete minimizer set.
A completed program result establishes a program-scoped optimum. Completeness of
the terminal minimizer relation requires separate relation evidence, so the
reported support stays unestablished unless that evidence is supplied.
