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
- Interpret dense matrices by their declared layout and element strides. Accept
  non-square and nonoverlapping strided layouts, use the addressed extent, and
  ignore padding values that are not matrix coefficients. Do not retain storage
  after the final addressed coefficient.
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
