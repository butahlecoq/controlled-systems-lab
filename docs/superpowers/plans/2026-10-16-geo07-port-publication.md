# GEO-07 Registered Port Publication Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** Publish the independently audited `geo07-port-4dee19cde3d50259` saved adapter report as an English, versioned offline and Pages artifact without rerunning native code.

**Architecture:** A GEO-07 port renderer validates pinned native bytes and emits deterministic page, CSV, SVG, manifest and source ZIP. A separate extension stager binds the resulting bytes and LF-normalized publisher modules to a public route, then adds it to the existing staged site. The original 13 native files remain exact byte copies.

**Tech Stack:** Python standard library, repository report site/registered-report adapters, unittest, SVG/HTML, GitHub Pages workflow.

**Spec:** `docs/architecture/published-algorithm-results.md`; accepted collection audit at PR #345 comments 6218156180 and 6218170092.

## Global Constraints

- Source `41b4b58f2ef982e75554519862afdd803e30f717`, harness `95ba77d3fb2077ec3f56c8fe68903eb18f26488a`, saved report ID `geo07-port-4dee19cde3d50259`.
- Native `trials.jsonl` SHA-256 `41649b7f4acde2c0e980b7c648358d9d217f68e3e5ec9c103f25173e7ab0d39e`; `records.json` SHA-256 `e197ee1852fdb49b3b9180e0a7bfee3004cbb5bb000cf3f175f5ba22b61a5cb1`; native `manifest.json` SHA-256 `27b162d9d9ac271c7eea3145a4cb75972e13f11771ff700341c8603cf9ce63a2`.
- Separately captured post-host observation SHA-256 `dff519dc043fe14cd451f919315a9eee34f00a919e979fba46be809a71548c8a`.
- One excluded warmup and seven measured alternating batches per fixture, 5,000 fresh checked calls per batch, minimum admitted batch 20 ms.
- `collection-001` is excluded, nonpublishable duration-only evidence; preserve it outside the report and mention raw SHA-256 `7f31a8988d36fde6846b4fbb463b797ced9f4b93796bf06e3e9db5843a7d433e`.
- Performance is exploratory and inconclusive: no comparator, mapped limiter, speedup, application-scale result or validated rounding enclosure.

## Review Focus

- Native byte drift must fail before rendering; test raw, record, manifest and post-host mutation.
- A plausible but wrong table or graphic must fail saved regeneration; test deterministic renderer output.
- Extracted source and public ZIP root/nested links must resolve; test every local href.
- A publisher change beyond LF/CRLF normalization must alter the public ID; test each actual byte-generating module.
- Staging must preserve existing routes and reject altered catalogue/ZIP bytes; test in temporary site directories.

### Task 1: Native fixture and renderer

**Files:** `reports/algorithm-results/geo07-port-4dee19cde3d50259/*` (13 copied native files, post-host note, generated assets), `scripts/reports/geo07_port/render_saved.py`, `tests/reporting/test_geo07_port_publication.py`.

**Interfaces:** `validate_native(bundle: Path) -> dict`, `generated(record: dict) -> dict[str, bytes]`, `render(bundle: Path, *, check: bool) -> None`.

- [ ] Copy the 13 accepted native files and post-host note; verify exact source hashes before editing.
- [ ] Write failing tests for byte pins, tampering, literal outcomes/timings, regeneration and source ZIP links.
- [ ] Implement native validator and deterministic HTML/SVG/CSV/source ZIP renderer.
- [ ] Run focused tests red then green and renderer `--check`; inspect page visually.

### Task 2: Content-bound publication route

**Files:** `scripts/reports/stage_geo07_port.py`, `reports/algorithm-results/geo07-port-publications.json`, `.github/workflows/algorithm-reports.yml`, `tests/reporting/test_geo07_port_publication.py`.

**Interfaces:** `validate(bundle: Path) -> PublicationRecord`, `catalogue_entry(bundle: Path) -> dict`, `stage(catalogue: Path, site: Path) -> str`.

- [ ] Write failing tests for public ID publisher hashes, catalogue drift, existing routes and both extracted public ZIP pages.
- [ ] Implement extension stager without changing `registered_reports.py` or existing routes.
- [ ] Generate catalogue from validated source bytes and add additive Pages workflow call.
- [ ] Stage to a temporary site, check exact public ZIP and links, run focused and complete reporting tests.

### Task 3: Review handoff

**Files:** `reports/algorithm-results/tooling/geo07_port/README.md`, PR #345 body, draft publication PR body.

- [ ] Document saved-only regeneration, input hashes, measured scope and rejected attempt.
- [ ] Update #345 metadata to describe accepted collection and pending publication gate.
- [ ] Commit/push draft stacked PR with exact tests, hashes and visual QA evidence; request independent report review.
- [ ] After main includes EXT-04 #346, integrate current main and resolve only additive workflow conflict; rerun full suite and both routes before merge review.
