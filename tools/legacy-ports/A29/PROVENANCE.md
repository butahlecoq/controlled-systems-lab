# A29 source closure and provenance

This Python 3 port transcribes the active A29 `QLPHULL.m` driver and its A30
`Modified_SM.m` helper. Original MATLAB files stay in the owner-authorized
local archive, outside Git; they are neither imported nor redistributed.
`verify_sources.py` rechecks their raw bytes against the selected-source
register. Both matched on this host on 2026-10-17 before implementation and
again after the port was written.

| Role | Archive-relative path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| A29 driver | `Scientific Research/QLPHULL.m` | 1,619 | `663625d206758ad80a56dc0ef9f3ea66cbb18b3d374d46b4fc90c4bf19d95a65` |
| A30 membership helper | `Scientific Research/Modified_SM.m` | 1,150 | `5e0f29b0bed8a87f8ec477cb0f3fae55c66f0e3e3b28021c032b9891afa9ea6a` |

The constrained-directory sibling `Modified_SM.m` used by A33 has SHA-256
`072745d6448f70d17fd12e8eea8027a87eb56be115cc33fb40737c3cc1d210b9`;
it is not silently substituted here. A29's proposed grouping/SMLP section is
commented out. A30's local `degeneracy` function is present in the original
file but its only call site is commented out, so it is not active behavior.

Source and policy anchors: `docs/research/archive-selected-sources.json`,
`docs/research/algorithm-module-inventory.md` (ordered/grouped section),
`docs/research/comparison-optimization-inventory.md`, issue #400, and issue
#424. The port's version is the Git commit containing `port.py`, `oracle.py`,
fixture and tests; generated records also pin both original SHA-256 values.
For this revision, SHA-256 of `port.py` is
`4bdd38f250314c5e87ffdea1d5919be0fd8640a3bc67df2a61241fb67a36d2da`;
SHA-256 of the independent `oracle.py` is
`90d570f4fe65d15e2379999640d5ecafc8eb6643ffd092eea04de42b35e7dd6c`.

The included synthetic square is a literal, deterministic row-wise binary64
point cloud `(x,y)`. No time grid, dynamics (`A/B/D`), controls, uncertainty,
policy class, objective, or physical units apply. It has no randomness or
seed. Historical B03 Normal/Uniform/Sphere arrays and seeds are unrecovered;
this fixture cannot reproduce B03's published MATLAB numbers.
