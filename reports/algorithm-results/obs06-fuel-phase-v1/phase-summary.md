# OBS-06 fuel phase summary

Generated from saved raw phase spans. Millisecond columns sum same-operation spans across calls; they are not wall time across different operations. Parent inclusive and child inclusive values overlap and must not be added. Exclusive values remove nested child intervals. Missing metrics remain `unavailable`.

Source commit: `c84ccc75cbb9abe01072bf244a32077de65454b2`. Environment: `{"clock": {"metric": "steady wall", "period": "1/1000000000 seconds per tick"}, "configuration": "Release, BUILD_TESTING=ON, HiGHS=OFF, Qhull=OFF", "cpu_model": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx", "cpu_timing": "unavailable: no CPU clock supplied", "kernel": "7.2.5-3-omarchy", "load_average_at_manifest_write": [1.46, 1.62, 1.12], "machine": "x86_64", "platform": "Linux-7.2.5-3-omarchy-x86_64-with-glibc2.44", "resources": {"native_backend_threads": "not_applicable: no external numerical backend", "process_memory_per_phase": "unavailable for B07/B09 phase rows; B06 reports process peak RSS", "requested_outer_workers": 1, "selected_worker_spans": 0}}`.

| case_id | operation | span_count | call_count | returned | rejected | not_called | failed | incomplete | inclusive_wall_ms_sum | exclusive_wall_ms_sum |
|---|---|---|---|---|---|---|---|---|---|---|
| B06-paired-run | finite-minimax/objective | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 362.405556 | 362.405556 |
| B06-paired-run | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 7.766987 | 7.766987 |
| B06-paired-run | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 1139.790281 | 1044.642757 |
| B06-paired-run | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.615765 | 5.615765 |
| B06-paired-run | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036807 | 0.036807 |
| B06-paired-run | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1547.9872699999999 | 32.35602 |
| B06-paired-run | finite-minimax/stage-materialization | 15625 | 15625 | 15625 | 0 | 0 | 0 | 0 | 95.147524 | 95.147524 |
| B06-paired-run | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.015854 | 0.015854 |
| B06-unsupported-capacity-failure | finite-minimax/objective | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001397 | 0.001397 |
| B06-unsupported-capacity-failure | finite-minimax/plan-setup | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.0014670000000000002 | 0.0014670000000000002 |
| B06-unsupported-capacity-failure | finite-minimax/propagation | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.015714 | 0.008662 |
| B06-unsupported-capacity-failure | finite-minimax/record-assembly | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001397 | 0.001397 |
| B06-unsupported-capacity-failure | finite-minimax/result-selection | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001327 | 0.001327 |
| B06-unsupported-capacity-failure | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.038763 | 0.015574999999999999 |
| B06-unsupported-capacity-failure | finite-minimax/stage-materialization | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0.007052 | 0.007052 |
| B06-unsupported-capacity-failure | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.001886 | 0.001886 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 61.693522 | 61.693522 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.299646 | 6.299646 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 462.864637 | 419.292859 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.528792 | 5.528792 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036807 | 0.036807 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 565.733154 | 29.286702000000002 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 43.571778 | 43.571778 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.023048 | 0.023048 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 50.910261 | 50.910261 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.350035 | 6.350035 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 427.876268 | 384.311589 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.5493570000000005 | 5.5493570000000005 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.028496 | 0.028496 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 520.1437169999999 | 29.399756999999997 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 43.564679000000005 | 43.564679000000005 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.029543000000000003 | 0.029543000000000003 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 60.809062999999995 | 60.809062999999995 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.039524 | 6.039524 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 433.138236 | 391.97343 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.48811 | 5.48811 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.049099 | 0.049099 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 535.276787 | 29.736131999999998 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 41.164806 | 41.164806 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.016623 | 0.016623 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 45.209997 | 45.209997 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.75644 | 5.75644 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 379.34951700000005 | 340.169813 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.233658 | 5.233658 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 463.08600900000005 | 27.475844 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 39.179704 | 39.179704 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.023886 | 0.023886 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 57.977534999999996 | 57.977534999999996 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.442769999999999 | 6.442769999999999 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 443.79970099999997 | 401.765111 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.497579 | 5.497579 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 543.501846 | 29.727549 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 42.034589999999994 | 42.034589999999994 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.020045 | 0.020045 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 41.283798 | 41.283798 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.666298 | 5.666298 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 370.32553 | 330.69512899999995 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.149342000000001 | 5.149342000000001 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036737 | 0.036737 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 449.09273 | 26.613425 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 39.630401 | 39.630401 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.0176 | 0.0176 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 54.446754999999996 | 54.446754999999996 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.122873 | 6.122873 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 413.160037 | 373.258556 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.484293 | 5.484293 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036387 | 0.036387 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 508.280096 | 29.014037 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 39.901481000000004 | 39.901481000000004 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.015714 | 0.015714 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 43.00321 | 43.00321 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.231566 | 6.231566 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 366.447723 | 326.97278800000004 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.534631 | 5.534631 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.027098999999999998 | 0.027098999999999998 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 450.756279 | 29.497942 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 39.474935 | 39.474935 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.014107999999999999 | 0.014107999999999999 |
| B09-lambda-0 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 18.445695 | 18.445695 |
| B09-lambda-0 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 12.552894 | 12.552894 |
| B09-lambda-0 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 386.73017300000004 | 317.91261599999996 |
| B09-lambda-0 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.503664 | 11.503664 |
| B09-lambda-0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.062019000000000005 | 0.062019000000000005 |
| B09-lambda-0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 491.71335300000004 | 62.382101000000006 |
| B09-lambda-0 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 68.81755700000001 | 68.81755700000001 |
| B09-lambda-0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036807 | 0.036807 |
| B09-lambda-1 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 17.898443999999998 | 17.898443999999998 |
| B09-lambda-1 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 12.301452 | 12.301452 |
| B09-lambda-1 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 389.765518 | 321.465167 |
| B09-lambda-1 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.412972 | 11.412972 |
| B09-lambda-1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.073334 | 0.073334 |
| B09-lambda-1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 492.00752 | 60.517527 |
| B09-lambda-1 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 68.30035099999999 | 68.30035099999999 |
| B09-lambda-1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.038272999999999995 | 0.038272999999999995 |

Raw input files: `b06-phase.json.gz`, `b07-phase.jsonl.gz`, `b09-lambda0-phase.json.gz`, `b09-lambda1-phase.json.gz`

B06 failure pair: baseline and instrumented capacity failures matched exactly; 12 planned failure-path spans are retained in the raw B06 record.
