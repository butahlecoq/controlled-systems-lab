"""Verify research documentation and archived-source preservation."""
import ast
import hashlib
import json
import math
import re
from pathlib import Path

from check_proof_counterexamples import check_counterexamples
from check_temporal_lift import check_temporal_lift


def verify_proof_provenance(provenance, registered, research_dir):
    """Validate public source references and authored-version disposition chains.

    Private review artifacts are not required or reopened. Their digests identify
    antecedents; this validates the recorded relationships, not those private bytes.
    """
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def digest(value):
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
                "Invalid SHA-256 identity")

    require(provenance["schema_version"] == 2, "Unsupported schema version")
    require(provenance.get("public_report_digest_convention") == "utf8-lf",
            "Public report digest convention must be utf8-lf")
    report_hashes = provenance.get("public_report_sha256")
    require(isinstance(report_hashes, dict)
            and set(report_hashes) == {a["id"] for a in provenance["audits"]},
            "Public report hash coverage differs")
    sources = provenance["sources"]
    source_ids = [source["id"] for source in sources]
    require(len(source_ids) == len(set(source_ids)), "Duplicate source ID")
    anchors = {}
    for source in sources:
        sid = source["id"]
        require(sid in registered, "Unregistered source " + sid)
        require(source["original_sha256"] == registered[sid]["sha256"],
                "Registered source hash differs: " + sid)
        expected_register = ("docs/research/inventory.json" if sid.startswith("L")
                             else "docs/research/archive-selected-sources.json")
        require(source["register"] == expected_register, "Wrong source register: " + sid)
        digest(source["original_sha256"])
        if "navigation_extract_sha256" in source:
            digest(source["navigation_extract_sha256"])
        require(source["anchors"], "Missing source anchors: " + sid)
        for anchor in source["anchors"]:
            aid = anchor["id"]
            require(aid.startswith(sid + "-") and aid not in anchors, "Invalid/duplicate anchor " + aid)
            require(bool(anchor["description"]), "Empty source anchor description")
            if anchor["kind"] == "ooxml_section_paragraph":
                require(registered[sid]["path"].endswith(".docx") and bool(anchor["section"]),
                        "Invalid OOXML anchor: " + aid)
            else:
                require(anchor["kind"] in ("pdf_pages", "original_lines"), "Unknown anchor kind")
                require(type(anchor["start"]) is int and type(anchor["end"]) is int
                        and 1 <= anchor["start"] <= anchor["end"], "Invalid anchor range: " + aid)
                if anchor["kind"] == "pdf_pages":
                    require(registered[sid]["path"].endswith(".pdf"), "PDF anchor for non-PDF")
                    if "pages" in registered[sid]:
                        require(anchor["end"] <= registered[sid]["pages"], "PDF anchor out of range")
                else:
                    require(Path(registered[sid]["path"]).suffix in (".m", ".py", ".pas"),
                            "Code anchor for non-code")
            anchors[aid] = sid
    aliases = {source["antecedent_alias"]: source["id"] for source in sources
               if "antecedent_alias" in source}
    require(aliases == provenance["alias_crosswalk"], "Alias crosswalk mismatch")
    for alias, sid in aliases.items():
        require(registered[sid].get("audit_alias") == alias, "Registered alias differs: " + sid)

    audits = {}
    final_dispositions = {}
    headings = {}
    all_refs = set()
    for audit in provenance["audits"]:
        key = audit["id"]
        require(re.fullmatch(r"[a-z-]+", key) and key not in audits, "Invalid/duplicate audit ID")
        require(audit["public_report"] == "docs/research/" + key + ".md", "Unexpected report path")
        report_bytes = (research_dir / (key + ".md")).read_bytes()
        # Only public authored reports use the declared LF convention. Primary
        # sources and private antecedent/review identities retain their raw bytes.
        report_bytes = report_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest(report_hashes[key])
        require(hashlib.sha256(report_bytes).hexdigest() == report_hashes[key],
                "Public report hash differs: " + key)
        text = report_bytes.decode("utf-8")
        headings[key] = set(re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE))
        require(audit["original_issue_status"] == "open", "Original issue silently closed")
        refs = audit["source_anchor_refs"]
        require(refs and len(refs) == len(set(refs)) and set(refs) <= anchors.keys(),
                "Unknown/duplicate source anchor reference")
        all_refs.update(refs)
        versions = audit["antecedent_versions_sha256"]
        require(versions and len(versions) == len(set(versions)), "Empty/duplicate variant chain")
        for version in versions:
            digest(version)
        require(versions[-1] == audit["final_antecedent_sha256"], "Final antecedent differs from chain")
        current = 0
        states = {}
        events = audit["review_events"]
        require(events and events[0]["kind"] == "independent_review"
                and events[-1]["kind"] == "scoped_recheck", "Missing initial/final review gate")
        for event in events:
            digest(event["artifact_sha256"])
            require(bool(event["scope"]), "Missing review scope")
            target = event["reviewed_version_sha256"]
            kind = event["kind"]
            if kind == "reviewer_withdrawal":
                require(target == versions[0], "Withdrawal must identify the initial reviewed version")
                require(set(event["dispositions"].values()) == {"withdrawn"}, "Invalid withdrawal")
            else:
                require(target == versions[current], "Broken reviewed-version chain")
            require(kind in ("independent_review", "author_fix", "scoped_recheck", "reviewer_withdrawal"),
                    "Unknown review event kind")
            if kind == "author_fix":
                current += 1
                require(current < len(versions) and event["result_version_sha256"] == versions[current],
                        "Broken fix-result version chain")
            else:
                require("result_version_sha256" not in event, "Review cannot create an authored version")
            for finding, disposition in event["dispositions"].items():
                require(disposition in ("changes_requested", "clarification_requested", "addressed", "disputed_on_primary_source", "withdrawn"),
                        "Unknown finding disposition")
                require(states.get(finding) != "withdrawn" or disposition == "withdrawn",
                        "Withdrawn finding resurrected")
                if disposition == "withdrawn":
                    require(kind == "reviewer_withdrawal" or states.get(finding) == "withdrawn",
                            "Withdrawal lacks reviewer disposition")
                states[finding] = disposition
        require(current == len(versions) - 1, "Unvisited authored version")
        require(states and set(states.values()) <= {"addressed", "withdrawn"}, "Unresolved review finding")
        require(not (final_dispositions.keys() & states.keys()), "Finding shared by different audits")
        final_dispositions.update(states)
        audits[key] = audit
    require(all_refs == anchors.keys(), "Unreferenced provenance anchor")

    findings = provenance["findings"]
    require(len(findings) == len(final_dispositions)
            and {f["id"] for f in findings} == final_dispositions.keys(), "Finding coverage differs")
    for finding in findings:
        key = finding["audit"]
        require(key in audits, "Unknown finding audit")
        require(finding["disposition"] == final_dispositions[finding["id"]], "Final finding disposition differs")
        require(finding["source_anchor_refs"] and set(finding["source_anchor_refs"]) <= set(audits[key]["source_anchor_refs"]),
                "Finding source anchor outside audit")
        require(finding["report_section"] in headings[key], "Missing finding report section")
    checks = check_counterexamples() | check_temporal_lift()
    references = provenance["counterexample_checks"]
    require(len(references) == len(checks) and {r["name"] for r in references} == checks.keys(),
            "Counterexample reference coverage differs")
    for reference in references:
        require(reference["audit"] in audits, "Unknown counterexample audit")
        require(reference["report_section"] in headings[reference["audit"]], "Missing counterexample report section")
    return {"sources": len(sources), "anchors": len(anchors), "audits": len(audits),
            "review_events": sum(len(a["review_events"]) for a in audits.values()),
            "findings": len(findings), "literal_checks": len(checks)}


