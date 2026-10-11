# Scientific review and contributions

This repository starts as a research dossier. The owner selected C++ as the main implementation language, with C++20 as the working standard and Python allowed for independent verification. The product interface is still being designed. Read [the research index](docs/research/README.md), [foundations](docs/research/scientific-foundations.md) and [architecture hypothesis](docs/architecture/initial-architecture.md) first.

Use issues for scientific corrections, reproduction reports and algorithm proposals. Cite an Lxx source identifier or a primary external reference, the formula/page, exact assumptions and a minimal example where possible. Distinguish a proven discrepancy, an interpretation question, a numerical observation and an implementation defect.

A useful reproduction report identifies the problem manifest, source version, coordinate/time convention, objective, control domain, uncertainty dependence, policy class, software/hardware versions, solver settings, residuals and result evidence. Compare like-for-like output and guarantees.

For a new algorithm, state supported assumptions, returned guarantees, complexity/representation costs, and an evaluation plan against the published baselines. A faster sampled approximation should not be described as the same result as an exact worst-case solve without qualification.

Keep historical reported numbers unchanged. Record corrected references separately with an issue explaining the change. Do not silently “repair” an article or attribute an extracted PDF formatting issue to executable source.

New curated documentation and future software should be in English. Preserve original-language quotations only when necessary for provenance and with a translation.

Original papers, listings, raw extractions and personal source metadata remain local. Source IDs and hashes are public; reviewers can cite the published counterparts and request a precise transcription through an issue. Public availability of the repository does not establish a redistribution license for archival materials. Project licensing remains an owner decision.

Changes to mathematical contracts or guarantee labels require a clear rationale and appropriate independent checks. The owner selected nominal planning with an optimal solution-family output. Product implementation follows the agreed architecture. New algorithms should integrate through the [modular ports](docs/architecture/modular-algorithms-and-solution-sets.md), with output completeness and set-conversion/approximation evidence recorded.

Implementation work follows the [dependency-ordered backlog](docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md). Claim an unblocked ticket and proposed file ownership before parallel edits. Each module implementation ships minimum independent tests; separate test expansions and rigorous review issues provide additional gates. Use the [skill routing policy](docs/agents/skill-routing.md) to avoid competing workflows.

Every algorithm that produces numerical results also delivers a versioned standalone HTML report and raw records under the [published-results policy](docs/architecture/published-algorithm-results.md). Follow the [report commands and record contract](docs/contracts/algorithm-report-records.md): review the fixed code/harness, measure its clean Release executable, review saved results/figures, then publish and verify the accessible versioned URL. Functional CTest/smoke runs are not benchmark measurements. Link the actual report URL and measured source commit in the relevant PR and issue; preserve failures, unavailable metrics and the declared evidence scope.
