# Portable run statistics

`CSL::artifacts` publishes immutable scenario records and reads/writes the closed
`csl.run-statistics/4` format plus inert recorded-artifact formats v5 and v6.
Version 6 retains the applied relation in each span descriptor; v5 remains
readable for existing records. Include `csl/artifacts/run_statistics.hpp` for
records and `csl/execution/observability.hpp` for bounded collection and RUN01
projection. These additions preserve mathematical identity version 1. The
problem-aware publication boundary uses the existing trajectory verifier; it
does not introduce a solver, estimator, timer instrumentation, or scenario
planner.

## Publication and identity

Resolve an actual problem through MODEL03 and an already selected effective
`ConfigurationInput` through `resolve_configuration`. The configuration factory
checks complete selected module IDs/versions, options, selector, numerical and
resource requests, output, stop budget, workspace policy and all six collection
settings. It resolves no registry defaults. `publish_run(RunInput)` checks the
actual problem identity and full-history dimensions before publishing a deep
immutable owner. For synthesis results it also independently verifies each
claimed incumbent against the resolved problem, including the original objective,
before setting `problem_revalidated` provenance. An infeasible outcome that
conflicts with a verified feasible incumbent, or a bound that conflicts with its
verified objective, is rejected. `RunStatistics::description()` borrows while
that owner survives.
All producer strings, vectors, JSON and optional metadata may be destroyed or
changed after successful publication.

`decode_run(text, limits)` records a syntactically checked mathematical identity;
it sets provenance to `identity_recorded` and does not promote incumbent support
claims to verified feasibility. It cannot establish what absent external problem
bytes mean. The overload taking an actual `ResolvedProblem` routes synthesis
incumbents through the independent trajectory check before returning
`problem_revalidated`. Neither reader creates a callable workspace, valid NVI
stamp, executable family, exception pointer, solver registration or a
mathematical certificate.

Configuration identity is `csl.config.v1.sha256:` plus 64 lowercase hexadecimal
digits. The canonical byte prefix is `CSL.RESOLVED.CONFIG`, NUL, `v1`, NUL, followed
by compact UTF-8 JSON with sorted object keys, selected roles and option names.
Integer values are canonical decimal strings. Configuration binary64 numbers use
16 lowercase IEEE-754 hexadecimal bits and retain signed zero. String control
bytes use lowercase `\u00xx`; there is no Unicode normalization. Ordered directions
and lists retain their order. Hashing uses MODEL03's content snapshot utility;
backend choice, configuration, run IDs and measurements never enter ProblemId.

A module pin is exactly available `{scope, sha256}` or unavailable
`{state:"unavailable", value:null, reason, detail}`. Supported scopes are
`source_archive` and `build_manifest`. Unavailable pin reasons are
`not_instrumented`, `not_exposed_by_adapter` and `not_applicable`. The required
UTF-8 detail has at most 256 encoded bytes. Only this explanatory unavailable-pin
prose is normalized to the empty string in the hash projection; faithful wire
serialization retains it. OBS01 does not relabel Git IDs as SHA256, fetch source
archives or assert that a recorded pin proves build provenance.

## Final mathematical data and availability

Portable final variants distinguish synthesis, program, unsupported, skipped and
failed results. Synthesis preserves canonical termination, outcome/evidence,
objective bounds, T+1 states, T controls and original objective values. Program
projection retains its canonical subject, primal, bounds, residual context and
raw diagnostics. Shapes and finite data are checked; serialization does not prove
feasibility, optimality, uniqueness, attainment, family completeness or numerical
reproduction.

