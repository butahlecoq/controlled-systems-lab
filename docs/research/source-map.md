# Original source map

Inventory date: 2026-10-11. Original artifacts: 31 files, including 21 PDFs (226 pages), five Python files, two DOCX files, two content-bearing legacy DOC files, and one Office lock file. [Full SHA-256 inventory](inventory.json).

## Artifact register

Original filenames are retained for provenance; original files and extracted text are local-only and intentionally untracked in the public repository. English descriptions below are editorial summaries.

| ID | Original artifact | Extracted text | Initial interpretation |
|---|---|---|---|
| L01 | papers/1993 АиТ Алгоритм решения задачи терминального управления для ЛДС.pdf | Local: L01.txt | 1993 foundational terminal-control algorithm; LTV dynamics, compact convex constraints, forward/backward reachable constructions and LP. |
| L02 | papers/1997 Алгоритм решения задачи оптимального терминального управления в ЛДДС.pdf | Local: L02.txt | General optimal terminal and adaptive control, including production planning. Filename says 1997; L04 references an identically titled 2005 work. Publication identification remains provisional. |
| L03 | papers/pardalos.docx | Local: L03.txt | Reachability chapter draft: vertex redundancy, simplex reuse, ordering and divide-and-conquer hull construction. Filename alone does not establish authorship by Pardalos. |
| L04 | papers/Shorikov_Kalev_AиT_New.pdf | Local: L04.txt | 2020-labelled minimax open-loop article revision; four-state, four-step fuel example, 625 control sequences. Different from the five-step examples in L09/L10. |
| L05 | papers/АППРОКСИМАЦИЯ ОБЛАСТЕЙ ДОСТИЖИМОСТИ .pdf | Local: L05.txt | 2018 nonlinear reachability approximation article, DOI 10.18101/2304-5728-2018-1-52-65. Two numerical examples and substantial differences between baseline/modified polytope volumes. |
| L06 | papers/Пояснительная записка.docx | Local: L06.txt | Editable explanatory report; paragraph extraction does not recover all image equations. Use PDF L07 for mathematics. |
| L07 | papers/Пояснительная записка.pdf | Local: L07.txt | 60-page report: flight mechanics, liquid slosh, elastic modes, descriptor formulation, LTV discretization and polytope algorithms. PDF metadata dates 2016; metadata is not publication proof. |
| L08 | papers/Шориков АФ Калев ВИ Вестник ЮУрГУ_Часть 2 new.doc | Local: L08.txt | Adaptive optimal fuel control, Part II draft; published counterpart DOI 10.14529/ctcr190203. Legacy embedded equations not decoded; table text is accessible. |
| L09 | papers/Шориков АФ, Калев ВИ статья в Косм. иссл..pdf | Local: L09.txt | Minimax open-loop fuel draft; five-step, 3125-action-sequence example with synchronization penalty. Different objective from L10. |
| L10 | papers/Шориков, Калев, статья.pdf | Local: L10.txt | Minimax open-loop fuel draft with robust state constraints; five-step enumeration prunes 3125 sequences to 365. Weighted terminal objective without L09 synchronization term. |
| L11 | papers/ШориковАФ, КалевВИ, последняя версия.pdf | Local: L11.txt | 2019-labelled optimal open-loop terminal fuel draft; four-state, 16-step example; weighted criterion with synchronization penalty; reported optimum 30.899. |
| L12 | papers/ШориковАФ, КалевВИ, текст.doc | Local: L12.txt | Editable draft in the optimal-control family of L11; not byte-identical. Equation Editor objects not decoded. |
| L13 | papers/Электронная версия_статьи.pdf | Local: L13.txt | Published 2019 minimax adaptive fuel study, Samara Aerospace 18(4), 129–145; DOI 10.18287/2541-7533-2019-18-4-129-145. Four-step, nine-action receding-open-loop example. |
| L14 | Свидетельства/Свидетельство на ПО №3 (опт. прогр)/Листинг.pdf | Local: L14.txt | Optimal open-loop listing, PDF only: OpenLoopControl, ConvexProgram, Snatch and LPControl. Missing standalone OpenLoopControl.py. |
| L15 | Свидетельства/Свидетельство на ПО №3 (опт. прогр)/Реферат.pdf | Local: L15.txt | Registration abstract for optimal open-loop program; scope/copyright metadata, not an algorithm proof. |
| L16 | Свидетельства/Свидетельство на ПО №4 (опт. адапт)/ClosedLoopControl.py | Local: L16.txt | Optimal adaptive ClosedLoopControl.py: solve remaining horizon, apply first action, advance plant. Implicit globals and missing standalone imports. |
| L17 | Свидетельства/Свидетельство на ПО №4 (опт. адапт)/Листинг.pdf | Local: L17.txt | PDF listing corresponding to L16. |
| L18 | Свидетельства/Свидетельство на ПО №4 (опт. адапт)/Реферат.pdf | Local: L18.txt | Optimal adaptive registration abstract. |
| L19 | Свидетельства/Свидетельство на ПО №5 (минимакс. прогр)/MinimaxOpenLoopControl.py | Local: L19.txt | Minimax open-loop Python module: finite-action enumeration, polytope operations, simplex, H/V conversion, terminal optimization. |
| L20 | Свидетельства/Свидетельство на ПО №5 (минимакс. прогр)/Листинг.pdf | Local: L20.txt | PDF listing corresponding to minimax open-loop module L19; formatting is less suitable for execution. |
| L21 | Свидетельства/Свидетельство на ПО №5 (минимакс. прогр)/Реферат.pdf | Local: L21.txt | Minimax open-loop registration abstract; finite controls and convex bounded disturbances. |
| L22 | Свидетельства/Свидетельство на ПО №6 (минимакс. адапт)/ClosedLoopControl.py | Local: L22.txt | Byte-identical to L16 despite minimax-adaptive folder name. No distinct minimax adaptive source recovered. |
| L23 | Свидетельства/Свидетельство на ПО №6 (минимакс. адапт)/Листинг.pdf | Local: L23.txt | Byte-identical to L17 despite minimax-adaptive folder name. |
| L24 | Свидетельства/Свидетельство на ПО №6 (минимакс. адапт)/Реферат.pdf | Local: L24.txt | Byte-identical to L18; even the abstract is the optimal adaptive abstract. |
| L25 | Свидетельства/Свидетельство №1 (ОД)/Listing.pdf | Local: L25.txt | PDF listing for reachable-set program L26. |
| L26 | Свидетельства/Свидетельство №1 (ОД)/ReachableSet.py | Local: L26.txt | Python 2 reachable-set code; forward/backward construction, redundancy elimination, simplex and double description. |
| L27 | Свидетельства/Свидетельство №1 (ОД)/Реферат.pdf | Local: L27.txt | Reachable-set program registration abstract. |
| L28 | Свидетельства/Свидетельство №2 (Модель)/LinearSystem.py | Local: L28.txt | Domain-specific four-state LinearSystem.py, not a general-purpose linearization library. Uniform-grid branch loses mass memory. |
| L29 | Свидетельства/Свидетельство №2 (Модель)/Listing (1).pdf | Local: L29.txt | PDF listing corresponding to L28. |
| L30 | Свидетельства/Свидетельство №2 (Модель)/~$рма РП_Доп_лицевая сторона.doc | Excluded: lock file | 162-byte Office owner/lock file; inventoried but excluded from scientific content. |
| L31 | Свидетельства/Свидетельство №2 (Модель)/Реферат.pdf | Local: L31.txt | Registration abstract for the model-construction program. |

