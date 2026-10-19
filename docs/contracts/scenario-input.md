# Scenario input

`CSL::input` loads strict local JSON bytes or a local file into the existing
immutable `problem::ResolvedProblem`. Include `csl/input/scenario_loader.hpp`.
`load_scenario(span<const byte>, LoadOptions)` and `load_scenario_file(path,
LoadOptions)` return a variant of LoadedScenario, HistoricalScenario,
InputFailure, UnsupportedInput or OperationStopped. Loading does not select a
strategy, discretize a continuous model, run a solver, prove feasibility or
produce a family of solutions. CLI execution and scenario catalogues are separate
modules. No observation or reporting module is a dependency. Continuous affine
coefficients have a separate [loader and conversion contract](time-domains.md).

## Supported executable grammar

The root schema is exactly `csl.scenario/1`. Required fields are schema, horizon,
model, initial_state, controls and objective. Optional fields are id, times,
dimensions, profile, states, run and metadata. The only profile is the JSON string
`nominal_discrete_v1`; omission is equivalent mathematically. Null, other types,
empty strings and unknown profile strings fail at `/profile`, expected
`string "nominal_discrete_v1"`. Unknown keys reject. The
[schema](../../schemas/scenario/v1.schema.json) and its
[cross-field notes](../../schemas/scenario/README.md) are authoring aids; the
native validation boundary remains authoritative.

Matrices accept rectangular row arrays or `{rows,cols,values}` with flat row-major
values. Empty row arrays mean 0x0. For 0xn use explicit extents and an empty value
array. Extents are checked before multiplication/allocation. Counts require
unsigned integer JSON tokens; booleans, strings and floating tokens do not count.
Numeric coefficients require finite binary64. Integer coefficient tokens must
have magnitude at most 2^53; nonzero decimal underflow to zero rejects. There is
no rational-string parsing, coefficient clipping or repair.

Model kinds are `linear_discrete`, `affine_discrete`, `linear_discrete_ltv` and
`affine_discrete_ltv`. Constant kinds contain A/B and, for affine kinds, offset.
Indexed kinds contain exactly T stages with those same fields, without a nested
kind. A is nxn, B is nxm, offset has n entries; every stage has the same n/m.
Linear kinds supply zero offsets. External width is zero. Supplied dimensions
contains exactly state/control/external, matching the matrices; empty indexed
providers at T=0 require it. Constant T=0 coefficients remain part of identity.
Supplied times contains T+1 finite strictly increasing values. Otherwise times
are indices 0..T, with no physical unit implied. Discrete matrices are applied
once per transition; nonunit time spacing does not rescale them.

Initial_state is a required known n-vector. A control set is broadcast to T
stages, or `{kind:"stages",values:[...]}` supplies exactly T sets. State sets
similarly require T+1 entries; omitted states are elementary universal sets.
Set kinds are empty, universal, singleton(point), box(lower/upper),
polyhedron_h(H/h/E/e), and polyhedron_v(vertices/rays). Empty/universal carry the
inferred ambient dimension. Box endpoints are finite or null (absent); lower
must not exceed upper. Each present upper endpoint produces +ei*x<=upper before
the corresponding lower row -ei*x<=-lower. Fixed bounds retain both rows.
All-null boxes retain zero-row H representation, distinct structurally from
elementary universal. H equalities and inequalities preserve authored rows,
including contradictory or redundant rows: publication is not a feasibility
claim. V semantics come from CSL::sets, including the distinction between no
vertex and a zero vertex with rays. No canonical set vocabulary is duplicated.

Original terminal objective kinds are linear(coefficients, optional offset),
quadratic(Q, linear, optional offset), residual_norm(L, target), and
terminal_distance(target). Quadratic means 0.5*x'Q*x + linear'x + offset.
Residual norm means ||L*x-target||2, not its square; terminal distance sets L=I.
Offsets default to zero. Rectangular/zero-row maps are retained. Existing
ObjectivePolicy checks symmetry and PSD numerically; the loader does not upgrade
that to validated proof. LoadOptions publication policy is recorded separately
from requested run tolerances.

## Explicit unsupported structures and ordering

Reserved root keys are initial_information, external, observations, information,
uncertainty, temporal and hybrid. Presence, including null or empty values,
returns UnsupportedInput. initial_state plus initial_information is instead an
invalid conflicting declaration. Missing required initial_state is not zero.

The exact reserved model strings are linear_continuous, affine_continuous,
linear_continuous_ltv and affine_continuous_ltv. They return UnsupportedInput at
`/model/kind`, expected `a discrete transition model; continuous-time input is
not supported in v1`. The model must be an object with a string kind; an unknown
or misspelled kind is invalid. Reserved bodies are not interpreted. Control
provider kinds finite/mixed and objective kinds sum/mixed are similarly
recognized unsupported; nested entries of a stages provider use ordinary set
kinds only. No future grammar or capability is fabricated.

An external matrix descriptor has exactly kind=external, string uri, 64 lowercase
hexadecimal sha256, unsigned rows/cols and layout=row_major. The descriptor is
validated and then rejected as unsupported without opening the locator or
claiming digest verification. Future support must decode actual bounded owned
bytes and pass their canonical content bindings into resolve.

