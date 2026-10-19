# APP-03 zonotope reduction design

Issue: [APP-03 #42](https://github.com/butahlecoq/controlled-systems-lab/issues/42).

## Outcome and scope

Provide two registered binary64 methods for native generator sets. An exact
conversion removes physically zero generators from an unconstrained zonotope.
An outer approximation meets a requested generator budget by retaining source
factors and replacing removed generators with independent coordinate-axis
interval factors. The same outer construction accepts constrained inputs but
explicitly relaxes their factor equalities. Neither method claims validated
rounding error bounds, a recovered control witness, or an optimal family.

## Interfaces and identities

`include/csl/geometry/zonotope_reduction.hpp` declares the conversion and
approximation registrations. The exact method uses `ConversionPort`, requests
`csl.zonotope`, and emits an equivalent physical-set claim. It removes only
columns whose every stored binary64 coefficient is zero; no factor equality is
allowed. The outer method uses `ApproximationPort`, requests `csl.zonotope` and
`outer`, and records source factor count, generator budget, retained factor
count, produced factor count, and whether constraints or shared factor
dependencies were relaxed. Both preserve coordinate labels and immutable
request/reference identities.

## Outer construction and independent admission

The producer deterministically orders generators by descending maximum
coordinate magnitude with input order as a tie break. It tries the largest
retained prefix that fits the budget after one axis factor is allocated for
each coordinate touched by a removed generator. A retained column keeps its
source `FactorId` and exact stored coefficients. Axis factors have fresh IDs
and one nonzero coefficient each, rounded outward from the exact sum of
absolute removed coefficients. If no admissible budget exists, the method
returns unsupported. Constraints in the source are relaxed; the output has
none. New factor IDs are scoped by the complete request and source identity,
with length-prefixed components, and cannot collide with source IDs.

The approximation policy reconstructs the claim independently from immutable
native handles. It requires matching centers and coordinate labels, no output
factor equalities, identical retained columns by `FactorId`, and only axis
columns for new IDs. It compares each axis radius with the exact dyadic sum of
absolute coefficients of source columns omitted from the output. This proves
physical-set inclusion for the mathematical sets defined by the stored
binary64 coefficients. The policy counts output generator columns against the
requested budget. It rejects a false provider enclosure instead of trusting
the producer's evidence text. This check does not certify the effect of
rounding in earlier operations.

## Tests, publication, and limits

Contract tests use analytic 1D and 2D support values, an independent finite
corner inclusion oracle, constrained and shared-factor cases, zero columns,
insufficient budgets, unsupported directions, forged provider results,
cancellation, and installed public use. A small saved 2D result gets an HTML
report, raw records, source/build receipts, offline bundle, and discoverable
labelled plot through the existing main-only publication workflow. Timings are
descriptive single-adapter measurements; no comparison or scalability claim
is inferred. A04 and the owner zonotope paper are compared only where their
source assumptions are resolved; unresolved historical claims are recorded
without fabricating a result.
