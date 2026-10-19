"""Render the issue #4 candidate certificate from its saved integer endpoints."""

from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "research"))
import issue4_volterra_enclosure as checker  # noqa: E402

SOURCE_COMMIT = "9286b5ffa9313650ceea0fc033c1410395db22fe"
FILES = ("records.json", "bounds.csv", "error-box.svg", "index.html", "manifest.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csv_bytes(record: dict) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("stage", "quantity", "x1_lower", "x1_upper", "x2_lower", "x2_upper"))
    for row in record["rows"]:
        for name in ("reference", "linear", "nonlinear", "same_control_error"):
            writer.writerow((row["stage"], name, *row[name][0], *row[name][1]))
    return output.getvalue().encode("utf-8")


def svg_bytes(record: dict) -> bytes:
    # Visual coordinates use binary64 only for drawing. The certificate is the
    # exact decimal endpoint data in records.json and bounds.csv.
    width, height = 760, 470
    left, top, span_x, span_y = 75, 35, 610, 365
    extent_x, extent_y = 12.5, 9.0

    def point(x: float, y: float) -> tuple[float, float]:
        return (left + (x + extent_x) * span_x / (2 * extent_x),
                top + (extent_y - y) * span_y / (2 * extent_y))

    origin_x, origin_y = point(0, 0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Candidate same-control error boxes at stages 1, 20, 40 and 60">',
        '<title>Validated coordinate error boxes</title>',
        '<desc>Outward interval boxes for nonlinear minus linear state. The stage 60 box is coarse and covers every admitted control history of the candidate recurrence.</desc>',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#111827"/>',
        f'<rect x="{left}" y="{top}" width="{span_x}" height="{span_y}" fill="none" stroke="#64748b"/>',
        f'<line x1="{left}" y1="{origin_y:.2f}" x2="{left+span_x}" y2="{origin_y:.2f}" stroke="#94a3b8"/>',
        f'<line x1="{origin_x:.2f}" y1="{top}" x2="{origin_x:.2f}" y2="{top+span_y}" stroke="#94a3b8"/>',
    ]
    colors = {60: "#fb7185", 40: "#fbbf24", 20: "#38bdf8", 1: "#a78bfa"}
    for stage in (60, 40, 20, 1):
        row = record["rows"][stage - 1]
        x_bounds, y_bounds = row["same_control_error"]
        x0, y0 = point(float(x_bounds[0]), float(y_bounds[1]))
        x1, y1 = point(float(x_bounds[1]), float(y_bounds[0]))
        parts.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1-x0:.2f}" height="{y1-y0:.2f}" fill="none" stroke="{colors[stage]}" stroke-width="{3 if stage == 60 else 2}"/>')
    parts.extend([
        f'<circle cx="{origin_x:.2f}" cy="{origin_y:.2f}" r="4" fill="#f8fafc"/>',
        f'<text x="{origin_x+8:.2f}" y="{origin_y-8:.2f}" fill="#f8fafc" font-size="14">0</text>',
        f'<text x="{left+span_x-5}" y="{origin_y+20:.2f}" text-anchor="end" fill="#e2e8f0" font-size="14">error x1</text>',
        f'<text x="{origin_x+9:.2f}" y="{top+18}" fill="#e2e8f0" font-size="14">error x2</text>',
    ])
    for index, stage in enumerate((1, 20, 40, 60)):
        x = 80 + 150 * index
        parts.append(f'<line x1="{x}" y1="438" x2="{x+24}" y2="438" stroke="{colors[stage]}" stroke-width="3"/>')
        parts.append(f'<text x="{x+31}" y="443" fill="#e2e8f0" font-size="14">stage {stage}</text>')
    parts.append('</svg>')
    return ("\n".join(parts) + "\n").encode("utf-8")


