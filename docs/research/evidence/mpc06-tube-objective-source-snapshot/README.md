# MPC-06 source snapshots

These four files preserve source bytes in the frozen MPC-06 tube-objective
manifest. They come from commit `452db1ceb0312607fe7791b5ff4d84a2730df6ff`
and match the manifest's exact SHA-256 values. The publisher also requires the
frozen manifest SHA-256 `a4c5fc40dbb4ea72bc29d10fd72b1559abff01edbd26c0f380825fefb32c6f9e`,
so edited source inventories cannot be accepted under the historical report ID.

The snapshots cover the two Pages workflows that now apply the shared route
policy, the validator that checks this source manifest, and the test that
previously rebuilt the frozen report in place. The validator uses these files
only when the manifest names one of the four fixed hashes below. It checks every
other source against the current repository.

| Source path | SHA-256 |
| --- | --- |
| `.github/workflows/algorithm-reports.yml` | `321feccc93d8402af6e8acd39c578bdf92882483353ab692b38ef8ef7df5dc9f` |
| `.github/workflows/mpc06-tube-objective-pages-augmentation.yml` | `973be97cb17d0b5cf09fe51a6e38ecf3230c93f07398a05947739658cb6f4475` |
| `scripts/reports/stage_mpc06_tube_objective.py` | `99710a4a6a5399d64cf741ce63fad89f61b836681fbccd494c45c53fc818bfef` |
| `tests/reporting/test_mpc06_tube_objective.py` | `519c00e0e1530bbd33b8f195972fa7efab32d521c5ee7375cb7a4343f7483613` |
