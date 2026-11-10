# MPC-06 checked-source evidence, version 2

This is a new reading/checking layer for the unchanged native capture in `mpc06-online-anchor-v1`. No native QP, disturbance calculation or algorithm timing was rerun. Capture source remains `7e08f9196504488fde4d28bb62ff5030af64fe2f`; the checked-source fix is `2588493a875e60d71023c47977b3707725848b17`.

`checked-inputs/mpc06-online-anchor-v1/` is a byte-for-byte copy of the complete original archive, including its historical unbound receipt and checksum manifest. Those files are preserved as historical input, not promoted by their old status label. `verification-v2.json` binds every one of those source bytes and all five reviewing scripts, and records the fresh successful replay of the same 180 native QPs. The shared boundary parses every completed native response stream and requires exact equality with structured APP-04/QP results in repetition/program order, including recorded timings. Capture-source and scenario bindings and native timing-versus-response intervals are checked separately from checksum integrity.

The new renderer validates that receipt and extraction boundary before consuming quantitative values. It writes a separate directory, never renews a manifest around modified source data, and preserves the checked original under its own report identity. `review-tools/` retains the exact checker/helper/model/study/renderer code; its hashes are part of the receipt. The root SHA256SUMS covers the new generated reading layer and its preserved inputs.

Read-only recheck from the repository root:

```sh
python3 -B reports/algorithm-results/mpc06-online-anchor-checked-v2/review-tools/check.py \
  reports/algorithm-results/mpc06-online-anchor-checked-v2/checked-inputs/mpc06-online-anchor-v1 \
  --receipt-output reports/algorithm-results/mpc06-online-anchor-checked-v2/verification-v2.json
```

To reproduce the reading layer, pass that same checked input and receipt to `review-tools/render.py --receipt ... --output /absolute/new/output`. The output directory must be new. Altered raw responses, structured timing, capture source, receipt content or reviewing scripts fail before rendering. Mathematically valid original results and all prior policy/finite-grid/timing limitations remain unchanged. #602 stays open; no Pages publication or library release is claimed here.
