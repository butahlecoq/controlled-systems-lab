# OBS-06 fuel phase summary

Generated from saved raw phase spans. Millisecond columns sum same-operation spans across calls; they are not wall time across different operations. Parent inclusive and child inclusive values overlap and must not be added. Exclusive values remove nested child intervals. Missing metrics remain `unavailable`.

Source commit: `dc06f0a8fcb9301b0397b7c184c5b17d50a70474`. Environment: `{"clock": {"metric": "steady wall", "period": "1/1000000000 seconds per tick"}, "configuration": "Release, BUILD_TESTING=ON, HiGHS=OFF, Qhull=OFF", "cpu_model": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx", "cpu_timing": "unavailable: no CPU clock supplied", "kernel": "7.2.5-3-omarchy", "load_average_at_manifest_write": [0.69970703125, 0.82177734375, 0.767578125], "machine": "x86_64", "platform": "Linux-7.2.5-3-omarchy-x86_64-with-glibc2.44", "resources": {"native_backend_threads": "not_applicable: no external numerical backend", "process_memory_per_phase": "unavailable for B07/B09 phase rows; B06 reports process peak RSS", "requested_outer_workers": 1, "selected_worker_spans": 0}}`.

| case_id | operation | span_count | call_count | returned | rejected | not_called | failed | incomplete | inclusive_wall_ms_sum | exclusive_wall_ms_sum |
|---|---|---|---|---|---|---|---|---|---|---|
| B06-paired-run | finite-minimax/objective | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 323.900692 | 323.900692 |
| B06-paired-run | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 7.2207740000000005 | 7.2207740000000005 |
| B06-paired-run | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 1104.881159 | 1020.131178 |
| B06-paired-run | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.320077 | 5.320077 |
| B06-paired-run | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.02647 | 0.02647 |
| B06-paired-run | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1467.647477 | 26.281612 |
| B06-paired-run | finite-minimax/stage-materialization | 15625 | 15625 | 15625 | 0 | 0 | 0 | 0 | 84.749981 | 84.749981 |
| B06-paired-run | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.016693 | 0.016693 |
| B06-unsupported-capacity-failure | finite-minimax/objective | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003771 | 0.003771 |
| B06-unsupported-capacity-failure | finite-minimax/plan-setup | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003772 | 0.003772 |
| B06-unsupported-capacity-failure | finite-minimax/propagation | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.037505000000000004 | 0.019835 |
| B06-unsupported-capacity-failure | finite-minimax/record-assembly | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003352 | 0.003352 |
| B06-unsupported-capacity-failure | finite-minimax/result-selection | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003352 | 0.003352 |
| B06-unsupported-capacity-failure | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.08276299999999999 | 0.028566 |
| B06-unsupported-capacity-failure | finite-minimax/stage-materialization | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0.017669999999999998 | 0.017669999999999998 |
| B06-unsupported-capacity-failure | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.0024449999999999997 | 0.0024449999999999997 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 57.221894 | 57.221894 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.982959 | 5.982959 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 443.056862 | 402.005972 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.28583 | 5.28583 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036876 | 0.036876 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 534.450739 | 22.848718 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 41.05089 | 41.05089 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.0176 | 0.0176 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 44.785726999999994 | 44.785726999999994 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.262877 | 6.262877 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 374.474671 | 334.601763 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.77873 | 5.77873 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036597000000000005 | 0.036597000000000005 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 457.301847 | 25.958146000000003 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 39.872907999999995 | 39.872907999999995 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005098999999999999 | 0.005098999999999999 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 57.533414 | 57.533414 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.279475 | 6.279475 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 434.229644 | 393.259572 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.486006 | 5.486006 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036946 | 0.036946 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 529.116453 | 25.544264000000002 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 40.970072 | 40.970072 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.006704 | 0.006704 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 44.953105 | 44.953105 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.3669340000000005 | 6.3669340000000005 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 372.048557 | 332.624164 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.563772 | 5.563772 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.027797000000000002 | 0.027797000000000002 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 455.393595 | 26.428192 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 39.424393 | 39.424393 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005238 | 0.005238 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 49.985251 | 49.985251 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.763823 | 5.763823 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 410.894186 | 371.482455 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.173727 | 5.173727 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 494.53799599999996 | 22.679104 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 39.411730999999996 | 39.411730999999996 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005238 | 0.005238 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 39.383995999999996 | 39.383995999999996 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.6622189999999994 | 5.6622189999999994 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 356.02024700000004 | 317.640312 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.248088 | 5.248088 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.0264 | 0.0264 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 428.957953 | 22.611904 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 38.379934999999996 | 38.379934999999996 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005098999999999999 | 0.005098999999999999 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 50.47501 | 50.47501 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.701681 | 5.701681 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 413.149279 | 373.22504899999996 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.266983000000001 | 5.266983000000001 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 497.391152 | 22.756294 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 39.92423 | 39.92423 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005238 | 0.005238 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 38.644791999999995 | 38.644791999999995 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.699404 | 5.699404 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 360.76066000000003 | 322.222533 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.171479 | 5.171479 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.025004 | 0.025004 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 432.888495 | 22.582337000000003 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 38.538126999999996 | 38.538126999999996 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.004819 | 0.004819 |
| B09-lambda-0 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 11.634853 | 11.634853 |
| B09-lambda-0 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.290501999999998 | 11.290501999999998 |
| B09-lambda-0 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 381.409855 | 313.16905699999995 |
| B09-lambda-0 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.15731 | 11.15731 |
| B09-lambda-0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.066839 | 0.066839 |
| B09-lambda-0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 462.433117 | 46.854273 |
| B09-lambda-0 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 68.24079800000001 | 68.24079800000001 |
| B09-lambda-0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.019485000000000002 | 0.019485000000000002 |
| B09-lambda-1 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 11.786346 | 11.786346 |
| B09-lambda-1 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.323471999999999 | 11.323471999999999 |
| B09-lambda-1 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 387.445359 | 318.324903 |
| B09-lambda-1 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 10.910771 | 10.910771 |
| B09-lambda-1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.058807 | 0.058807 |
| B09-lambda-1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 468.105393 | 46.572676 |
| B09-lambda-1 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 69.12045599999999 | 69.12045599999999 |
| B09-lambda-1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.007961999999999999 | 0.007961999999999999 |

Raw input files: `b06-phase.json.gz`, `b07-phase.jsonl.gz`, `b09-lambda0-phase.json.gz`, `b09-lambda1-phase.json.gz`

B06 failure pair: baseline and instrumented capacity failures matched exactly; 12 planned failure-path spans are retained in the raw B06 record.
