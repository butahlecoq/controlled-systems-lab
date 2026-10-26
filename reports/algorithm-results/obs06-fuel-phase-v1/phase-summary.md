# OBS-06 fuel phase summary

Generated from saved raw phase spans. Millisecond columns sum same-operation spans across calls; they are not wall time across different operations. Parent inclusive and child inclusive values overlap and must not be added. Exclusive values remove nested child intervals. Missing metrics remain `unavailable`.

Source commit: `953c74fbf71549501b1bb0fb7b6f9aec18326f55`. Environment: `{"clock": {"metric": "steady wall", "period": "1/1000000000 seconds per tick"}, "configuration": "Release, BUILD_TESTING=ON, HiGHS=OFF, Qhull=OFF", "cpu_model": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx", "cpu_timing": "unavailable: no CPU clock supplied", "kernel": "7.2.5-3-omarchy", "load_average_at_manifest_write": [0.69970703125, 0.82177734375, 0.767578125], "machine": "x86_64", "platform": "Linux-7.2.5-3-omarchy-x86_64-with-glibc2.44", "resources": {"native_backend_threads": "not_applicable: no external numerical backend", "process_memory_per_phase": "unavailable for B07/B09 phase rows; B06 reports process peak RSS", "requested_outer_workers": 1, "selected_worker_spans": 0}}`.

| case_id | operation | span_count | call_count | returned | rejected | not_called | failed | incomplete | inclusive_wall_ms_sum | exclusive_wall_ms_sum |
|---|---|---|---|---|---|---|---|---|---|---|
| B06-paired-run | finite-minimax/objective | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 362.725171 | 362.725171 |
| B06-paired-run | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 7.707314 | 7.707314 |
| B06-paired-run | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 1151.715141 | 1054.105624 |
| B06-paired-run | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.887489 | 5.887489 |
| B06-paired-run | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.024375 | 0.024375 |
| B06-paired-run | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1562.305482 | 34.220291 |
| B06-paired-run | finite-minimax/stage-materialization | 15625 | 15625 | 15625 | 0 | 0 | 0 | 0 | 97.60951700000001 | 97.60951700000001 |
| B06-paired-run | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.025701 | 0.025701 |
| B06-unsupported-capacity-failure | finite-minimax/objective | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001397 | 0.001397 |
| B06-unsupported-capacity-failure | finite-minimax/plan-setup | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001397 | 0.001397 |
| B06-unsupported-capacity-failure | finite-minimax/propagation | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.015785 | 0.008172 |
| B06-unsupported-capacity-failure | finite-minimax/record-assembly | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.0014670000000000002 | 0.0014670000000000002 |
| B06-unsupported-capacity-failure | finite-minimax/result-selection | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001885 | 0.001885 |
| B06-unsupported-capacity-failure | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.039531 | 0.015715 |
| B06-unsupported-capacity-failure | finite-minimax/stage-materialization | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0.007613 | 0.007613 |
| B06-unsupported-capacity-failure | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.001885 | 0.001885 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 79.893369 | 79.893369 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 8.693843 | 8.693843 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 648.4821029999999 | 584.696584 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.8385169999999995 | 6.8385169999999995 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.082972 | 0.082972 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 781.89697 | 37.888634999999994 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 63.785519 | 63.785519 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.017530999999999998 | 0.017530999999999998 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 48.020299 | 48.020299 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.430092999999999 | 6.430092999999999 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 431.429856 | 388.97173499999997 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.337877000000001 | 5.337877000000001 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.043023 | 0.043023 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 519.8222470000001 | 28.542521 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 42.458121 | 42.458121 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.018578 | 0.018578 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 61.443767 | 61.443767 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.8144540000000005 | 6.8144540000000005 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 494.254062 | 450.18883 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.724967 | 5.724967 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.025702 | 0.025702 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 599.640359 | 31.357991000000002 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 44.065232 | 44.065232 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.019416 | 0.019416 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 52.666338 | 52.666338 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 9.587681 | 9.587681 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 458.270883 | 409.907943 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.162936 | 6.162936 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.033455 | 0.033455 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 560.824428 | 34.084486999999996 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 48.36294 | 48.36294 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.018647999999999998 | 0.018647999999999998 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 56.933973 | 56.933973 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.742978 | 6.742978 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 471.16985300000005 | 427.124822 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.727957 | 5.727957 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.031429 | 0.031429 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 571.8889780000001 | 31.254852 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 44.045031 | 44.045031 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.027936000000000002 | 0.027936000000000002 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 43.700607000000005 | 43.700607000000005 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.452618999999999 | 6.452618999999999 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 430.84828699999997 | 387.766897 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.413310999999999 | 5.413310999999999 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036736000000000005 | 0.036736000000000005 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 515.349426 | 28.879847 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 43.08139 | 43.08139 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.018019 | 0.018019 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 53.804627 | 53.804627 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.307849 | 6.307849 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 454.10453099999995 | 412.59814700000004 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.521761 | 5.521761 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.030102 | 0.030102 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 549.32098 | 29.531227 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 41.506384 | 41.506384 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.020883 | 0.020883 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 39.635470999999995 | 39.635470999999995 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.972271 | 5.972271 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 391.806659 | 351.75946200000004 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.4555180000000005 | 5.4555180000000005 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.02626 | 0.02626 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 470.677326 | 27.75761 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 40.047197 | 40.047197 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.023537 | 0.023537 |
| B09-lambda-0 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 14.131748 | 14.131748 |
| B09-lambda-0 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 13.876951 | 13.876951 |
| B09-lambda-0 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 432.148467 | 354.748434 |
| B09-lambda-0 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 12.351588999999999 | 12.351588999999999 |
| B09-lambda-0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.051054999999999996 | 0.051054999999999996 |
| B09-lambda-0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 536.1438469999999 | 62.070704 |
| B09-lambda-0 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 77.400033 | 77.400033 |
| B09-lambda-0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1.513333 | 1.513333 |
| B09-lambda-1 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 12.830617 | 12.830617 |
| B09-lambda-1 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 12.688009000000001 | 12.688009000000001 |
| B09-lambda-1 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 430.048165 | 355.81845899999996 |
| B09-lambda-1 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.709026000000001 | 11.709026000000001 |
| B09-lambda-1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.061042000000000006 | 0.061042000000000006 |
| B09-lambda-1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 524.4834699999999 | 57.105265 |
| B09-lambda-1 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 74.22970600000001 | 74.22970600000001 |
| B09-lambda-1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.041346 | 0.041346 |

Raw input files: `b06-phase.json.gz`, `b07-phase.jsonl.gz`, `b09-lambda0-phase.json.gz`, `b09-lambda1-phase.json.gz`

B06 failure pair: baseline and instrumented capacity failures matched exactly; 12 planned failure-path spans are retained in the raw B06 record.
