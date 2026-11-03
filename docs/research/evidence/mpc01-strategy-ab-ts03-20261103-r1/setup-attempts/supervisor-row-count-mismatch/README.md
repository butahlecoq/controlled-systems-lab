# Setup attempt: supervisor expected the wrong row count

The algorithm process exited successfully and emitted one header plus twelve passed trials (one warmup pair and five measured pairs). The post-run supervisor mistakenly expected ten trials, so the outer capture command returned nonzero after preserving the valid algorithm output. This attempt is retained for transparency; the canonical record uses a fresh rerun with the corrected supervisor count.
