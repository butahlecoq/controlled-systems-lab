# L08 embedded-equation provenance: B05 Table 2 policy labels

Date: 2026-10-18. This bounded source-reading follow-up supports [issue #2](https://github.com/butahlecoq/controlled-systems-lab/issues/2); it does not reconstruct the publication-generating run. Inventory entry L08 identifies the inspected draft by source ID, size (507,904 bytes), and SHA-256 `9ac92be986a5f4a5ef9942cc611a66075d0ba7dae02a44cd9442112536b7395c`. The original source bytes were read only and remain local.

## Method and comparison source

The legacy Word compound file contains 85 distinct `Equation Native` streams. Read-only extraction and hashing used `olefile` 0.47. Word 16.0 (build 16.0.17932) opened the document read-only with automation security set to `ForceDisable`; temporary PDF and DOCX derivatives were created outside the repository. No embedded Equation Editor object was activated, and the original document's size and SHA-256 remained equal to the inventory values after inspection. Python 3.13.5 was used for extraction checks.

The temporary DOCX relationships and document order map the ten embedded objects in draft page 10, Table 2, to opaque stream IDs E01–E10 below. The mapping was checked against the [publisher's Part II PDF](https://vestnik.susu.ru/ctcr/article/download/8019/7026), DOI [10.14529/ctcr190203](https://doi.org/10.14529/ctcr190203), printed page 34 (PDF page 6 of 9). The downloaded PDF SHA-256 was `c91cadc73dc75fc42ef7fa1acfb0c2c37579d3e1ad9a62c872a03bdb5ca25437`. Visual comparison confirms the row grouping and labels, and the published terminal-coordinate/objective tuples match the draft's extracted rows. The reference-control notation is `u(t) ≡ 0` in the draft and `u(t) = 0` in the publication.

| Draft Table 2 row | Restored policy label | Terminal state | Reported criterion | Stream | Bytes | `Equation Native` SHA-256 |
|---:|---|---|---:|---|---:|---|
| 1 | Reference: `u(t) ≡ 0` | (1200, 0, 450, 0) | 0 | E01 | 255 | `7ec93efb79cf2009647439a62729d96dda3e0a0d029ccdd6ff68ff46f093992c` |
| 2 | Nonlinear open-loop, j=1: `u⁽ᵉ,¹⁾(t)` | (1200.1, 39.1, 450, 10.6) | 48.261 | E02 | 294 | `1dad7594b3ea7de68510f9768e03a82acdf616a7adc7fc24bba574b225f9f0f8` |
| 3 | Nonlinear adaptive, j=1: `uₐ⁽ᵉ,¹⁾(x(t))` | (1200.2, 32.7, 449.9, 8.5) | 39.837 | E03 | 315 | `da08b7c4d54446f7b60caf1fb31b0e6c88eb0f9d1cdc45ef8462f049ec390fbb` |
| 4 | Nonlinear open-loop, j=2: `u⁽ᵉ,²⁾(t)` | (1200.1, 39.6, 450, 12.1) | 51.021 | E04 | 294 | `9e3bdb74ec5ab017d8a49e9b03076e9b2e2a9a2af288dd270b2dc5c09902ac38` |
| 5 | Nonlinear adaptive, j=2: `uₐ⁽ᵉ,²⁾(x(t))` | (1200.1, 36.3, 450, 9.5) | 44.228 | E05 | 315 | `9da30b25f1db2fa79bd777f9ad61a04c92cf3e5dd78d48b7fabfb31b7d3cd6b7` |
| 6 | Nonlinear open-loop, j=3: `u⁽ᵉ,³⁾(t)` | (1200, 38.7, 450, 9.6) | 46.339 | E06 | 294 | `856338a01b7154fdadbf257418f72e5f3c81cd0649d648e786fbba6ba93b9a22` |
| 7 | Nonlinear adaptive, j=3: `uₐ⁽ᵉ,³⁾(x(t))` | (1200.1, 31.1, 450, 8.2) | 37.935 | E07 | 315 | `2cfd325af1ebc9be737ab7b83ce7813ded4933a368daeb4c0a2db0af131587c8` |
| 8 | Nonlinear open-loop, j=4: `u⁽ᵉ,⁴⁾(t)` | (1200.1, 39.9, 450, 10.6) | 48.906 | E08 | 294 | `8007e224d0803e16d2cf502a840bed7e5a2404bbf58a11bb3f8e3df28af5f2cf` |
| 9 | Nonlinear adaptive, j=4: `uₐ⁽ᵉ,⁴⁾(x(t))` | (1200, 36.6, 450, 10.1) | 45.372 | E09 | 315 | `a1dec46a87be3b5e0b29a0cc2368a062aafe09f556913963a6ed2ac2a7c44c37` |
| 10 | Linear open-loop: `u⁽ᵉ,ʲ⁾(t)` | (1200.1, 39, 450, 10.5) | 47.988 | E10 | 294 | `bd932f134a5dbe23826f06ac443c3a59353c17c88226992b8e886871544bdf1b` |

The tuple match establishes the row-policy assignment for this published comparison table. It does not establish that any stream is the canonical optimizer output or that a historical run can be reproduced.

## Limits and remaining recovery

Only the ten Table 2 streams were mapped. The other 75 embedded streams and the figures were not audited here. This note does not recover the complete historical implementation, optimizer inputs, control histories, or generating project; it does not execute a historical implementation or claim a reproduced run. Original papers and extracted source material remain local. Source IDs and stream digests are published as evidence identifiers, not as a source release. Issue #2 remains open for canonical revision/input matching, original projects and numerical inputs, remaining embedded equations, provenance, and any permission required for source release.
