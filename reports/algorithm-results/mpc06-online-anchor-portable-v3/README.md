# MPC-06 portable checked-source layer, version 3

This separately versioned layer binds current portable manifest writers from `8133414d43f5c35fb7c52833fe4d339c9057b2ea`. Only path serialization changed: study source-map and checksum names, and renderer output checksum names now explicitly use POSIX separators. The original v1 archive and v2 checking layer are unchanged, including their offline bound reviewing tools.

No algorithm, native QP or mathematical experiment was rerun. `checked-inputs/mpc06-online-anchor-v1/` is the unchanged original archive; all 180 native QPs and their numerical/timing payloads remain identical. The fresh `verification-v2.json` uses the existing version-2 receipt schema to bind the same input bytes to the updated study/renderer code. The new receipt identity, reviewing source digests and independent recheck duration are metadata changes, not new measurements of the algorithm.

The phase-plot SVG and reading-page payload remain unchanged on Linux. Summary rows, native costs, feasibility counts and timing observations are identical; only renderer identity and recheck metadata differ. Windows-shaped regressions exercise actual capture source-map/checksum generation and rendering checksums. Both failed before the portable writer fix and now pass. Actual hosted Windows CI remains the platform gate.

Read-only replay (no native solve):

```sh
python3 -B reports/algorithm-results/mpc06-online-anchor-portable-v3/review-tools/check.py \
  reports/algorithm-results/mpc06-online-anchor-portable-v3/checked-inputs/mpc06-online-anchor-v1 \
  --receipt-output reports/algorithm-results/mpc06-online-anchor-portable-v3/verification-v2.json
```

Regenerate the reading layer only into a new output directory, with those checked inputs and receipt passed to the retained `review-tools/render.py`. The raw/structured extraction, source/script/receipt binding and immutable-input requirements remain enforced. #602 remains open; no Pages publication, performance winner or library release is claimed.
