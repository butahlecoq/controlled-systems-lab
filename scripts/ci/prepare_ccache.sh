#!/usr/bin/env bash
set -u

# ccache only improves build time. Its absence must never prevent validation.
enabled=false
if [[ "${RUNNER_OS:-}" == Linux && "${CACHE_CLEAN:-false}" != true ]]; then
  if ! command -v ccache >/dev/null 2>&1 || ! ccache --version >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
      timeout 120s sudo apt-get update -qq && timeout 120s sudo apt-get install --no-install-recommends -y ccache || true
    fi
  fi
  if command -v ccache >/dev/null 2>&1 && ccache --version >/dev/null 2>&1; then
    enabled=true
  fi
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'compiler_enabled=%s\n' "$enabled" >> "$GITHUB_OUTPUT"
else
  printf '%s\n' "$enabled"
fi