Admission order is bytes/encoding/syntax/duplicate/quota checks; root schema,
unknown/required fields; exclusions; profile; reserved root keys in the order
listed above; model/stages/dimensions/times; initial/control/state data;
objective; run/metadata; canonical publication. Unknown object keys are reported
in lexical key order. Supported field validation follows schema order and array
indices. InputFailure carries category, JSON Pointer, observed and expected
forms, optional parser byte offset and optional original canonical Diagnostic.
Pointer keys escape ~ and /. Canonical Q diagnostics point to `/objective/Q`;
caller LoadOptions policy errors have root pointer because no authored field
caused them. Unsupported canonical policies remain UnsupportedInput. Diagnostic
explanation text from dependencies is supplementary to structured category/path.

## Run intent, defaults and ownership

Optional run contains comparison or methods (mutually exclusive), backends,
witnesses, numerical, resources and seed. The only comparison string is
historical_reachability_vs_joint_trajectory. Methods is an ordered nonempty
array of `{id,version?}` requests with nonempty strings. No registration,
effective version, ConfigId or prepared execution graph is produced.

Backends accepts lp, convex, hull, geometry, converter, approximation and
selector as module requests, plus representation as a nonempty ID string.
Omissions stay unspecified. Witnesses optionally retains positive count,
nonnegative distinctness_tolerance and finite direction vectors; compatibility
with a future selected strategy is not decided here. Numerical requires both
finite nonnegative absolute_tolerance and relative_tolerance. Resources requires
positive total_threads/outer_workers/threads_per_worker and optional positive
memory_bytes, checked by existing check_resources. Memory is admission/accounting,
not an enforcement promise. Seed is an optional unsigned size_t value. Timeout
is not a v1 field.

Metadata supports title, description, time_unit, state_labels/control_labels and
state_units/control_units. Coordinate lists match dimensions. ID defaults to an
empty display label. These labels and all run settings are outside mathematical
identity. The owning default records distinguish authored presence from nominal
omissions (profile, times, offsets, states, external, observations, temporal,
run, id and metadata). They name defaults, not resolved backend configurations.

LoadedScenario and HistoricalScenario cannot be constructed in an invalid empty
state. Const retaining getters outlive the outer handle; original input buffers
and files may be changed or destroyed after synchronous loading. The caller
keeps input bytes stable during the call. SourceProvenance owns exact original
bytes/digest through existing snapshot_content, location, schema/default revision
and publication policy. Source capture is outside resolve.external_content, so
whitespace, location, run intent and display changes preserve ProblemId. Provider
and representation changes may change structural identity even when sets or
mathematics happen to agree. No parser type or private dependency escapes.

## Bounds, cancellation and historical records

Defaults cap input at 4 MiB, nesting depth32, keys/values/containers524288,
decoded strings4096 bytes (description16384), total authored matrix coefficients
262144, matrix extents and state/control dimensions256, horizon4096, expanded
numeric scalars1048576, and conservative identity storage64 MiB. Callers may
lower each quota, including to zero, but not raise it. Derived storage admission
checks occur before allocation; the identity estimate charges 16 bytes per
numeric scalar, 256 per structural object and 1024 fixed bytes. This deliberately
conservative estimate can reject below the nominal byte cap. These are admission
limits, not peak-process-memory enforcement. Lexer buffering is bounded by the
input byte cap; file reads stop at cap+1. Standard allocation failures propagate.

Cancellation is polled before IO, each file chunk, parser node, translation
expansion and after publication work. Calls into canonical factories are
synchronous; cancellation is cooperative, not hard interruption. File failures
distinguish not_found, unreadable and read_failed; parser failures remain parser
failures. No network or external matrix IO occurs.

A separate archival branch recognizes schema_version1, id B04-historical,
executable=false and restoration_status=incomplete_and_inconsistent. It requires
a nonempty unresolved string list and execution_gate. It returns HistoricalScenario
with owned raw bytes and restoration data, never a ResolvedProblem. Extra
archival metadata stays opaque. Unrelated old formats are unsupported; executable
true, missing gates and malformed recognized records fail. The repository B04
manifest remains incomplete and inconsistent: no controls are inferred and its
reported cost is not replayed.

## Validation and packaging

Public byte/file tests use literal independent identities, transitions 2,7,16 on
nonunit times, original quadratic/norm costs, constraints, T0/R0, malformed and
reserved data, quotas, cancellation and retained ownership. Both loader routes
test all four continuous kinds and the misspelled discriminator. Historical
tests read the unchanged B04 archive. Sampled trajectories are not complete
minimizer enumeration. The source and installed clients check the literal
260-byte structural identity and original linear cost. Neutral header fixtures
include the new header in both existing orders while retaining numeric-only
linking. The private pinned nlohmann3.11.3 headers stay source-only; its MIT notice
is installed, and the installed export has no JSON target. Existing core source
version, mathematics, adapters and report assets remain unchanged.
