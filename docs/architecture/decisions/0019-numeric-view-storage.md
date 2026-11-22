# ADR 0019: Keep numeric views immutable and layout-aware

Date: 2026-11-22
Status: Accepted

## Context

Numerical adapters consume dense or CSR matrices through read-only views.
Correct indexing depends on logical dimensions, storage layout, strides, and
row offsets. Borrowed input buffers may also outlive or be mutated by their
producers, while descriptors expose spans into the retained storage.

## Decision

- Snapshot borrowed matrix and vector inputs into immutable retained storage.
  Matrix and vector views may be copied and shared by readers; descriptor spans
  are borrowed and remain valid only while a retaining view is alive.
- Interpret dense matrices by their declared layout and element strides. For
  nonempty shapes, accept only positive strides that satisfy the declared
  layout, do not overlap logical coefficients, and address within the input
  storage extent. Negative strides are unsupported. Empty shapes have no
  addressed coefficients; preserve their dimensions for nonnegative strides
  without requiring storage. Copy the addressed prefix, including internal
  padding, but validate and use only logical coefficients.
- Preserve zero-row and zero-column dimensions in both dense and CSR forms.
  Preserve CSR row offsets, including empty rows, rather than inferring shape
  from the nonzero entries.
- Let adapters map the view's existing immutable storage without making another
  snapshot copy. A consumer that uses descriptor spans asynchronously must
  retain the view for the full borrow lifetime.

## Consequences

Tests use nonsquare literal multiplication oracles across row-major,
column-major, padded, interleaved, and CSR layouts. They also verify that
non-finite padding is ignored, trailing unrelated producer storage is excluded,
empty shapes retain their dimensions, and asynchronous readers remain valid
after producer handles leave scope. These checks protect storage and lifetime
semantics without asserting that adapters can outlive their view owners.

The buffer-view tests also exercise copy and move construction and assignment
across each dense layout, then replace the original handles while retained
copies and descriptor spans remain live. A signed rectangular oracle is shared
across row-major, column-major, interleaved, and CSR representations so that
axis swaps, sign loss, or omitted columns cannot be hidden by a layout-specific
expected value. CSR lifetime coverage preserves empty rows and explicit stored
zeros across move and replacement. The joined-worker fixture reserves its
future slots before launching gated asynchronous tasks: if vector growth threw
after launch, destruction of a still-gated `std::async` temporary could wait
forever before the gate is opened. Declaring the gate after the future vector
ensures its destructor opens the gate before the future vector waits for
workers during stack unwinding.
