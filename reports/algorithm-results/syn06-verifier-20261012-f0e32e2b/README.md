# SYN-06 original-data verifier report

Clean fixed full harness source: `f0e32e2b8aae6a710892c5559d353da7ea70d637`; original verifier base: `edf2b200209f4312b0d00a522a7a0b2e26a96d65`.

This report times two literal witnesses of a two-stage scalar integrator. The terminal objective is `x[2]`, so its value is 1. Every timed call is checked against literal named residuals and all six claim statuses. A deliberately violating control produces a 0.25 domain violation and 0.5 transition residual. No optimal-family completeness or validated proof is established.

`records.json` and `raw-events.jsonl` contain accepted measurements. `pilot.json` and `profile.json` are separate non-report observations; the limiter is not established. The build graph and commands use `SOURCE_ROOT`/`BUILD_ROOT` placeholders, and the original build was fresh Release/C++20/NDEBUG. Run the collector from a clean checkout of the fixed harness commit with a fresh build directory and `--cmake`, `--generator`, and `--architecture` arguments.
