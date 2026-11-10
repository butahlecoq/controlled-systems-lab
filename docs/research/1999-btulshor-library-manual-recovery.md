# 1999 BTULSHOR library manual: publisher recovery

2026-11-10. This [issue #2](https://github.com/butahlecoq/controlled-systems-lab/issues/2) follow-up recovers a public publisher copy of the Shorikov–Tyulyukin Pascal-library manual. It does not recover the library's complete source project. Keep #2 open.

## Publisher artifact and article boundaries

The publisher's [Journal of New Economy archive](https://jne.usue.ru/en/all-issues-until-2020) leads to [1999](https://jne.usue.ru/en/all-issues-until-2020/157?task=view), whose number 2 link downloads [the complete issue](https://jne.usue.ru/download/2.pdf). The current journal [identifies its former Izvestiya title](https://jne.usue.ru/). The downloaded issue's cover independently states the university, number 2 and year 1999.

Actual download on 2026-11-10:

- Size: **8356813 bytes**; **134 PDF pages**.
- SHA-256: `a661b7ad11d035a7ed3e33766ef6af7b122c126b7fb60fa6890868be3b74ecff`.
- PDF metadata reports ABBYY FineReader 8.0 Corporate Edition and creation/modification on 2010-11-26. These are properties of the retrieved digital copy, not the article's publication date.
- Text extraction produced no usable article text. The relevant pages were rendered and read visually; no OCR transcription is treated as source authority.

The logical article occupies **PDF pages 34–44 inclusive**: page 34 has the two authors and library-description title; pages 35–43 contain the instructions, routine descriptions and final main-program section; page 44 finishes the bibliography and has a closing separator. PDF page 33 ends the preceding article, and page 45 starts a different article by Fedorov and Smolyaninova. This establishes the inspected logical extent of this digital copy.

Its table of contents on PDF page 2 gives the library article's start as **printed page 36** and the following article's start as **50**. That supports the bibliographic range **36–49** used in the [2021 paper's reference 13](https://journals.ssau.ru/vestnik/ru/article/view/8635) and [2019 paper's reference 9](https://vestnik.susu.ru/ctcr/article/download/8019/7026). However, the recovered article spans eleven PDF pages, not fourteen, and no continuous printed page numbering was visible within those article images. The preceding PDF page 33 visibly carries printed page 35. Do not assign internal printed page numbers by a constant offset or infer why this digital copy's pagination differs. Missing/reformatted material or a bibliographic error is not established by this observation.

The displayed title uses the Russian word for **subprograms** (`подпрограмм`); the later citations use the shorter **programs** wording. Authors, subject and issue contents identify the manual, but the title variation and pagination are retained rather than silently normalized.

## What was actually recovered

The manual describes Turbo Pascal on IBM PC/AT. PDF page 35 names the module **BTULSHOR**, main program **FILTR**, interface-visible array types and column-major flattened arrays. PDF page 43 also names **BTULSHOR.TPU**. These are concrete historical artifact search keys.

| PDF pages | Manual interface or role |
|---|---|
| 35–36 | `REACH`: one-step affine reachable-set vertex construction, calling the vertex-filter routine |
| 36–37 | Vertex filter, printed `КРАВЕР` (transliterated `KRAVER`): affine nonnegative normalized representation by other points, using the LP routine |
| 37–38 | `MODIF`: LP interface, tolerance and outcome parameters; describes optimal, inconsistent and unbounded outcomes |
| 38–40 | `GIPBER` and `CRAPOV`: polyhedral representation procedures, with supporting helper names |
| 40–43 | `CHEBR`, `HSG`, then the `FILTR` main-program description |

The inspected span is a mathematical/interface manual with call signatures and usage notes. It does **not display complete Pascal routine bodies or a complete compilable project** in that span. No software-download address, package attachment, registration identifier or distribution instructions were found there. This is a bounded observation about the recovered article, not a claim that no project was ever distributed elsewhere. No implementation was executed or adapted.

## Relation to registered local sources

The unchanged [selected-source register](archive-selected-sources.json) identifies A06 as `Статьи/А.Ф. Шориков/btulshor.pas`, SHA-256 `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442`, and A07 as `Scientific Research/BTULSHOR/BTULSHOR.m`, SHA-256 `59c7849bb4ad79bd910f79343583de60552cb5a939d0bf19874a3e91a07bf004`. A later archive recovery now provides the exact A06 bytes and confirms implementations for `REACH`, `KPABEP` and `MODIF`; see the [bounded A06 source-body recovery](btulshor-original-body-recovery.md). The [existing A06 interface audit](temporal-lift-source-audit.md) records `REACH`, `OBREACH` and missing external type units.

The public manual independently establishes **the BTULSHOR name and historical Pascal-library description**. The later A06 recovery confirms the registered source bytes and supplies bodies for selected routines, but matching names do not establish that A06 is the 1999 manual's release. It establishes neither complete dependency recovery, compatibility of A07, a historical release, nor ownership/permission to redistribute source. The 1993 Pascal claim and later ITIS17 modifications remain separate evidence; old captures retain their original qualification.

Next work is to locate the named library/project and its dependencies, then compare a versioned source with the manual and registered hashes. The article and its page images remain outside the repository. This change adds research documentation only: no public API, dependency, installation, publication workflow, license grant, benchmark or release/package change.
