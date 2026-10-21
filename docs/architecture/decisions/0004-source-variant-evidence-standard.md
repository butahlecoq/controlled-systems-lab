# ADR 0004: Evidence standard for selecting source variants

Date: 2026-10-21. Status: accepted for evidence classification under the
repository owner's delegated implementation authority. It does not authorize a
research run, select a canonical historical model, or change a published value;
those actions remain owner-bound as specified below.

## Context

The archive has encountered three different situations that can look like a
damaged transcription: the displayed B04 model excludes a published endpoint;
the printed R29 control representation is dimensionally incompatible with its
scalar recurrence; and exact optimization of the displayed B08 data differs
from the reported value while L13's disputed mixture constraint is unavailable
as text. A plausible nearby artifact or a numerically close result is not, by
itself, evidence that the source was transcribed incorrectly.

## Decision

### Evidence threshold

Classify a source as internally contradictory only when a reproducible
certificate follows from the identified source version and the contradiction
cannot be explained by its printed precision. Acceptable certificates are:

1. **Direct inconsistency:** an exact dimensional, algebraic, logical, or
   feasibility contradiction in the printed data.
2. **Invariant separation:** an exact invariant or bound implied by the
   printed model excludes a printed claim by a margin larger than the maximum
   effect of all stated rounding intervals.
3. **Independent artifact identification:** a separately archived,
   independently identified artifact is shown to match the disputed
   construction field by field. This identifies a candidate variant; it does
   not prove that the article used it unless provenance links the artifact to
   that experiment.

A certificate must record the source identifier and hash, page/table/equation
locations, exact inputs and arithmetic, printed decimal precision, derived
rounding radii, and the certificate margin. If any premise is inferred or
unavailable, label it as such and keep the conclusion conditional. Plausibility,
floating-point proximity, solver output, sampled agreement, and visual
similarity are not certificates.

### Variant and result handling

- Keep supplied values, published results, archived artifacts, and repository
  interpretations in distinct records with their provenance and immutable
  source labels.
- A corrected or inferred reference gets a new scenario identifier. Preserve
  the published row as context and report only the result for the explicitly
  defined reference. Do not claim reproduction, correction of the article, or
  recovery of author intent without the corresponding evidence.
- If a certificate contradicts a saved artifact rather than the printed
  source, scope the finding to that artifact and its derivation. Do not transfer
  the contradiction to the article or other artifacts.
- The article's printed data and matrices remain the authority for a
  displayed-data reference; its reported numbers remain claims to test. A
  mismatch establishes disagreement under the stated reference inputs, not
  that the article's result is wrong.
- Do not silently normalize inputs, replace published values, widen tolerances
  after seeing a result, or promote a candidate artifact to canonical status.

### Sign-off and assumptions

The group may classify evidence under this standard, derive exact consequences
of explicitly named inputs, and create a distinctly named reference variant
when its assumptions are fully recorded. The assumption register must identify
each inferred input, its source and rationale, the affected conclusions, and
what evidence would resolve it.

Owner sign-off is required to assert author intent; adopt a candidate as the
canonical historical source; alter a frozen historical manifest or published
interpretation; introduce a corrected bound or input not determined by the
source; or authorize a research run on a disputed/corrected scenario. Private
source access or owner-controlled records cannot be inferred from public
transcriptions. Until sign-off arrives, the record stays provisional and any
run remains unauthorized.

## Retrospective application

### B04 / L11

The [exact B04 variant diagnosis](../../research/b04-model-variant-diagnosis.md)
and its cited [consistency audit](../../research/b04-restoration.md) give
terminal stock-plane functional
`-2122.7`; the published endpoint gives `-406.201`. The exclusion margin is
`1716.499`, far above the `0.0145` rounding radius. This is an invariant
separation certificate that the displayed model and endpoint cannot both be
correct under the stated transcription. The printed terminal criterion still
evaluates to the published objective, but that does not repair the feasibility
contradiction. A39/A01/A40 provide an independently archived candidate variant
with corroborating recurrence and endpoint evidence; its historical generator
and canonical status remain unestablished. Keep `B04-historical` frozen and
non-executable. The owner-authorized `b04-reference-v1` and any corrected-track
run remain separate, named work and do not change the historical result.

### R29

The printed scalar recurrence and four-component control-zonotope
representation do not have compatible dimensions at the control multiplication
boundary. This is a direct structural inconsistency in the printed
representation. The [scalar-input construction](../../research/r29-corrected-scalar-reference.md) in
`r29-corrected-scalar-reference.md` is explicitly an inferred reference
motivated by the printed recurrence, scalar bound, and input-matrix shape; its
exact derivation does not establish author intent, recover the historical
implementation, or authorize replacing the printed representation.

### B08 / L04 and B09 / L13

For B08, the [exact displayed-data audit](../../research/b08-displayed-exact-audit.md)
establishes by exact enumeration of the printed rational data a
three-way minimax tie with minimum norm approximately `67.15060110140489`,
while the reported value is `67.12`. At two printed decimal places, the
reported value's conservative nearest-rounding interval is
`[67.115, 67.125]`. The exact squared minimum
`112730080707/25000000` exceeds `67.125^2` by
`42970041/12500000`; its square root is approximately
`0.0256011014` above the interval's upper endpoint. This proves a mismatch
for the `b08-displayed-rational-v1` reference. The unrounded source arrays
and original implementation are missing, so their possible precision and
semantics are not ruled out; this evidence does not establish a damaged
transcription or explain the published result. Keep both values and their
evidence labels unchanged.

For L13, the [variant diagnosis](../../research/b04-model-variant-diagnosis.md#related-finding-where-the-7-constraint-lives)
records that the text layer says the mixture deviation is at most 7% of nominal
`K`, but the constraint formula is an image not recovered in the available
text. The initial `dK=-0.075` would violate an absolute `0.07` bound by
`0.005`, but not a relative `0.07K=0.175` bound. Since the formula image and
corrected value are unavailable, neither reading is a source certificate.
Preserve the owner's statement that the printed figure is erroneous; the
corrected value, affected cases, and any use of the constraint remain
owner-bound and unresolved.

## Consequences

Research notes and machine-readable records must separate source facts,
derived certificates, assumptions, and owner decisions. A disagreement can
advance a clearly labelled reference without changing the historical record.
This standard does not close the outstanding recovery issues or authorize
additional execution.

## Alternatives considered

- **Choose the most plausible archived variant.** Rejected because similarity
  does not establish which artifact generated a published experiment.
- **Treat every reported-value mismatch as source damage.** Rejected because
  missing precision, mappings, or implementation details can explain a
  mismatch without contradicting the printed source.
- **Resolve conflicts by tolerance adjustment.** Rejected because it makes the
  acceptance rule depend on the observed answer.
- **Wait for complete historical recovery before classifying any evidence.**
  Rejected because exact contradictions and explicitly scoped references can
  be useful while preserving unresolved provenance and owner decisions.
