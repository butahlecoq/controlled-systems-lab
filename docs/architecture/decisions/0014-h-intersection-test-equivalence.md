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
and that each of the five defining input inequalities has a positively scaled
counterpart in the result. The five input inequalities include two that are
redundant for the triangle; they are not all facets.

## Consequences

The test accepts redundant output rows and positive rescaling while still
checking both containment directions. Changes to row order or normalization do
not break the test when the represented set remains the same.
