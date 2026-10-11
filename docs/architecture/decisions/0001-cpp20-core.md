# ADR 0001: C++ core language

Date: 2026-10-11. Status: accepted language direction; C++20 working standard.

## Context and decision

The owner requires modular mathematical algorithms, interchangeable geometry and optimization backends, efficient computation, and parallel scalability. Architecture and language must be established before numerical implementation. After considering C++ and Rust, the owner explicitly selected C++ in the conversation.

Use C++ for the main library and computational orchestration. Adopt C++20 as the working standard carried forward from the architecture discussion. Keep Python scientific references as independent verification tools. Product algorithms do not require an initial Python implementation followed by a rewrite.

## Consequences

- Native interfaces define ownership, buffer layout, workspaces, cancellation and algorithm capabilities explicitly.
- Select algorithms and backends at coarse runtime boundaries; specialize arithmetic and storage inside computational kernels.
- Share immutable problem/set data. Each worker owns its mutable solver workspace and warm-start state.
- Keep third-party solver and matrix-library types behind adapters. Register compatible in-process plugins first; do not promise a portable C++ binary ABI.
- Preserve versioned problem/result artifacts for independent references and later bindings.
- Measure end-to-end performance, memory and result guarantees. C++ does not eliminate combinatorial growth or imply that one numerical method is fastest.

## Remaining design decisions

CMake packaging, a native library as the first interface, concrete numerical dependencies, compiler support, distribution policy and the initial geometry/backend combination remain proposals requiring design review. This ADR selects the language; it does not accept every illustrative type or third-party backend in earlier documents.

Rust, Julia, MATLAB and Python tools can remain external scientific comparisons or backend implementations where useful. They are no longer competing choices for the main core in this design cycle.

See the [native contracts draft](../../superpowers/specs/2026-10-11-cpp-core-contracts-design.md), [modular algorithm design](../modular-algorithms-and-solution-sets.md) and [performance framework](../performance-and-language.md).
