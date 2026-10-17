# A33 source closure and provenance

This port transcribes the **active** constrained-directory `QLPHULL.m` driver
and its two active helper calls. The originals remain in the owner-authorized
local archive, outside Git. They are neither imported nor redistributed here.
`verify_sources.py` checks their raw bytes read-only against the selected-source
register and the pinned constrained sibling. On this host all three matched on
2026-10-17 before implementation and again after the port was written.

| Role | Archive-relative path | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| A33 driver | `Публикации/Минимакс/Constrained/QLPHULL.m` | 1,778 | `6ea9ee74cb376c644ab5441e7ca747b0ad5856d7c7c32e2518ec680502c8d7ae` |
| A16 incremental/final reduction | `Scientific Research/Simplex_Hull_mod.m` | 1,131 | `ec23c8b9984f0b475044320141d07b00823b47ae052ffbe6f9e9fa9e2551321a` |
| Grouped membership | `Публикации/Минимакс/Constrained/Modified_SM.m` | 1,168 | `072745d6448f70d17fd12e8eea8027a87eb56be115cc33fb40737c3cc1d210b9` |

The selected-source A30 `Scientific Research/Modified_SM.m` has SHA-256
`5e0f29b0bed8a87f8ec477cb0f3fae55c66f0e3e3b28021c032b9891afa9ea6a`.
It is a different file and is **not** substituted. The commented A33 `SMLP`
block is not executed and has no port dependency. The A33 source initializes
`itrt` to zero and discards helper iteration values; the returned source
counter is therefore always zero, regardless of actual pivots.

Source mapping and audits: `docs/research/archive-selected-sources.json`,
`docs/research/algorithm-module-inventory.md` (ordered/grouped section), and
`docs/research/comparison-optimization-inventory.md`. Porting policy: issue
#400 and `docs/architecture/comparison-program.md`; issue #425 defines this
driver/helper closure. The port version is the Git commit containing `port.py`,
`oracle.py`, the fixture and tests; the generated output records the three
original source hashes. For this revision, SHA-256 of `port.py` is
`ea2d8b106c0b13beb25ded702414a242ab40bda1fee70b49397afcb736418ce2`;
SHA-256 of the independent `oracle.py` is
`1828ea7b3eb9b21039566a0734b7c810d4b422449a51766c6d68ed0a2be69229`.

The pinned synthetic square fixture supplies row-wise binary64 coordinates
`(x,y)` directly. No time grid, dynamics, controls, uncertainty, objective or
policy class applies to this geometric hull input. It has no randomness or
seed. The B03 Normal/Uniform/Sphere generators, seeds and full arrays are
unrecovered, so this fixture is not a replay of B03 or a substitute for its
reported MATLAB R2014a results.
