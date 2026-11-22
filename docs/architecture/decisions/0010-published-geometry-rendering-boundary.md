# ADR 0010: Keep geometry validation in the publisher

Date: 2026-11-22. Status: accepted.

## Context

The [native fixed-tail geometry publisher](../../../scripts/reports/native_fixed_tail_geometry.py)
combines authenticated saved episode archives with projected set data, then
offers an interactive browser view in [`geometry.js`](../../../scripts/reports/assets/native-fixed-tail-geometry/geometry.js).
The browser code selects stages and coordinate planes and draws the supplied
points. It is not an independent checker for the mathematical claims behind
those points.

## Decision

The publisher validates archive identity, task and run identity, complete
state-stage coverage, full-state carrier containment, and saved projection
coordinates before it emits the geometry data used by the page. The browser
renderer consumes that publisher-validated data and only provides a visual
reading interface.

## Consequences

Changes to the browser renderer must not be described as revalidating a set or
certifying a control result. Changes to the publisher keep the source-record,
containment, and projection checks at the publication boundary. The regression
coverage in [`test_native_fixed_tail_geometry.py`](../../../tests/reporting/test_native_fixed_tail_geometry.py)
exercises these checks. The page may explain that validation boundary, while
the renderer remains free of comments that repeat the same guarantee.
