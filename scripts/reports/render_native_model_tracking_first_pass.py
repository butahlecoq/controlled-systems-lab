#!/usr/bin/env python3
"""Render labelled full-state-checked 2D projections for the native 1012 first pass."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import pathlib
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = pathlib.Path(__file__).resolve().parents[2]
PALETTE = {
    "page": "#272822", "surface": "#303129", "text": "#f8f8f2", "muted": "#b7b7af",
    "accent": "#a6e22e", "link": "#66d9ef", "warm": "#fd971f", "line": "#504945",
}


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def draw(path: pathlib.Path, points: list[tuple[int, float, float]], x_label: str,
         y_label: str, title: str, subtitle: str) -> None:
    fig, ax = plt.subplots(figsize=(8.6, 5.4), constrained_layout=True)
    fig.patch.set_facecolor(PALETTE["page"])
    ax.set_facecolor(PALETTE["surface"])
    xs, ys = [point[1] for point in points], [point[2] for point in points]
    ax.plot(xs, ys, color=PALETTE["accent"], linewidth=2.0, zorder=2)
    ax.scatter(xs, ys, color=PALETTE["link"], edgecolors=PALETTE["page"], linewidths=1.0,
               s=48, zorder=3, label="observed state")
    ax.scatter([xs[0]], [ys[0]], color=PALETTE["warm"], edgecolors=PALETTE["page"],
               s=72, zorder=4, label="initial state")
    ax.scatter([xs[-1]], [ys[-1]], color="#f92672", edgecolors=PALETTE["page"],
               s=72, zorder=4, label="final observed state")
    stride = max(1, (len(points) - 1) // 5)
    offsets = [(7, 7), (7, -13), (-25, 7), (-25, -13)]
    for index, (step, x, y) in enumerate(points):
        if step not in {0, len(points) - 1} and step % stride:
            continue
        offset = offsets[index % len(offsets)] if len(points) > 8 else (6, 6)
        ax.annotate(f"t={step}", (x, y), xytext=offset, textcoords="offset points",
                    color=PALETTE["text"], fontsize=8)
    ax.set_xlabel(x_label, color=PALETTE["text"], labelpad=10)
    ax.set_ylabel(y_label, color=PALETTE["text"], labelpad=10)
    ax.set_title(title + "\n" + subtitle, color=PALETTE["text"], loc="left", pad=14, fontsize=12)
    ax.tick_params(colors=PALETTE["muted"])
    for spine in ax.spines.values():
        spine.set_color(PALETTE["line"])
    ax.grid(True, color=PALETTE["line"], linewidth=0.65, alpha=0.8)
    legend = ax.legend(loc="best", facecolor=PALETTE["surface"], edgecolor=PALETTE["line"],
                       labelcolor=PALETTE["text"], fontsize=8)
    legend.get_frame().set_alpha(0.95)
    fig.savefig(path, format="svg", facecolor=fig.get_facecolor())
    fig.savefig(path.with_suffix(".png"), dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=pathlib.Path, required=True)
    parser.add_argument("--catalogue", type=pathlib.Path, required=True)
    parser.add_argument("--checks", type=pathlib.Path, required=True)
    args = parser.parse_args()
    capture, catalogue, checks = args.capture.resolve(), args.catalogue.resolve(), args.checks.resolve()
    capture_manifest = json.loads((capture / "manifest.json").read_text(encoding="utf-8"))
    catalogue_manifest = json.loads((catalogue / "manifest.json").read_text(encoding="utf-8"))
    checked = json.loads((checks / "checks.json").read_text(encoding="utf-8"))
    if checked["capture_manifest_sha256"] != sha256(capture / "manifest.json"):
        raise SystemExit("The independent check report does not bind this first-pass capture")
    if checked["counts"]["independent_check_passed"] != 32 or checked["counts"]["checker_errors"]:
        raise SystemExit("Only a clean 32-case independent check report can be projected")
    model_rows = read_csv(catalogue / "catalogue-data/native-output/catalogue.csv")
    coordinate_rows = read_csv(catalogue / "catalogue-data/native-output/coordinates.csv")
    coordinate_map: dict[str, dict[str, dict[int, tuple[str, str]]]] = {}
    for row in coordinate_rows:
        coordinate_map.setdefault(row["model"], {}).setdefault(row["kind"], {})[
            int(row["index"])
        ] = (row["name"], row["unit"])
    metadata = {row["model"]: row for row in model_rows}
    trajectory_rows = read_csv(checks / "full_state_trajectory_checked.csv")
    trajectory: dict[str, list[tuple[int, list[float]]]] = {}
    for row in trajectory_rows:
        trajectory.setdefault(row["model"], []).append(
            (int(row["executed_step"]), [float(value) for value in json.loads(row["coordinates"])])
        )
    for values in trajectory.values():
        values.sort(key=lambda value: value[0])

    report_parent = capture.parent
    base_name = "visual-example-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = report_parent / base_name
    suffix = 0
    while destination.exists():
        suffix += 1
        destination = report_parent / f"{base_name}-{suffix:02d}"
    (destination / "figures").mkdir(parents=True)
    css_source = ROOT / "reports/algorithm-results/native-discrete-models-v1/offline-examples.css"
    (destination / "offline-examples.css").write_bytes(css_source.read_bytes())

    profiles = {item["model"]: item["status"] for item in capture_manifest["outcomes"]}
    figures: list[dict[str, str]] = []
    eligible = []
    for ident, dimensions in coordinate_map.items():
        if profiles.get(ident) != "completed" or checked["checks"].get(ident, {}).get("status") != "passed":
            continue
        if ident == "catalogue-2026/model-21/1":
            coordinates = (2, 8)
            title = "model-21/1 · OSQP quadcopter"
            subtitle = f"12-state · literal source MPC · 15 replans · Δt={metadata[ident]['time_step']} {metadata[ident]['time_unit']}"
        elif len(dimensions.get("state", {})) == 2:
            coordinates = (0, 1)
            short_id = ident.split("/")[1]
            title = f"{short_id} · {metadata[ident]['title']}"
            subtitle = f"2-state · authored target=0 · N=3, replans=3 · Δt={metadata[ident]['time_step']} {metadata[ident]['time_unit']}"
        else:
            continue
        if ident not in trajectory:
            raise SystemExit(f"Missing independently checked observed trajectory for {ident}")
        x_index, y_index = coordinates
        x_name, x_unit = dimensions["state"][x_index]
        y_name, y_unit = dimensions["state"][y_index]
        points = [(stage, state[x_index], state[y_index]) for stage, state in trajectory[ident]]
        if len(points) < 2:
            raise SystemExit(f"Insufficient executed stages for {ident}")
        basename = f"model-{int(ident.split('/')[1].split('-')[1]):02d}-state-{x_index + 1}-{y_index + 1}.svg"
        draw(destination / "figures" / basename, points, f"{x_name} [{x_unit}]", f"{y_name} [{y_unit}]",
             title, subtitle)
        source = metadata[ident]
        profile = "source21 literal source task" if ident.endswith("model-21/1") else "authored nominal tracking profile"
        eligible.append((ident, basename, points, x_name, x_unit, y_name, y_unit, source, profile))
        png_name = pathlib.Path(basename).with_suffix(".png").name
        figures.append({"model": ident, "file": f"figures/{basename}",
                        "sha256": sha256(destination / "figures" / basename),
                        "preview_png": f"figures/{png_name}",
                        "preview_png_sha256": sha256(destination / "figures" / png_name)})

    source_csv = checks / "full_state_trajectory_checked.csv"
    index = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Native model tracking: checked first pass</title><link rel='stylesheet' href='offline-examples.css'></head><body>",
        "<main class='page-content'><p class='eyebrow'>Controlled Systems Lab · #1012 · functional first pass</p>",
        "<h1>Native model tracking, with every state retained</h1>",
        "<p>This report shows executed closed-loop observations after the full-state QP and plant-step records passed independent dynamics and objective checks. Each panel belongs to one model and task; panels are not performance comparisons.</p>",
        "<p class='note'><strong>Scope:</strong> all 35 catalogue records were attempted. Thirty-two completed and passed independent checks; three were refused by HiGHS because their unchanged source matrices contain nonzero values at or below the adapter's 1e-12 removal threshold. Failures remain in the raw capture. The run is numerical and nominal; it is not calibration evidence, a robust guarantee or a nonlinear stability claim.</p>",
        f"<p>Checked full-state dynamics transitions: <strong>{checked['counts']['full_state_dynamics_transitions_checked']}</strong>. The saved trajectories contain all state coordinates before projection. <a href='../{checks.name}/full_state_trajectory_checked.csv'>Download checked full-state observed trajectories</a> · <a href='../{checks.name}/independent_results.csv'>Per-model objectives and replay costs</a> · <a href='../{checks.name}/checks.json'>Independent checks</a> · <a href='../{capture.name}/manifest.json'>Immutable capture manifest</a> · <a href='../{catalogue.name}/catalogue-data/native-output/catalogue.csv'>Model source catalogue</a>.</p>",
        "<p class='note'>Objective and realized-cost values belong to their separately authored task profiles. Their scales differ across models and they are not a cross-model ranking.</p>",
        "<section><h2>Executed trajectories</h2><p>Each curve joins observed state samples at indexed steps. Labels show sample order. The display projects only after checking all state coordinates and every applied transition against the original model matrices.</p>",
    ]
    for ident, basename, points, x_name, x_unit, y_name, y_unit, source, profile in eligible:
        title = f"{ident} · {source['title']}"
        index += [
            "<figure>",
            f"<img src='figures/{basename}' alt='{html.escape(title)} observed state trajectory projected onto {html.escape(x_name)} and {html.escape(y_name)}'>",
            f"<figcaption><strong>{html.escape(title)}</strong><br>{html.escape(profile)} · observed samples={len(points)} · state axes: {html.escape(x_name)} [{html.escape(x_unit)}], {html.escape(y_name)} [{html.escape(y_unit)}]<br>Source: {html.escape(source['source_title'])}; SHA-256 {html.escape(source['source_sha256'])}<details><summary>Source qualification and locator</summary><p>{html.escape(source['source_qualification'])}</p><p>{html.escape(source['source_locator'])}</p></details></figcaption></figure>",
        ]
    index += [
        "</section><section><h2>Task definitions</h2>",
        "<p><strong>Source21:</strong> literal OSQP MPC example, horizon 10, running and terminal state costs, control costs and printed bounds; 15 observed-state replans; original source task adapter and independent literal cost evaluator.</p>",
        "<p><strong>Other completed cases:</strong> separately authored nominal task to zero; fixed three-stage horizon repeated at three observed-state replans; state weights 1/max(1,|x0_i|)^2, terminal weight five times state weight, R=0.02I, recorded-coordinate actuator bounds [-1,1], and no state bounds. A supplied nominal external vector is folded with E into the affine term; absent one, fixed external zero is declared and source E is retained in catalogue data.</p>",
        "<p>Original model labels, source hashes, coordinate names and units are in the saved catalogue records. Controllability/rank caveats and source assumptions remain attached to the source qualification text for each model.</p></section>",
        "<section><h2>Reproduce</h2><pre><code>cmake -S examples -B build -DCSL_DIR=$CSL_PREFIX/lib/cmake/CSL -DCMAKE_BUILD_TYPE=Release\ncmake --build build --parallel 1 --target native_model_tracking native_discrete_models quadcopter_mpc\npython scripts/reports/native_model_tracking_first_pass.py --build build\npython scripts/reports/verify_native_model_tracking_first_pass.py &lt;capture&gt; --retry &lt;capability-retry&gt;\npython scripts/reports/render_native_model_tracking_first_pass.py --capture &lt;capture&gt; --catalogue &lt;catalogue-metadata-capture&gt; --checks &lt;independent-checks&gt;</code></pre>",
        "<p>Set <code>CSL_PREFIX</code> to a clean installed build exposing the three targets. The saved executable SHA-256 and the running-history library archive hash are in each capture manifest. The component archive is identified separately; no whole-SDK qualification is claimed here.</p></section>",
        "</main></body></html>",
    ]
    (destination / "index.html").write_text("\n".join(index) + "\n", encoding="utf-8")
    receipt = {
        "schema": "csl.1012-native-model-tracking-visual-example/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "renderer_source_sha256": sha256(pathlib.Path(__file__).resolve()),
        "capture": str(capture), "capture_manifest_sha256": sha256(capture / "manifest.json"),
        "catalogue_capture": str(catalogue), "catalogue_manifest_sha256": sha256(catalogue / "manifest.json"),
        "independent_checks": str(checks), "checks_sha256": sha256(checks / "checks.json"),
        "per_model_results_sha256": sha256(checks / "independent_results.csv"),
        "css_sha256": sha256(destination / "offline-examples.css"),
        "figures": figures,
        "panel_count": len(figures),
        "source21_projection": "indexed state coordinates x3 and x9 from the fully checked 12-state trajectory",
        "2d_model_count": len(figures) - 1,
        "cross_model_performance_comparison": False,
    }
    (destination / "manifest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"visual_example": str(destination), "panel_count": len(figures)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
