# A06 BTULSHOR Pascal source-body recovery

This note records a bounded read-only recovery from the owner-supplied archive on 2026-11-10. It supplements [the 1999 BTULSHOR library-manual recovery](1999-btulshor-library-manual-recovery.md) and [the selected-source register](archive-selected-sources.json). It does not close issue #2.

## Exact registered source recovered

The archive contains A06, `btulshor.pas`, at 43,261 bytes with SHA-256 `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442`. That hash matches the A06 entry in the existing register. Its one-member `btulshor.rar` contains identical source bytes. [The machine-readable evidence](evidence/btulshor-original-body-recovery.json) records opaque anchors and hashes without copying source text.

The source has a `BTULSHOR` unit and exposes the procedures `MTRAB`, `REACH`, `KPABEP`, `MODIF`, `OBREACH`, `OBRMTR`, `GIPBER`, `CRAPOV`, `ALOWER`, `VERLIM`, `CHEBR` and `HSG`. Procedure bodies are present for `REACH` (source lines 41–72), `KPABEP` (73–127) and `MODIF` (128–214). The source therefore recovers actual implementations for those routines, beyond the interfaces described in the manual.

`KPABEP` expands point columns with auxiliary rows, sets normalization and objective rows, calls `MODIF` with tolerance `1e-5`, and retains columns when its returned status is `2`. `MODIF` maintains a basis inverse and basis labels, performs phase-based reduced-cost and ratio pivots, and returns status codes `1`, `2` or `3`. These source-level observations support correspondence with the manual's reachability and vertex-filter descriptions. They do not prove correctness for all floating-point, degenerate or malformed inputs.

The Pascal unit declares `BIBTUSH` and `DIALOGS`; the implementation also uses `term` and `funfnx`. Those dependencies were not recovered as a complete buildable project. The `DIALOGS` and `MessageDlg` usage is consistent with Delphi-era code and does not establish an unchanged Turbo Pascal 1993 or 1999 release. The exact A06 hash establishes identity with the registered artifact, not its date, relationship to ITIS17, or suitability as a canonical experiment implementation.

## Related MATLAB files and registration listing

The archive includes `BTULSHOR.m` and six MATLAB neighbours. They are related sources, but this inspection found literal differences from the Pascal behavior. In the MATLAB `KPABEP`, `MODIF` returns `p`, `BERG` and `NB`, while the caller tests its unchanged local `ip`. MATLAB `MODIF` returns `X` as its second output. The MATLAB routine sets `m=n3-3`, while the Pascal call uses `m=n3`. The auxiliary-sum update also indexes `BERG(n3+j)` where the Pascal source uses `A[n3*j]`. These are source discrepancies only. No execution was used to test their effects, so this note makes no runtime-defect claim.

A separate `Свидетельство_16.rar` package was inspected in three supplied archive copies. All three container hashes match. Its `Listing.doc` identifies unit `identif`, credits Shorikov and Tyulyukin, and carries a 2016 UrFU copyright notice. The listing uses Delphi GUI units and references `bibtush` and `btulshor`, but it contains the `identif` body rather than the missing library units. It is evidence for a Delphi consumer of BTULSHOR, not an ITIS17 hull implementation, a verified registration number, or a complete project. The package's `16` label is not treated as an official registration number.

## Search scope and limits

The audit inventoried 59 matching source/container paths across the two supplied archive roots, including 52 compressed-container listings. It found no named `BIBTUSH`, `term` or `funfnx` unit, compiled unit, project file or standalone `OpenLoopControl.py` in the bounded suffix/name/member search. This does not override the previously recovered W09 standalone Python source, and it does not establish global absence outside these supplied trees and inspected containers.

No source was compiled, run, installed or benchmarked. No original source body, administrative form or personal data is included here. The evidence file records the source hash, registration-listing hash, container identity, procedure anchors and the bounds of the archive search.

The recovered A06 bytes do not supply the missing dependencies, complete historical project, canonical experiment inputs, source-to-publication version lineage, or permission to redistribute code. The 1999 manual, the registered source artifact, and a possible earlier Turbo Pascal release remain separate artifacts until direct version evidence connects them. Issue #2 remains open.
