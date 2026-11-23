# ADR 0013: Keep private research materials out of public releases

Date: 2026-11-22. Status: accepted.

## Context

The working tree may contain owner-held paper scans, local source archives and
raw extraction output under `/papers/`, `/Свидетельства/` and
`/docs/research/extracted/`. These are not public project inputs. Public
scientific reports may retain reviewed citations, derived results and
provenance without publishing the underlying private originals.

## Decision

Do not include those local originals or raw extraction files in public source
or release artifacts unless the owner explicitly clears the specific material
for publication. Curated research notes and result evidence may be published
under their own review and provenance requirements; they do not grant release
rights to their source archives.

The root `.gitignore` patterns are a contributor convenience, not a release
boundary: ignored files can still be force-added or included by another
packaging path. Release staging must inspect the actual archive for local paths
and private research material, as required by the delivery guidance.

## Consequences

Release and publication reviews preserve source provenance while keeping
private originals local. Changes to ignore patterns do not alter publication
permission. A release check must verify the assembled artifact, rather than
infer its contents from `.gitignore` alone.
