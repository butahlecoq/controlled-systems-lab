# REVIEW-05 pinned HiGHS internal clocks

This bounded HORIZON-01 diagnostic capture includes 42 independently verified attempts, at horizons 2, 4 and 8, with one excluded warmup pair and six alternating measured pairs per horizon. It records native simplex and factorization clocks, including INVERT, FTRAN and BTRAN. Timer scopes overlap and are never summed. Diagnostic overhead prevents comparison with uninstrumented timings.

`capture.zip` contains the complete retained stdout/stderr, inputs, attempts, checks, summaries, HTML report, build receipt and per-file SHA256SUMS. Extract it into an empty directory and open `index.html`. The source revision is `8abaf50b1dc612eeb9deaf1827c8e57042e8364f`; checker revision `c8ecccb95324afe915c9d980106bb7aaa8c75758` adds stdout/result equality verification. The executable was built from matching adapter source before that source commit; this provenance limitation is retained in the build receipt.

Recheck from the repository root:

```sh
python3 benchmarks/reporting/review05/check_horizon_ladder.py --bundle <EXTRACTED_DIRECTORY>
```

The current checker verifies all 42 attempts and rejects tampered stdout even when its recorded hash is updated. This increment does not complete issue #95. Pages routing and broader scalability coverage remain separate work.
