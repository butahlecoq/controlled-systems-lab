# Immutable numeric snapshots and retained views

CORE-03 provides `<csl/numeric/data.hpp>` and the CMake target `CSL::numeric`.
It sits between [neutral authored values](core-interfaces.md) and later model or
optimizer adapters. It leaves interface revision 1.1 unchanged. This is a C++20
source interface for compatible toolchains, without a stable binary ABI.
No third-party matrix container appears in the interface.

## Creation and ownership

`csl::numeric::snapshot` accepts a borrowed `DenseInput`, an authored `csl::Matrix`,
or an authored `csl::SparseMatrix`. `snapshot_vector` accepts a
`std::span<const double>`. Each returns `Result<T>`: either an immutable
`MatrixView`/`VectorView`, or one `csl::Diagnostic`. Inputs are validated at this
seam; failure does not publish a partially valid view. Views have no default or
public storage constructor. They expose dimensions, coefficient values returned
**by value**, and a coarse read-only storage borrow. Matrix indices must satisfy
`row < rows()` and `column < cols()`; vector indices must satisfy `index < size()`.
These programming preconditions are asserted in Debug. Internal operations do
not revalidate complete storage on each coefficient access.

Every successful snapshot **copies** its input into privately constructed,
shared, const storage. It accepts no arbitrary owner token or borrowed retained
pointer. Later caller mutation, reallocation, destruction or surviving mutable
aliases cannot change the published snapshot. Copies of a view retain this owned
storage, including when captured by asynchronous or detached workers. View
handles deliberately provide copy construction/assignment without a destructive
move, so moving a handle also leaves its source valid. No mutable storage or
writable pointer is exposed. Sharing immutable views is safe; assigning the **same handle
object** concurrently still requires caller synchronization. Multiplication
allocates an independent owning output vector for each caller.

The synchronous creation precondition is that the borrowed span/aggregate really
describes live, initialized objects, and that the producer does not mutate or
destroy them until the call returns. The module validates sizes and descriptors;
it cannot prove that a fabricated span points to a real array. For strided dense
inputs all elements in the addressed extent, including padding, must be readable
initialized doubles because that extent is copied. No immutability precondition
on producer aliases remains after publication. Allocation failures and standard
container length errors propagate as exceptions; descriptor errors use `Result`.

`MatrixView::descriptor()` returns a `MatrixDescriptor` variant holding either a
`DenseInput` or a `CsrInput`. The dense descriptor contains const coefficient
storage and original shape/layout/element strides; the CSR descriptor contains
shape plus const spans of offsets, column indices and values.
`VectorView::values()` returns a const double span. These accessors cost O(1),
share the same backing storage across view copies, and perform no new snapshot
copy or validation. An adapter can dispatch on representation once and map the
buffer/CSR arrays directly, without per-coefficient variant dispatch.

**Returned descriptors and spans are borrowed and do not retain ownership.**
Keep a `MatrixView`/`VectorView` or its copy alive for the complete lifetime of
every borrow. An asynchronous adapter captures these owning views, then takes
the descriptor within that worker. Returning just a descriptor/span from a scope
that destroys its last owning view violates this lifetime precondition. The
borrow is read-only; modifying its const elements by casting is unsupported.
`CsrInput` is an adapter observation descriptor, not an additional creation seam.

## Dense layouts, stride and extent

`DenseInput` contains a `span<const double> storage`, `size_t rows, cols`, signed
`ptrdiff_t row_stride, column_stride`, and a `DenseLayout`. Strides count **double
elements**, from the first element of the provided span. There is no byte-stride,
offset or scalar reinterpretation. Only double is accepted by the C++ types;
float, complex, exact and interval inputs need a separate future interface.

For nonempty shapes:

- `row_major`: column stride is 1 and row stride is at least `cols`.
- `column_major`: row stride is 1 and column stride is at least `rows`.
- `strided`: arbitrary positive strides whose coefficient addresses do not
  overlap. This includes interleaved and padded layouts, beyond the two standard
  leading-dimension conventions.

Unknown layout values, negative strides, zero strides on nonempty shapes,
overlapping addresses and layout/stride inconsistencies return `unsupported`
with field `numeric.dense.layout` or `numeric.dense.stride`. Positive strides
alone do not establish nonoverlap: for `g = gcd(row_stride, column_stride)`, a
collision exists exactly when both `rows > column_stride/g` and
`cols > row_stride/g`. This follows from the smallest positive solutions to
`dr*row_stride == dc*column_stride`; both index differences must fit the shape.