## Relationships and recovery limits

L06/L07 are editable/PDF report companions. L08 is an adaptive-control draft; L11/L12 belong to an optimal open-loop draft family. L04, L09, and L10 are related minimax studies with materially different experiments and criteria; do not merge them into one canonical result. L13 is a published adaptive minimax study.

SHA-256 equality confirms three duplicate pairs: L16=L22, L17=L23, and L18=L24. Folder names cannot establish minimax adaptive functionality. Remaining apparent draft relationships are semantic, not hash equality.

All 30 content-bearing artifacts have text extractions. PDF text/OCR can distort signs, subscripts, ordering, and numerical decimals. Legacy DOC extraction recovers the Word piece table but omits embedded Equation Editor objects and figures. DOCX paragraph extraction also misses some equation images. The PDF versions and published counterparts should anchor formula transcription.

No Pascal implementation, MATLAB project, full original environment, numerical input bundle, or standalone OpenLoopControl.py was present. Registration folders contain abstracts/listings, not verified scans of all issued certificates. Exact program versions and rights for public redistribution need owner clarification before a future GitHub release.

## Initial module decomposition from the archive

| Historical material | Reusable responsibility | Domain-specific portion |
|---|---|---|
| L07, L28 | Model construction and discretization | Flight/fuel equations, units, nominal trajectories |
| L01–L05, L25–L27 | Set operations and reachable sets | Example dimensions and inputs |
| L02, L11, L14–L15 | Nominal terminal optimization and trajectory recovery | Fuel objective and constraints |
| L04, L09–L10, L19–L21 | Fixed-plan worst-case reachability and finite-action minimax search | Actuator catalogue, tank limits |
| L08, L13, L16–L18 | State-feedback orchestration over shrinking horizon | Nonlinear plant integration and fuel measurements |
| Article experiment sections | Benchmarks and comparison metrics | Published physical scenarios |
| L22–L24 | Duplicate provenance record | Missing distinct minimax adaptive implementation |

Scientific interpretation is in [foundations](scientific-foundations.md); implementation findings are in [audit](legacy-audit.md).

## Supplementary proof sources

The [selected-archive register](archive-selected-sources.json) supplements this unchanged 31-entry inventory. A43–A45 are the permanent IDs for audit-local RP01–RP03, respectively; A39–A42 retain their B04 identities. The [reachability](reachability-proof-audit.md) and [adaptive-policy](adaptive-policy-proof-audit.md) reports cite source-specific anchors, with original-byte and authored-version identities in [proof provenance](proof-audit-provenance.json). Sources remain local-only.
