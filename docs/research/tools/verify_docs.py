"""Verify research documentation and archived-source preservation."""
import ast
import hashlib
import json
import math
import re
from pathlib import Path

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
    "errors":errors,"skipped":skipped,
    "limits":["External links were researched using browsing, not exhaustively HTTP-tested by this script.",
              "Markdown math/Mermaid rendering and all paper proofs are not automatically verified.",
              "Full historical workflows and nonlinear simulations are not reproduced."]
}
(root/"docs/research/verification.json").write_text(
    json.dumps(result,indent=2)+"\n",encoding="utf-8")
print(json.dumps(result,indent=2))
raise SystemExit(bool(errors))
