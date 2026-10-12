# Problem identity byte format, version 1

The resolved problem ID is `csl.problem.v1.sha256:` followed by 64 lowercase hex
digits. SHA-256 hashes the canonical bytes described below. This is a structural
mathematical and resolved-content identity, not an algorithm configuration key
or a proof that two formulations have equivalent feasible sets. The private
implementation follows FIPS 180-4; no FIPS validation claim is made.

Normal publication streams these bytes through the hash without allocating a
second full encoding. `canonical_bytes()` materializes the same writer's output
for inspection/interchange. Encoding and SHA processing are linear in emitted
bytes. Native H/V matrices emit logical dense row-major values: dense views use
constant-time coordinate reads, and CSR views consume their validated sorted
entries with a forward cursor while emitting missing coordinates as zeros.
Each coordinate is emitted once and each stored CSR entry is consumed once;
there is no per-coordinate search or full dense matrix copy. For nonzero column
count, this takes O(rows * columns) work even for sparse inputs. A zero-column
matrix emits its two counts without traversing rows. Temporal CSR instead
retains structural order and takes O(rows + nnz) work. Large sparse H/V inputs
can therefore still have substantial output volume and encoding cost.

These encoding costs exclude component publication/validation, actual external
content hashing, binding-key sorting/comparison and objective PSD checks.
`canonical_bytes()` additionally owns storage proportional to the emitted byte
count; normal fingerprinting streams without that output allocation. These are
source-derived bounds, not a measured speedup. Counts and products are checked
against the SHA-256 byte-length limit `2^61-1` before overflow/narrowing. Standard allocation
exceptions propagate; unrepresentable publication lengths produce
`invalid_input` at `problem.identity.length`. The format requires eight-bit bytes
and IEEE-754 binary64, checked at compile time. It does not serialize native
object memory, pointer values, padding or implementation-specific enums.

## Primitives

| Primitive | Encoding |
|---|---|
| `u8`, `u32`, `u64` | unsigned, big endian, exactly 1, 4 or 8 bytes |
| `f64` | IEEE-754 binary64 bits in big endian; both signed zeros encode as positive zero |
| `vector` | `u64` count, followed by that many `f64` values |
| `array<R>` | `u64` count, followed by records `R` in order |
| `string` | `u64` byte count, then exact string bytes without a terminator |
| `matrix` | `u64` rows, `u64` columns, then logical row-major `f64` entries; no extra value count |
| `CSR` | `u64` rows, `u64` columns, `array<u64>` offsets, `array<u64>` column indices, `vector` values |
| `interval` | lower-present `u8`, optional lower `f64`, upper-present `u8`, optional upper `f64` |

Presence bytes are zero or one. Publication authorities reject nonfinite
numerical coefficients. Zero normalization affects encoding only; stored authored
coefficients remain unchanged. CSR temporal structure retains explicit zeros.

## Root record

Concatenate the following in order, with no alignment or extra separators:

1. Twelve magic bytes `43 53 4c 2d 50 52 4f 42 4c 45 4d 00`, then `u32(1)`.
2. Time-domain `u8(0)` for discrete, `u64` state/control/external dimensions,
   then the time `vector`.
3. Dynamics provider: `u8(0)` followed by one stage, or `u8(1)` followed by an
   array of indexed stages. Each stage is matrices A, B, E, then offset vector.
4. Array of observation channels. Each channel has provider `u8(0)` plus one
   map, or `u8(1)` plus an array of maps; then an array of samples. A map is
   matrices state, control, external, error, then offset vector. A sample is
   `u64` state stage, measured event, available event, input-stage presence byte
   and optional `u64` input stage. An event is `u64` stage followed by `u8(0)`
   before decision or `u8(1)` after decision.
5. Initial information: `u8(0)` plus known-point vector; or `u8(1)`, quantifier
   (`u8(1)` existential, `u8(2)` universal), then set record.
6. Controls: `u8(0)` plus array of continuous stage sets; `u8(1)` plus finite
   catalogue; or `u8(2)` plus array of continuous stage sets and finite catalogue.
   A catalogue is `u64` declared dimension followed by an array of point vectors.
7. Array of state sets (T+1 records).
8. Temporal presence byte, then if present the CSR joint map and array of
   interval bounds.
9. External information: `u8(0)` absent; `u8(1)` plus array of known vectors;
   `u8(2)` plus quantifier and array of exogenous stage sets; or `u8(3)` plus
   quantifier, array of adversarial stage sets and semantics-reference string.
10. Information pattern: `u8(0)` nominal open loop, `u8(1)` feedback.
11. Original terminal criterion: `u8(0)` plus linear coefficient vector and
    offset; `u8(1)` plus quadratic Q matrix, linear vector and offset; or
    `u8(2)` plus residual map matrix and target vector. No implicit squaring.
12. Intake `u8(0)`, the only publishable stage-product/uncoupled declaration.
13. Array of content bindings sorted by ASCII key. Each record is key string,
    `u64` actual content byte length and exactly 32 raw digest bytes.

## Set records

| Tag | Following fields |
|---|---|
| `u8(0)` elementary empty | `u64` ambient dimension |
| `u8(1)` elementary universal | `u64` ambient dimension |
| `u8(2)` elementary singleton | point vector |
| `u8(3)` verified native handle | `u64` ambient dimension, native representation record |

Native representations are: `u8(0)` H with inequality matrix, upper vector,
equality matrix, equality-value vector; `u8(1)` V with vertex matrix and ray
matrix; `u8(2)` empty; `u8(3)` universal; `u8(4)` singleton with point vector.
H/V matrices use logical row-major values independent of dense layout, strides,
padding and CSR storage. Verified native elementary representations deliberately
remain structurally distinct from elementary DTO variants.

Authored ProblemId, SetId, coordinate labels, affine-dimension claims/evidence,
backend selections, resource policy, accepted numerical tolerances and source
locations are excluded. Retained descriptions still carry their metadata.
Provider choice, dormant constant coefficients at T=0, observation maps with
empty schedules, H/V row order/scaling, finite catalogue order/duplicates, all
quantifiers, and optional temporal presence remain structural. No set
minimization, row normalization, hull conversion or semantic-equivalence proof
is performed. Format changes require a new identity version.

## Independent literal examples

Z has zero state/control/external dimensions, T=0 and times `[0]`, constant empty
coefficient matrices, known empty initial point, continuous empty control stages,
one universal zero-dimensional state set, no observations/temporal/external data,
nominal information, zero linear criterion and no content. Its encoding is 186
bytes and digest is
`2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e`.

S has dimensions (1,1,0), times `[0,1]`, constant A=0, B=1, empty E, offset 0,
known initial 2, continuous singleton control 3, universal state sets, no other
data, nominal information and linear criterion x. Its 260-byte encoding hashes to
`167962d4127c26ae199032551dceb32e8a04bfed653cfd44e90ad6cc89a36cb4`.
Changing A to 1 yields terminal value/cost 5 and digest
`695f976378c20b642302b5d1af88e656bdd50c1828824a92c0088ecc6364f1dc`.

Adding to S the binding `dynamics/B/constant` with ASCII byte `1` produces 327
bytes and digest
`ade9632753f13fa2790071c5fcff8dea139ebb28314a2f2942a9de0ace1e7c79`.
Changing that byte to ASCII `2` yields
`de2be880f1fa27c99593d7b0f3c90b475050452a1d7b2c0ab3a68960b6413d68`.
These lengths, complete Z/S byte sequences and hashes are independent literals
in the public behavior tests. Content hashing also checks empty, `abc`, and
55/56/63/64/65/1000-byte padding and multiblock vectors.