A family record retains the source `FamilyIdentity` (resolved problem, effective
family request, joint coordinates, strategy/version and ordered transformation
lineage) and exactly one typed complete, partial or candidate product. The v4
run codec does not serialize the opaque live relation payload. With no exporter
its external family attachment is `unavailable_no_exporter`, while relation
metadata and evidence survive. Ordinarily `project_final` drops the live payload. For the
T-S01 profile it retains the exact relation object in the in-memory owner
because the typed capability binds that object; `encode_run` then refuses the
record under the v4 wire contract.
Generic complete- and partial-family publication remain fail-closed unless the
selected compiled verifier recognizes an exact profile. The dedicated T-S01
analytic complete-family profile remains a narrow live exception for the exact
two-step scalar integrator, exact known initial state 0, A=B=1, zero
offsets/external map, independent closed controls `[0,1]`, no extra
restrictions, and exact squared objective `(x2-1)^2`. A separate T-S01 partial
profile may publish only the singleton history `(0,1/2,1,1/2,1/2)` with scope
`s=1/2`; its independent partial-family verifier checks the exact resolved
objective/request, singleton H-representation and every-history optimality
evidence. It makes no complete-coverage claim and does not enable other partial
profiles. Both live capabilities are bound to the resolved problem, effective
request, coordinates, strategy/version and lineage. The v4 schema has no
T-S01 support tag, so `encode_run` returns `unsupported` for such a live family.
This is a wire-contract limitation, not a mathematical rejection. The decoder
never reconstructs trusted proof capability from text; the future generic
versioned verifier seam remains tracked in
[issue #202](https://github.com/butahlecoq/controlled-systems-lab/issues/202).

### Inert recorded artifacts v5

`encode_recorded_run` is a separate v5 archival path. For a live complete family
carrying registered completeness evidence, it requires the current-process
registry-verified family state and an owned, digest-checked
`csl.h-relation-attachment/1` family attachment. The concrete relation payload
exposes an optional inert H-data view for this exporter; it does not prove the
attachment is mathematically equivalent to the family claim. Schema, digest and
bytes establish archival encoding identity only. Unsupported payloads fail with
a typed error.

`decode_recorded_run` returns `RecordedRunArtifact`, an opaque owning v5 byte
value. It cannot convert to `RunStatistics`, `OptimalFamily`, `FamilyRecord` or
selector input. Import checks bounded canonical JSON, attachment content
integrity and, when supplied, the resolved problem identity. Its exact state
marker `unverified_recorded_data` is data, not a trust bit. Existing `encode_run`
and `decode_run` keep their v1-v4 behavior and reject v5 input. No replay
authority is implemented, so decoded claims remain archival data even when all
digests match.
Candidate feasibility is scoped to the whole relation, a named full-history
witness, or unknown; an outer enclosure with one feasible witness does not
claim whole-relation feasibility. Strategy results expose `IncumbentCandidate`
values, whose backend feasibility support is a claim. The portable
`SynthesisFinal::incumbents` values preserve that claim, but only a successful
problem-aware publication gives the enclosing record `problem_revalidated`
provenance. A late generated-request rejection retains request/provider
provenance, completed lineage and the scope of bounds, incumbents and candidate
or partial family that survived the stop. A separate contract-validation failure
retains the original stop record without inventing provider provenance. An external attachment is a digest/size/schema/media claim,
not an executable family or proof the referenced file exists. Supplied embedded
bytes are hashed and checked. Paths are relative artifact references without
absolute roots, drive prefixes, traversal or empty components; serialization
never opens them. Consumers select their own attachment root.

V3 requires stated support for retained objective bounds and checks each
incumbent's full-history shape against the run coordinates. When reading a V2
record, an `Unestablished` bound is dropped rather than promoted to supported
evidence. If a V2 stop scope refers to such a bound, migration is rejected
because rewriting the historical retained scope would invent provenance.

Every metric is exactly `{state:"available", value:...}` or
`{state:"unavailable", value:null, reason, detail}`. Available zero is retained.
Missing duration, iteration count, native execution observation or memory count
never becomes an observed zero. Evidence support reuses canonical unestablished,
numerical, symbolic and unchecked-certificate-reference variants. Requested
validated assurance can be recorded; applied validated assurance is rejected by
this publication profile. Equivalent/inner/outer/heuristic relation and numerical
assurance remain independent. A small residual does not create a relation proof.

## Clock and execution meanings

Clock records identify metric, scope, run-local origin, positive rational tick
period, resolution availability and calibration limitations. Tick intervals are
signed64 offsets from that origin, not parent-relative deltas. Observed endpoints
are nonnegative and ordered. A configured deadline may be negative. Differences
are checked before arithmetic can overflow; unavailable endpoints and overflow
have explicit reasons. Legacy `TimingSpan` binary64 absolute seconds remain a
separate `legacy_seconds` variant and are never silently rounded to ticks.

Nested same-clock children must lie within a known parent interval. Spawned
causal children may outlive their parent. Other clocks are not implicitly
comparable. Inclusive bucket totals are work sums, not end-to-end latency.
For the literal `[0,20]`, `[2,12]`, `[5,17]`, `[4,9]` intervals, work is 47 ticks
while the root interval is 20. Exclusive-time/child-union computation belongs to
OBS02.

`project_execution` consumes RUN01 post-join data and preserves configured
deadline, first admission-close cause/time, separately observed external
cancellation, workers joined and final completion. `project_task` preserves
queued/admitted/create/call/release observations against the same origin.
It performs no scheduling or timer sampling. Resource projection retains outer
admission enforcement, declared native thread limits and memory reservation
accounting; these are not hard OS thread/memory enforcement. A native observation
is returned, positively not called with source provenance, or unknown. No log
parser infers invocation from arbitrary diagnostic text.

## Bounded collection

Collection settings have six required fields: `enabled`, `mode` (`detail` or
`summary`), `plan_spans`, `plan_bytes`, `detail_spans`, `detail_bytes`. All remain
part of ConfigId, including dormant caps. Detail slots cannot exceed plan slots.
A disabled plan accepts no descriptors, clocks or shards and reports
`collection_disabled`; it makes no zero-call assertion. Summary mode keeps fixed
endpoints and summaries while variable detail is `not_requested`, with no fake
capacity drop. Zero detail caps in detail mode retain topology and report actual
`detail_limit` omissions.

A plan declares finite spans, parentage, clock/provenance metadata, shard ownership
and aggregate buckets. Required task and operation dictionaries contain unique,
nonempty labels; every descriptor resolves against those dictionaries. Selected
module provenance resolves against the immutable configuration at run publication.
Its immutable private owner token prevents shards from a
textually identical foreign plan entering a merge. One move-only shard belongs to
one producer; callers must join producers before moving shards into merge.
Duplicate and wrong-shard completion attempts do not overwrite first observations.
Missing shards leave incomplete records. Deterministic retention uses increasing
SpanId and fixed per-slot regions, never completion order.

`record(SpanCompletionView)` is noexcept and performs no allocation after shard
construction. It checks length before scanning/copying text. Oversize or invalid
detail finalizes the slot with a rejection disposition while fixed observations
remain explicit. `record_overflow` retains a saturating producer-declared count in
a fixed bucket, including one unclassified bucket; it retains no invented timing
or unbounded omitted-ID list. Counters carry exactness and duration-sum overflow
is unavailable/overflow. Math results are owned outside the collector and cannot
be changed by truncation, disabled collection or a record rejection.

The caps govern admitted plan/summary metadata and preallocated detail storage.
Checked native size arithmetic precedes proportional allocations. They do not
claim a hard process-heap bound covering allocator overhead, caller buffers,
final witnesses, native solvers or unrelated work. Final artifacts have separate
codec limits. Publication/encoding allocation failure returns an artifact error
and does not turn the caller's mathematical result into success or infeasibility.

### Portable metadata budget

`plan_bytes` admits a logical metadata size, independently of compiler ABI,
Debug STL layout, JSON formatting or allocator overhead. The private shared
accounting rule is normative for enabled collection at plan construction,
`publish_collection`, and wire decoding through publication. It walks borrowed
values without allocating, checks every unsigned64 addition, and rejects before
plan copies, optional-owner clones, validation maps or portability serialization.
A budget error has code `limit`, with path `plan.bytes` for setup or
`collection.plan_bytes` for publication/decoding.

The logical grammar counts every retained field of `CollectionRecord` recursively:

- Boolean and enum values cost 1 byte; signed/unsigned integers and binary64
  values cost 8 bytes, irrespective of their magnitude or printed spelling.
- A string costs an 8-byte length plus its UTF-8 **byte** length. Identifier
  wrappers count their string. An array costs an 8-byte count plus its elements.
- An optional or optional immutable pointer costs a 1-byte presence tag plus
  the present value. A variant costs a 1-byte alternative tag plus its active
  value. Empty alternatives cost zero beyond that tag. Structs sum their fields.
- `Metric<T>` therefore counts its alternative plus either the available value
  or the unavailable reason and detail string. All module/pin, program, geometry,
  representation-summary, clock, provenance, binding and dictionary text counts.
  Fixed span topology/status/availability fields, ten bucket exact counters,
  bucket clocks, completeness and all six effective collection settings count.
- Only an **available `SpanRecord::detail` string payload** is excluded from
  metadata bytes: its variant tag and length still count, while its actual
  UTF-8 payload is admitted against `detail_bytes` and `detail_spans`. Unavailable
  explanation text is metadata and cannot bypass the plan budget.

For example an enabled empty record with the 86-byte ProblemId, 85-byte ConfigId,
RunId `r`, five empty arrays, six settings and available completeness costs
`(8+86)+(8+85)+(8+1)+34+5*8+2 = 272` bytes. Cap272 admits it; cap271 rejects it.
Replacing `r` with a two-byte UTF-8 character costs273. These values are identical
on MSVC Debug/Release and GCC and do not use `sizeof` or a JSON byte count.

A live plan reserves the same grammar for its descriptors, clocks, bindings and
required task/operation dictionaries. It reserves10 bytes for unavailable
completeness with empty prose, and116 bytes per span plus the declared observation
source and module-version byte lengths for the largest possible fixed completion:
interval21, not-called observation18 plus those two string payloads, termination10,
iterations10, detail framing10, failed status45, completion/disposition2.
The largest failure text emitted by this collector is `unspecified` plus
`producer_reported`. Its API cannot accept arbitrary status/explanation text.
Each span additionally reserves116 bytes plus its clock-ID length for a possible
bucket, and another116 for the unclassified bucket. Duplicate buckets deliberately
overreserve; no temporary set is needed for admission. Publication counts the
actual retained fields, so unused reservations do not invent observations.

Native producer-only completion slots, local/bucket indices, per-shard counters,
validation/output containers and detail arenas have separate checked native
extent calculations before allocation. Their ABI-dependent storage is not a
portable `plan_bytes` decision. Logical metadata bounds limit actual admitted
counts/payload; native bookkeeping and allocator overhead are additional storage,
not a claimed byte-for-byte heap cap. Actual detail reservations are rounded down
per admitted slot and checked against native vector extents. No dormant maximum
setting allocates its declared maximum by itself.

When disabled, all four caps remain hashed but dormant as specified: only the
run/problem/configuration bindings and unavailable/collection_disabled completeness
with empty prose remain. No spans, clocks, buckets, task/operation dictionaries or
hidden completeness prose may use this exception. In summary mode only detail
caps are dormant; metadata admission is unchanged. Configured zero caps remain
valid configuration values but admit only fitting enabled records.

Logical values are copied after admission so spare producer capacity is not
retained. Optional metadata is cloned, including backend provenance. Record-time
lookups use sorted unsigned64 IDs (at most64 comparisons per lookup); text
inspection/copying is bounded by its admitted slot. Bucket merge uses the same
bounded lookup, and parent validation visits each edge a fixed number of times.
These are structural bounds, not latency or allocator-overhead measurements.

`project_legacy_span` checks matching supplied module/version/task/clock provenance
and finite ordered seconds; it returns an artifact error for contradictory input.
Failed final records preserve phase, category, message and an optional reference
to a diagnostics-role attachment. A missing attachment remains explicit null.

## Wire format and compatibility

The live `encode_run` form is described by the [v4 schema](../artifacts/schemas/run-statistics-v4.schema.json).
`encode_recorded_run` emits the inert archival [v7 schema](../artifacts/schemas/run-statistics-v7.schema.json),
which adds a finite fixed-plan minimax outcome, its outcome attachment reference,
the `finite_minimax` configuration output kind and explicit deadline termination.
The checked codec additionally enforces integer width,
UTF-8 byte limits, finite values, content digests, recomputed configuration ID,
problem/config/run bindings, parent DAGs, capacities and reference semantics.
Input byte, string, node and depth limits are checked before unrestricted DOM
growth; duplicate keys are rejected before overwrite. Unknown fields/tags/versions,
noncanonical integers, invalid UTF-8, trailing input and contradictory metric
variants are errors. New fields or variants require a new wire version and
explicit reader policy. The live reader accepts v7, v6, v5, v4, v3 and historical
v2; the recorded-run reader accepts v7, v6 and v5. A v2 candidate
with unestablished feasibility maps to v3 `Unestablished`; supported v2
candidate feasibility is rejected because its unscoped claim cannot be assigned
relation or witness scope without inventing evidence. Decoding a v2 live record and
encoding it again emits v4; recording a validated live run emits v7. Historical
fixtures and schemas remain unchanged.
The [v1 schema](../artifacts/schemas/run-statistics-v1.schema.json)
and the [v1 fixture](../../tests/artifacts/fixtures/run-statistics-v1.json) remain
historical evidence. V1 synthesis records are explicitly rejected with a schema
error: their independent target/evidence fields cannot be safely upgraded to a
typed family, and an old unestablished complete claim is never treated as proof.
JSON types and native solver types do not cross the
installed public boundary.

Historical standalone LP/convex bootstrap reports retain their real ProgramIdentity
and existing schema/readers. They are not scenario statistics and receive no
fabricated MODEL03 identity, strategy or resolved configuration. Linking their
raw records into a future scenario requires an actual scenario/config binding.
Published v1/v2 report data is never rewritten by this module. Reporting phases
retain their documented scope: a public run is not native-only time.

The full literal fixture includes a T=2 scalar integrator, two trajectories,
unestablished completeness, family reference, `abc` diagnostic content, nested and
parallel intervals, resources, configuration and stop observations. It is a data
contract fixture, not an algorithm publication or benchmark. Scientific HTML
publication still requires the separate reviewed measurement/profiler/provenance
gates.

Wire v4 adds required selection-batch `directions` and `distinctness_tolerance`.
Returned observations (including duplicates) are preserved; counts derive from
those observations using the full joint-history, ordered greedy metric documented
in the core contract and schema. The publisher checks request provenance against
resolved configuration and bounds the distinct count, not raw cardinality, by the
requested count. V2/v3 decoding recovers the request facts from their existing
resolved configuration without adding observations or evidence; re-encoding emits
v4. Historical schemas and fixtures remain unchanged. Unknown fields still reject.
The live registered T-S01 completeness capability remains unencodable; v4 does not
introduce a portable completeness proof or change that refusal.
