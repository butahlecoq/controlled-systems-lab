# OBS-06 fuel phase summary

Generated from saved raw phase spans. Millisecond columns sum same-operation spans across calls; they are not wall time across different operations. Parent inclusive and child inclusive values overlap and must not be added. Exclusive values remove nested child intervals. Missing metrics remain `unavailable`.

Source commit: `3fa4e1d1b05b968f3690b966c87f3e1e7e1f7a8d`. Environment: `{"clock": {"metric": "steady wall", "period": "1/1000000000 seconds per tick"}, "configuration": "Release, BUILD_TESTING=ON, HiGHS=OFF, Qhull=OFF", "cpu_model": "AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx", "cpu_timing": "unavailable: no CPU clock supplied", "kernel": "7.2.5-3-omarchy", "load_average_at_manifest_write": [0.8134765625, 0.8330078125, 0.75927734375], "machine": "x86_64", "platform": "Linux-7.2.5-3-omarchy-x86_64-with-glibc2.44", "resources": {"native_backend_threads": "not_applicable: no external numerical backend", "process_memory_per_phase": "unavailable for B07/B09 phase rows; B06 reports process peak RSS", "requested_outer_workers": 1, "selected_worker_spans": 0}}`.

| case_id | operation | span_count | call_count | returned | rejected | not_called | failed | incomplete | inclusive_wall_ms_sum | exclusive_wall_ms_sum |
|---|---|---|---|---|---|---|---|---|---|---|
| B06-paired-run | finite-minimax/objective | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 320.58430100000004 | 320.58430100000004 |
| B06-paired-run | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.905386 | 6.905386 |
| B06-paired-run | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 1102.122455 | 1017.4203669999999 |
| B06-paired-run | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.329264 | 5.329264 |
| B06-paired-run | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.026121 | 0.026121 |
| B06-paired-run | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1461.369308 | 26.383133 |
| B06-paired-run | finite-minimax/stage-materialization | 15625 | 15625 | 15625 | 0 | 0 | 0 | 0 | 84.70208799999999 | 84.70208799999999 |
| B06-paired-run | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.018647999999999998 | 0.018647999999999998 |
| B06-unsupported-capacity-failure | finite-minimax/objective | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001396 | 0.001396 |
| B06-unsupported-capacity-failure | finite-minimax/plan-setup | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001886 | 0.001886 |
| B06-unsupported-capacity-failure | finite-minimax/propagation | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.016692 | 0.009148 |
| B06-unsupported-capacity-failure | finite-minimax/record-assembly | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.0014670000000000002 | 0.0014670000000000002 |
| B06-unsupported-capacity-failure | finite-minimax/result-selection | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.001397 | 0.001397 |
| B06-unsupported-capacity-failure | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.059645000000000004 | 0.034362000000000004 |
| B06-unsupported-capacity-failure | finite-minimax/stage-materialization | 5 | 0 | 0 | 0 | 5 | 0 | 0 | 0.007544 | 0.007544 |
| B06-unsupported-capacity-failure | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.0024449999999999997 | 0.0024449999999999997 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 56.943954 | 56.943954 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 6.035894 | 6.035894 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 425.847142 | 385.86686799999995 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.524822 | 5.524822 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 519.872197 | 25.47848 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 39.980274 | 39.980274 |
| B07-reconstruction-s0-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005238 | 0.005238 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 41.569961 | 41.569961 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.820761 | 5.820761 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 365.359247 | 326.92431500000004 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.163784000000001 | 5.163784000000001 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.027658 | 0.027658 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 440.752408 | 22.80527 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 38.434931999999996 | 38.434931999999996 |
| B07-reconstruction-s0-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005727 | 0.005727 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/objective | 3125 | 493 | 493 | 0 | 2632 | 0 | 0 | 54.243688999999996 | 54.243688999999996 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.543402 | 5.543402 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 425.28203599999995 | 385.497186 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.127716 | 5.127716 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036737 | 0.036737 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 512.946276 | 22.706969 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/stage-materialization | 15625 | 5563 | 5563 | 0 | 10062 | 0 | 0 | 39.78485 | 39.78485 |
| B07-reconstruction-s0-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005727 | 0.005727 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/objective | 3125 | 365 | 365 | 0 | 2760 | 0 | 0 | 41.484042 | 41.484042 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.576765 | 5.576765 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 366.463576 | 327.966298 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.130288 | 5.130288 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036667 | 0.036667 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 441.334333 | 22.637687 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/stage-materialization | 15625 | 5365 | 5365 | 0 | 10260 | 0 | 0 | 38.497278 | 38.497278 |
| B07-reconstruction-s0-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005308 | 0.005308 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 49.383285 | 49.383285 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.693588999999999 | 5.693588999999999 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 411.776222 | 372.657492 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.171984 | 5.171984 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036736000000000005 | 0.036736000000000005 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 494.722685 | 22.65598 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 39.11873 | 39.11873 |
| B07-reconstruction-s1-l0-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.004889 | 0.004889 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 39.080036 | 39.080036 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.688478 | 5.688478 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 360.673621 | 322.34357600000004 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.088176 | 5.088176 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.037016 | 0.037016 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 433.13792 | 22.565285 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 38.330045 | 38.330045 |
| B07-reconstruction-s1-l0-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005308 | 0.005308 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/objective | 3125 | 442 | 442 | 0 | 2683 | 0 | 0 | 49.785686000000005 | 49.785686000000005 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.555371 | 5.555371 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 408.89765700000004 | 370.122972 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.093826 | 5.093826 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036807 | 0.036807 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 491.76133 | 22.386326 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/stage-materialization | 15625 | 5512 | 5512 | 0 | 10113 | 0 | 0 | 38.774685000000005 | 38.774685000000005 |
| B07-reconstruction-s1-l1-d0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005657000000000001 | 0.005657000000000001 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/objective | 3125 | 328 | 328 | 0 | 2797 | 0 | 0 | 38.006485 | 38.006485 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/plan-setup | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.789197000000001 | 5.789197000000001 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/propagation | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 354.212633 | 316.637715 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/record-assembly | 3125 | 3125 | 3125 | 0 | 0 | 0 | 0 | 5.091567 | 5.091567 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.036807 | 0.036807 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 425.856573 | 22.714227 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/stage-materialization | 15625 | 5328 | 5328 | 0 | 10297 | 0 | 0 | 37.574918 | 37.574918 |
| B07-reconstruction-s1-l1-d1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.005657000000000001 | 0.005657000000000001 |
| B09-lambda-0 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 11.751695 | 11.751695 |
| B09-lambda-0 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.412987 | 11.412987 |
| B09-lambda-0 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 384.11298500000004 | 315.718922 |
| B09-lambda-0 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 10.937415000000001 | 10.937415000000001 |
| B09-lambda-0 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.070052 | 0.070052 |
| B09-lambda-0 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 465.159803 | 46.866916 |
| B09-lambda-0 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 68.394063 | 68.394063 |
| B09-lambda-0 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.007753 | 0.007753 |
| B09-lambda-1 | finite-minimax/objective | 6561 | 76 | 76 | 0 | 6485 | 0 | 0 | 12.008523 | 12.008523 |
| B09-lambda-1 | finite-minimax/plan-setup | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 11.230159 | 11.230159 |
| B09-lambda-1 | finite-minimax/propagation | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 381.432999 | 313.17514800000004 |
| B09-lambda-1 | finite-minimax/record-assembly | 6561 | 6561 | 6561 | 0 | 0 | 0 | 0 | 10.926277 | 10.926277 |
| B09-lambda-1 | finite-minimax/result-selection | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.054197999999999996 | 0.054197999999999996 |
| B09-lambda-1 | finite-minimax/run | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 462.12322500000005 | 46.451025 |
| B09-lambda-1 | finite-minimax/stage-materialization | 26244 | 16609 | 16609 | 0 | 9635 | 0 | 0 | 68.25785099999999 | 68.25785099999999 |
| B09-lambda-1 | finite-minimax/validation | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0.020044 | 0.020044 |

Raw input files: `b06-phase.json.gz`, `b07-phase.jsonl.gz`, `b09-lambda0-phase.json.gz`, `b09-lambda1-phase.json.gz`

B06 failure pair: baseline and instrumented capacity failures matched exactly; 12 planned failure-path spans are retained in the raw B06 record.
