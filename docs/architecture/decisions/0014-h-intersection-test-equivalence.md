# ADR 0014: Test H intersections by represented sets

Date: 2026-11-22
Status: Accepted

## Context

An H representation can contain redundant inequalities, and equivalent
halfspaces can use positively scaled coefficients. Comparing output rows
directly with one canonical row list would couple geometry tests to
representation details rather than the represented set.

## Decision

Test H-intersection results by set equivalence. For the rational triangle
fixture, verify that each expected vertex satisfies every returned inequality
and that each of the triangle's three facet halfspaces has a positively scaled
counterpart in the result. Allow additional redundant rows. Test row retention
separately where that behavior is part of the contract.

## Consequences

The test accepts redundant output rows and positive rescaling while still
checking both containment directions. It does not require preservation of
redundant input inequalities. Changes to row order or normalization do not
break the test when the represented set remains the same.