def html_bytes(record: dict, report_id: str) -> bytes:
    terminal = record["rows"][-1]["same_control_error"]
    selected = (1, 10, 20, 30, 40, 50, 60)
    rows = "".join(
        f'<tr><th scope="row">{stage}</th><td>[{escape(record["rows"][stage-1]["same_control_error"][0][0])}, {escape(record["rows"][stage-1]["same_control_error"][0][1])}]</td>'
        f'<td>[{escape(record["rows"][stage-1]["same_control_error"][1][0])}, {escape(record["rows"][stage-1]["same_control_error"][1][1])}]</td></tr>'
        for stage in selected
    )
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Candidate Volterra model-error enclosure</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;background:#0b1220;color:#e2e8f0;max-width:1000px;margin:auto;padding:2rem}}a{{color:#7dd3fc}}h1,h2{{color:#f8fafc}}.lead{{font-size:1.2rem}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:1.3rem;margin:1.3rem 0}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #334155;padding:.5rem;text-align:left}}img{{max-width:100%;height:auto}}code{{overflow-wrap:anywhere}}</style></head><body>
<h1>Candidate Volterra model-error enclosure</h1>
<p class="lead">For every 60-stage control history with each value in [-0.3, 0.3], the candidate nonlinear and linear recurrences starting at (1, 2) have the same-control terminal error inside <strong>[{terminal[0][0]}, {terminal[0][1]}] × [{terminal[1][0]}, {terminal[1][1]}]</strong>.</p>
<p>The resulting two-sided reachable-set Hausdorff distance in the infinity norm is at most <strong>{record["error_linf_upper"]}</strong>, for the control-only candidate systems. This coarse enclosure does not establish either set's inclusion in the other.</p>
<div class="card"><h2>Assumptions and proof method</h2><p>State dimension 2; 60 discrete stages; independent scalar controls in [-0.3, 0.3]; zero-control reference starts at (410, 300). Both compared recurrences start at (1, 2), and each matrix uses the next reference sample. The step size is pi/(18 sqrt(2)), enclosed by [{record["step_size"][0]}, {record["step_size"][1]}]. Integer intervals at scale 10^-15 round every product outward. Pi is bounded by the alternating Machin series; sqrt(2) by integer square roots. The quadratic correction uses the nonlinear state box. Identical control terms cancel in the error recurrence.</p><p>For each admissible history, induction places both states and their difference inside the saved stage boxes. Pairing each history with itself proves the stated two-sided distance bound when no additional state constraints or pruning are imposed.</p></div>
<div class="card"><figure><img src="error-box.svg" alt="Validated coordinate error boxes for stages 1, 20, 40 and 60"><figcaption>Coordinate-wise error boxes. The drawing is illustrative; exact decimal endpoints are in the raw record and CSV.</figcaption></figure></div>
<h2>Selected stage bounds for nonlinear minus linear state</h2><table><thead><tr><th scope="col">Stage</th><th scope="col">First coordinate</th><th scope="col">Second coordinate</th></tr></thead><tbody>{rows}</tbody></table>
<div class="card"><h2>Evidence boundary</h2><p>This is a new calculation for the hash-identified private companion candidate, SHA-256 <code>{record["candidate_source_sha256"]}</code>. Its source transcript and limitations are in the repository source-check note. The inspected L05 publication prints different nonlinear and linear initial states and does not supply their coordinate map. The candidate uses different reference indexing from the printed matrix. This result does not reproduce Figure 1 or Table 1, identify their driver, certify either historical construction, or bound the physical (410, 300) trajectory. No historical runtime or performance comparison is inferred.</p><p>Frozen checker source commit: <code>{SOURCE_COMMIT}</code>. Report ID: <code>{report_id}</code>. Arithmetic is exact integer/rational apart from the illustrative SVG coordinates. No runtime measurements are claimed.</p></div>
<p><a href="records.json">Full raw JSON</a> · <a href="bounds.csv">All stage bounds CSV</a> · <a href="error-box.svg">SVG</a> · <a href="{report_id}.zip">Offline ZIP</a></p>
</body></html>'''
    return page.encode("utf-8")


def render(record_bytes: bytes, renderer_bytes: bytes) -> tuple[str, dict[str, bytes]]:
    record = json.loads(record_bytes)
    if record != checker.run() or record.get("schema") != "issue4-volterra-enclosure-v1":
        raise ValueError("saved certificate differs from frozen recurrence")
    report_id = "issue4-volterra-" + sha(record_bytes + renderer_bytes + SOURCE_COMMIT.encode())[:16]
    files = {
        "records.json": record_bytes,
        "bounds.csv": csv_bytes(record),
        "error-box.svg": svg_bytes(record),
        "index.html": html_bytes(record, report_id),
    }
    manifest = {
        "schema": "issue4-volterra-report-v1",
        "report_id": report_id,
        "source_commit": SOURCE_COMMIT,
        "renderer_sha256": sha(renderer_bytes),
        "files_sha256": {name: sha(data) for name, data in sorted(files.items())},
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    archive = io.BytesIO()
    # Stored members and fixed ZIP metadata make the archive byte-identical
    # across Python/zlib versions and Windows/Linux hosts.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
        for name in FILES:
            info = zipfile.ZipInfo(report_id + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            output.writestr(info, files[name])
    files[report_id + ".zip"] = archive.getvalue()
    return report_id, files


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report_id, files = render(args.record.read_bytes(), Path(__file__).read_bytes())
    destination = args.out_root / report_id
    if args.check:
        if {p.name for p in destination.iterdir()} != set(files):
            raise SystemExit("saved bundle inventory mismatch")
        for name, data in files.items():
            if (destination / name).read_bytes() != data:
                raise SystemExit(f"saved bundle differs: {name}")
    else:
        destination.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            (destination / name).write_bytes(data)
    print(report_id)


if __name__ == "__main__":
    main()
