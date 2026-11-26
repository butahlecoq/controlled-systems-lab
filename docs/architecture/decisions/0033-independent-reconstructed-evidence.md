# ADR 0033: Keep reconstructed synthesis evidence independent and explicitly scoped

Date: 2026-11-26
Status: Accepted

## Context

Synthesis and reachability verifiers can confirm a result by reusing the same
production composer, joint-relation builder, or adapter-provided report that
produced it. That can reproduce a defect in the implementation rather than test
the represented object. Provider evidence also has a narrower scope than the
authored model: a projection theorem about compiled binary64 rows does not
prove equality with the authored real-valued dynamics, and a replaceable
verifier can omit or rewrite operation and provider lineage.

## Decision

- Reconstruct hybrid path relations directly from the model's stage data for
  independent verification. Do not call the production joint-H composer or use
  its trace as the oracle.
- Assemble projected-reachability factors from the admitted inputs so that
  projection evidence does not depend on the model relation composer. Keep the
  public coordinate order of the one-step relation at the assembly site.
- Populate report operation and provider lineage from admitted
  program/candidate inputs, not from the replaceable verifier. An adapter may
  not omit or rewrite that lineage.
- Treat provider projection evidence as applying to the compiled binary64 joint
  rows it was established for. It does not certify that those rows equal the
  authored dynamics pullback over reals; leave predecessor support unestablished
  rather than upgrading the original claim.

## Consequences

Independent reconstruction can disagree with the production composer and expose
a defect, at the cost of maintaining a second construction. Reports retain
lineage that a verifier cannot silently change, and predecessor evidence stays
explicitly scoped to the compiled rows it covers.