The addressed extent is
`(rows-1)*row_stride + (cols-1)*column_stride + 1`. Each multiply and addition is
checked for `size_t` overflow **before indexing**. The span must cover that extent;
additional trailing elements are permitted. Overflow returns `invalid_input` /
`numeric.dense.extent`; insufficient storage returns `invalid_input` /
`numeric.dense.storage`. The snapshot copies precisely the addressed extent,
including its padding, preserving the original strides privately. It neither
reads nor copies trailing storage beyond that extent. Only logical matrix
coefficients are checked for finiteness; padding and trailing values may contain
NaN or infinity and cannot participate in arithmetic. Snapshot time is
O(rows*cols + addressed_extent), storage O(addressed_extent). Stride validation
also costs O(log(min(row_stride,column_stride))) for the gcd.

Authored `Matrix` is the stricter contiguous row-major form:
`values.size() == rows*cols` exactly. The shape product is checked for overflow
(`numeric.dense.shape`), and extra/missing values are invalid
(`numeric.dense.storage`). Nonempty derived strides must fit `ptrdiff_t`.
Its snapshot time and storage are O(rows*cols).

## Sparse convention

Authored `SparseMatrix` is zero-based CSR. It requires exactly `rows+1` offsets,
first offset 0, nondecreasing offsets in `[0,nnz]`, final offset `nnz`, and equal
value/index lengths. The `rows+1` addition is checked before evaluating storage
requirements. Column indices must be less than `cols` and **strictly increasing
within each row**, so duplicate or unsorted entries are rejected. Explicit zero
coefficients are allowed; missing entries read as zero. All stored values must
be finite doubles. There is no implicit sorting, duplicate summation, one-based
conversion or symmetry/triangular convention.

Failures return `invalid_input` with `numeric.csr.storage`,
`numeric.csr.offsets`, `numeric.csr.indices`, or `numeric.values` as applicable.
All three arrays are copied. Snapshot time/storage are O(rows+nnz); single
coefficient lookup uses binary search in that row. Sparse dimensions need not
have a representable dense shape product; later adapters must validate their
own native integer limits before narrowing.

## Empty dimensions and finite arithmetic

`0×n`, `n×0`, `0×0`, empty vectors and empty CSR are legal. An authored dense
empty shape requires empty values. A dense descriptor with either dimension zero
has no addressed extent: no storage is read/copied, zero strides are permitted,
and dimensions are retained. Its coarse descriptor normalizes both strides to
zero and preserves the declared layout. Unknown layouts or negative strides remain
unsupported even when empty. Empty CSR still has `rows+1` offsets, all zero:
`0×n` uses `{0}`; `n×0` uses `n+1` zeros and no indices/values. Thus zero-control
and zero-external-port buffers need no nonexistent coefficient addresses.

`multiply(MatrixView, VectorView)` first requires `matrix.cols()==vector.size()`
even for empty shapes. Mismatch returns `invalid_input` /
`numeric.multiply.shape`. A `0×n` matrix times a length-n vector yields an empty
output; an `n×0` matrix times the empty vector yields n zeros. Dense multiplication
costs O(rows*cols + rows); CSR costs O(rows+nnz), visiting stored entries rather
than scanning columns. Both allocate O(rows) output storage and use no shared
mutable worker state. View copies retain storage in O(1), with no numeric copy.

All vector values and matrix logical/stored coefficients must be finite at
creation (`invalid_input` / `numeric.values`). Multiplication uses ordinary
double products and sums in increasing column order, and rejects any nonfinite
output (`invalid_input` / `numeric.multiply.arithmetic`). This does not promise
correct rounding, bitwise equality across toolchains, a conditioning bound or
validated arithmetic. Allocation limits still apply to outputs of enormous
otherwise valid shapes. Numerical fixtures establish no optimization, synthesis,
set semantics or family evidence.

## Consumer example and tests

```cpp
#include <csl/numeric/data.hpp>

using namespace csl;
using namespace csl::numeric;
auto m = snapshot(Matrix{2, 3, {1, 2, 3, 4, 5, 6}});
auto v = snapshot_vector(Vector{7, 11, 13});
// A real caller handles Diagnostic alternatives before extracting the views.
auto y = multiply(std::get<MatrixView>(m), std::get<VectorView>(v));
// Successful y is the owning Vector{68, 161}.
```

Use `find_package(CSL 0.1 CONFIG REQUIRED)` and link `CSL::numeric`. The
[installed numeric client](../../tests/installed/numeric_client.cpp) compiles
from a copied source tree using only the installed prefix and public header.
[Unit tests](../../tests/unit/numeric/data_tests.cpp) cover the literal oracle
for standard/padded/interleaved layouts and CSR, diagnostic identity, overflow,
zero dimensions, mutable producer aliases, scope exit, independent workers and
gated detached use. Doctest checks remain active in Release. This covers only
the numeric zero-dimension/lifetime portion of T-M02; observation knowledge and
singleton/universal/empty-set semantics remain MODEL/GEO obligations.
