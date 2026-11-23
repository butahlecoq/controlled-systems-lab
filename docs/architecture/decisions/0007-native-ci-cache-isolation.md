# ADR 0007: Isolate native CI caches by trust boundary and build lane

Date: 2026-11-21
Status: Accepted

## Context

Native CI reuses dependency archives and compiled objects. An archive restored by a trusted build must come from a compatible build, and release lanes depend on complete snapshots of their own prerequisites.

## Decision

Pull requests can read trusted main snapshots. Only trusted main runs publish to the main cache namespace. Manual development runs on other branches save only to a branch-specific namespace when GitHub permits it.

Each build lane owns its immutable archive snapshots. The core lane can finish before a full or probe lane and may have only a subset of its dependencies. Including the lane in the cache identity prevents the core lane from claiming the full or probe archive key with a partial snapshot.

The compiler cache is an optional build-time optimization. A missing cache binary or a failed installation attempt disables compiler-object caching without failing validation. The setup script reports it as enabled only after `ccache --version` succeeds, and compiler-cache operations run only when that output is true. Raw dependency-archive caching is independent of compiler-cache availability.

## Verification

Cache namespace policy is implemented in `scripts/ci/cache_keys.py` and exercised by `tests/ci/test_cache_keys.py`. Optional compiler-cache setup is implemented in [`prepare_ccache.sh`](../../../scripts/ci/prepare_ccache.sh) and covered by [`test_prepare_ccache.py`](../../../tests/ci/test_prepare_ccache.py). The original cache work is tracked in [PR #490](https://github.com/butahlecoq/controlled-systems-lab/pull/490).
