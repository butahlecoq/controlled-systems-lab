# ADR 0012: Verify lesson layout through Chromium DevTools Protocol

Date: 2026-11-22. Status: accepted.

## Context

The native discrete lesson needs layout checks at real mobile and desktop
viewport sizes, plus saved screenshots and a printable PDF. The repository
does not need a Node browser-automation package for this check, but it does
need a Chromium executable available as `chromium`.

## Decision

[`check_native_discrete_layout.mjs`](../../../tests/reporting/check_native_discrete_layout.mjs)
starts headless Chromium and drives it directly through the browser's DevTools
Protocol using Node's built-in WebSocket API. Run it with:

```sh
node tests/reporting/check_native_discrete_layout.mjs LESSON.html OUTPUT_DIRECTORY
```

The check measures the rendered lesson at 390×844 and 1280×1000, captures
screenshots, verifies overflow and equation access, and writes a print PDF.

## Consequences

The test requires `chromium` on `PATH`; it does not require a separate Node
automation library. Changes to the browser protocol or to Chromium's startup
contract belong in the executable test and its CI environment. The validation
scope remains the rendered layout and accessibility properties asserted by
the script, not mathematical correctness of the lesson's source data.