root = Path(__file__).resolve().parents[3]
inventory = json.loads((root/"docs/research/inventory.json").read_text(encoding="utf-8"))
errors, skipped = [], []
originals_checked = 0
for entry in inventory:
    p = root/entry["path"]
    if p.exists():
        originals_checked += 1
        if hashlib.sha256(p.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append("Original hash changed: "+entry["id"])
    else:
        skipped.append("Original unavailable in public checkout: "+entry["id"])
    if p.exists() and entry.get("extracted_text") and not (root/entry["extracted_text"]).exists():
        errors.append("Missing local extraction: "+entry["id"])
if len(inventory) != 31 or sum(r.get("pages",0) for r in inventory) != 226:
    errors.append("Unexpected inventory count/page total")
duplicates = {}
for entry in inventory:
    duplicates.setdefault(entry["sha256"], []).append(entry["id"])
duplicate_groups = [v for v in duplicates.values() if len(v)>1]
if sorted(duplicate_groups) != sorted([["L16","L22"],["L17","L23"],["L18","L24"]]):
    errors.append("Unexpected duplicate groups")

docs = [root/"README.md", root/"CONTRIBUTING.md"]
docs += sorted((root/"docs").rglob("*.md"))
docs += sorted((root/".github/ISSUE_TEMPLATE").glob("*.md"))
local_links = 0
for p in docs:
    content = p.read_text(encoding="utf-8")
    if "\ufffd" in content:
        errors.append("Replacement character: "+p.relative_to(root).as_posix())
    for match in re.finditer(r"\[[^\]]*\]\((<[^>]*>|[^)\n]+)\)", content):
        dest = match.group(1).strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:",dest) or dest.startswith("#"):
            continue
        local_links += 1
        target = dest.split("#",1)[0]
        if not (p.parent/target).exists():
            errors.append("Broken link in "+p.relative_to(root).as_posix()+": "+dest)
scripts = sorted((root/"docs/research/tools").glob("*.py"))
for p in scripts:
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError as exc:
        errors.append("Tool syntax: "+p.name+": "+str(exc))
characterization = json.loads((root/"docs/research/legacy-characterization.json").read_text(encoding="utf-8"))
if len(characterization["checks"]) != 6:
    errors.append("Unexpected legacy characterization coverage")
reference = json.loads((root/"docs/research/reference-b08.json").read_text(encoding="utf-8"))
if reference["plans"] != 625 or reference["disturbance_box_corner_images_per_plan"] != 256:
    errors.append("Unexpected B08 exhaustive count")
if not math.isclose(reference["computed_discrete_minimax"],
                    reference["computed_cost_of_reported_plan"],abs_tol=1e-8):
    errors.append("Published B08 plan does not match computed minimum")
archive_register = json.loads((root/"docs/research/archive-selected-sources.json").read_text(encoding="utf-8"))
archive_checked = 0
for entry in archive_register["selected_sources"]:
    p = Path(archive_register["archive_root"]) / entry["path"]
    if p.exists():
        archive_checked += 1
        if hashlib.sha256(p.read_bytes()).hexdigest() != entry["sha256"]:
            errors.append("Selected archive source hash changed: " + entry["id"])
    else:
        skipped.append("Selected archive source unavailable: " + entry["id"])
b04_case = json.loads((root/"benchmarks/scenarios/b04-historical.json").read_text(encoding="utf-8"))
b04_check = json.loads((root/"docs/research/b04-consistency.json").read_text(encoding="utf-8"))
if b04_case["executable"] or b04_case["problem"]["controls"]["stage_sets"] is not None:
    errors.append("Unresolved historical B04 was silently made executable")
if b04_check["scenario"] != b04_case["id"] or b04_check["historical_reproduction_complete"]:
    errors.append("Unexpected B04 restoration/reproduction status")
if not math.isclose(b04_check["reported_point_recomputed_objective"],
                    float(b04_case["reported"]["objective"]), abs_tol=0.0005):
    errors.append("B04 printed-point objective check changed")
if b04_check["unrestricted_terminal_plane_minimum"]["objective_float"] <= float(b04_case["reported"]["objective"]):
    errors.append("B04 lower-bound discrepancy check changed")
proof_counts = {}
try:
    proof_provenance = json.loads((root/"docs/research/proof-audit-provenance.json").read_text(encoding="utf-8"))
    proof_counts = verify_proof_provenance(
        proof_provenance, {e["id"]: e for e in inventory + archive_register["selected_sources"]},
        root/"docs/research")
except (KeyError, TypeError, ValueError, OSError) as exc:
    errors.append("Proof provenance: " + str(exc))
result = {
    "date":"2026-10-11", "status":"passed" if not errors else "failed",
    "originals_checked":originals_checked, "inventory_entries":len(inventory),
    "pdf_pages":226, "duplicate_groups":duplicate_groups,
    "markdown_documents":len(docs), "local_links_checked":local_links,
    "research_scripts_syntax_checked":len(scripts),
    "legacy_characterization_checks":len(characterization["checks"]),
    "baseline_reference_plans":reference["plans"],
    "b04_consistency_status":b04_check["status"],
    "selected_archive_sources_checked":archive_checked,
    "proof_provenance_checked":proof_counts,
    "errors":errors,"skipped":skipped,
    "limits":["External links were researched using browsing, not exhaustively HTTP-tested by this script.",
              "Markdown math/Mermaid rendering and all paper proofs are not automatically verified.",
              "Full historical workflows and nonlinear simulations are not reproduced."]
}
(root/"docs/research/verification.json").write_text(
    json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
raise SystemExit(bool(errors))
