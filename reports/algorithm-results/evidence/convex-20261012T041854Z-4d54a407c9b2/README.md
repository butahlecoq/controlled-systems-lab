# Supplementary collection-window evidence

This supplement belongs to `convex-20261012T041854Z-4d54a407c9b2`, measured from source `cc3d91b579d1bfbb07fb6159b6709a08cd15fa10`. It is separate from the immutable thirteen-file report bundle and offline ZIP. GitHub Pages stages only that allowlisted bundle; this supplementary evidence remains available in the repository.

`host-load-during.json` retains 35 Windows `GetSystemTimes` snapshots collected by a lightweight launcher thread at approximately 250 ms across the entire collector process (including its final provenance build and machine snapshots). Kernel counters include idle time. For each adjacent available snapshot, total CPU ticks are the increments of kernel plus user, and busy percent is `100 * (total - idle_increment) / total`. The first snapshot is a baseline; 34 intervals have a busy percentage. These are aggregate all-processor observations, not per-trial or native-phase CPU measurements. Observer overhead is retained and not subtracted; desktop services and other user activity were uncontrolled.

`concurrent-work.txt` records the coordinated quiet window, cache/workspace policy and limitations used by the unchanged collector. The main report independently retains its pre/post observations and separate-profile process counters. These supplementary observations do not establish an exclusive native limiter, a speedup or a clean-system guarantee.

`run-collection.py` is the exact supplementary launcher used for this collection, retaining the collector command and sampling calculation. It delegates the unchanged source-commit-bound collector; it does not replace its numerical timers. It is retained as provenance, with paths relative to the original build directory, rather than as an offline report renderer. Opening the report or regenerating its figures does not execute this script or rerun the solver.

No solver was rerun for packaging. Numerical payload, HTML, figures, raw files and ZIP retain their reviewed exact bytes.
