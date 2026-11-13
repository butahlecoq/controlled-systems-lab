"""Read authenticated A6 results and render a matched, saved-data geometry lesson."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
import zipfile
from pathlib import Path

if __package__:
    from . import native_fixed_tail_episode_report as episodes
else:
    import native_fixed_tail_episode_report as episodes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
ROUTE = "native-fixed-tail-geometry-a6"
PLANES = {
    "syn-nl-lv-01": [[0, 1]],
    "earth-orbit": [[0, 3], [1, 2]],
    "syn-nl-fuel-01": [[2, 0], [3, 1]],
}
COORDINATES = {
    "syn-nl-lv-01": [
        ("Prey population P", "thousand individuals"),
        ("Predator population R", "thousand individuals"),
    ],
    "earth-orbit": [
        ("Radius r", "km"),
        ("Radial velocity v", "km/s"),
        ("Angle θ", "rad"),
        ("Angular rate ω", "rad/s"),
    ],
    "syn-nl-fuel-01": [
        ("Oxidizer mass mₒₓ", "kg"),
        ("Fuel mass m_f", "kg"),
        ("Oxidizer flow qₒₓ", "kg/s"),
        ("Fuel flow q_f", "kg/s"),
    ],
}
IDENTITY = "F carrier intersect B equals B: carrier rows participate in B admission"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def seal(value):
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _finite(values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def _inside_carrier(region, dimension):
    lower, upper, member = region["lower"], region["upper"], region["membership"]
    require(
        len(lower) == len(upper) == dimension
        and _finite(lower + upper)
        and all(a <= b for a, b in zip(lower, upper, strict=True)),
        "invalid full-state carrier",
    )
    tolerance = [1e-8 + 2e-12 * max(abs(a), abs(b), 1) for a, b in zip(lower, upper, strict=True)]
    if "center" in member:
        center, factor = member["center"], member["factor"]
        require(
            len(center) == len(factor) == dimension
            and _finite(center)
            and all(_finite(row) for row in factor)
            and len({len(row) for row in factor}) == 1,
            "invalid full-state membership factor",
        )
        norm = member["factor_domain_norm"]
        require(norm in ("linf", "l2"), "unknown factor domain")
        for i, row in enumerate(factor):
            radius = (
                sum(abs(x) for x in row) if norm == "linf" else math.sqrt(sum(x * x for x in row))
            )
            require(
                center[i] - radius >= lower[i] - tolerance[i]
                and center[i] + radius <= upper[i] + tolerance[i],
                "full-state B escapes carrier",
            )
    else:
        rows, bounds = member["inequalities"], member["upper_bounds"]
        require(
            len(rows) == len(bounds)
            and _finite(bounds)
            and all(len(row) == dimension and _finite(row) for row in rows),
            "invalid full-state H membership",
        )
        # Independently witness both carrier bounds with actual full-state H rows.
        # These are sufficient implications, not a projected-polygon intersection.
        for i in range(dimension):
            axis = [
                (row[i], bound)
                for row, bound in zip(rows, bounds, strict=True)
                if row[i] != 0 and all(v == 0 for j, v in enumerate(row) if j != i)
            ]
            for row, bound in zip(member["equalities"], member["equality_values"], strict=True):
                if row[i] != 0 and all(v == 0 for j, v in enumerate(row) if j != i):
                    axis.extend(((row[i], bound), (-row[i], -bound)))
            require(
                any(a > 0 and b / a <= upper[i] + tolerance[i] for a, b in axis)
                and any(a < 0 and b / a >= lower[i] - tolerance[i] for a, b in axis),
                "H membership does not establish full-state carrier containment",
            )


def validate_run(run, task):
    n, horizon = len(task["coordinates"]), task["horizon"]
    require(
        [r["stage"] for r in run["stages"]] == list(range(horizon + 1)),
        "invalid saved stage association",
    )
    require(len(run["candidate"]) == len(run["execution"]) == horizon + 1, "invalid path horizon")
    require(
        all(len(x) == n and _finite(x) for x in run["candidate"] + run["execution"]),
        "invalid physical path",
    )
    require(run["candidate"][0] == run["execution"][0], "initial observations differ")
    require(
        len(run["candidate_controls"]) == len(run["predictor_stages"]) == horizon,
        "affine prediction horizon differs",
    )
    for k, (stage, control) in enumerate(
        zip(run["predictor_stages"], run["candidate_controls"], strict=True)
    ):
        for i, (row, input_row, offset) in enumerate(
            zip(stage["A"], stage["B"], stage["c"], strict=True)
        ):
            predicted = (
                sum(a * x for a, x in zip(row, run["candidate"][k], strict=True))
                + sum(b * u for b, u in zip(input_row, control, strict=True))
                + offset
            )
            require(
                abs(predicted - run["candidate"][k + 1][i]) <= 1e-8 * (1 + abs(predicted)),
                "saved affine candidate recurrence differs",
            )
    for region in run["stages"]:
        require(
            region["intersection_identity"] == IDENTITY and region["relation"] == "inner",
            "unsupported intersection identity",
        )
        _inside_carrier(region, n)
        require(len(region["projections"]) == len(task["planes"]), "projection plane count differs")
        for projection in region["projections"]:
            require(
                seal(projection["B"]) == projection["saved_projection_sha256"],
                "saved projection coordinates differ",
            )
            require(
                bool(projection["B"]) and all(len(p) == 2 and _finite(p) for p in projection["B"]),
                "invalid projected coordinates",
            )


def validate_task(task):
    require(
        [p["indices"] for p in task["planes"]] == PLANES[task["id"]],
        "physical coordinate transform differs",
    )
    require(
        task["display_permutation"]
        == (
            [2, 0, 3, 1]
            if task["id"] == "syn-nl-fuel-01"
            else list(range(len(task["coordinates"])))
        ),
        "display coordinate permutation differs",
    )
    require(
        len(task["runs"]) == 5 and {r["family"] for r in task["runs"]} == set(episodes.FAMILIES),
        "five matched families required",
    )
    for key in ("task_sha256", "objective_id", "action_profile_id"):
        require(len({r[key] for r in task["runs"]}) == 1, "unmatched task/cost/action identities")
    for run in task["runs"]:
        validate_run(run, task)


def collect(assets):
    """Consume assets already authenticated by the existing episode publisher."""

    def raw(name):
        return assets[episodes.ROUTE + "/" + name]

    from contracts import load_task, manifest_sha256

    provenance = json.loads(raw("provenance.json"))
    data = {}
    for name, title, horizon in episodes.TASKS:
        source_task = load_task(name)
        receipt = json.loads(raw(f"figures/{name}/projection-receipt.json"))
        coordinates = [{"name": n, "unit": u} for n, u in COORDINATES[name]]
        require(
            [c["unit"] for c in coordinates] == [s["unit"] for s in source_task["model"]["states"]],
            "physical coordinate units differ from source",
        )
        task = {
            "schema": "csl.saved-fixed-tail-geometry/1",
            "id": name,
            "title": title,
            "horizon": horizon,
            "query": 0,
            "time_unit": source_task["episode"]["time_unit"],
            "coordinates": coordinates,
            "display_permutation": [2, 0, 3, 1]
            if name == "syn-nl-fuel-01"
            else list(range(len(coordinates))),
            "planes": [
                {
                    "indices": ix,
                    "labels": [
                        coordinates[i]["name"] + " (" + coordinates[i]["unit"] + ")" for i in ix
                    ],
                }
                for ix in PLANES[name]
            ],
            "source": provenance,
            "renderer_sha256": digest(Path(__file__).read_bytes()),
            "projection_receipt_sha256": digest(raw(f"figures/{name}/projection-receipt.json")),
            "runs": [],
        }
        for family in episodes.FAMILIES:
            folder = f"records/{name}-{family}"
            sealed = json.loads(raw(folder + "/receipt.json"))
            archive_bytes = raw(folder + "/raw.zip")
            require(
                digest(archive_bytes) == sealed["raw_zip_sha256"], "raw archive identity differs"
            )
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                payloads = []
                for path in (
                    "attempt.json",
                    "native-query-000-response.jsonl",
                    "native-query-000-request.jsonl",
                ):
                    value = archive.read(path)
                    require(
                        digest(value) == sealed["archive_members"][path]["sha256"],
                        "raw member identity differs: " + path,
                    )
                    payloads.append(value)
                attempt_raw, response_raw, request_raw = payloads
                attempt, response, request = map(
                    json.loads, (attempt_raw, response_raw, request_raw)
                )
            require(
                response["status"] == "accepted" and response["family"] == family,
                "query is not accepted for the named family",
            )
            require(
                request["original_horizon"]
                == attempt["original_intervals"]
                == attempt["completed_holds"]
                == horizon,
                "original horizon differs",
            )
            for key in ("task_id", "task_sha256", "action_profile_id"):
                require(
                    request[key] == response[key] == attempt[key],
                    "query task/action identity differs",
                )
            dimension = len(coordinates)
            candidate = [
                response["history"][i * dimension : (i + 1) * dimension] for i in range(horizon + 1)
            ]
            controls = len(request["control_bounds"])
            tail_controls = response["history"][(horizon + 1) * dimension :]
            require(
                len(tail_controls) == horizon * controls, "saved candidate control horizon differs"
            )
            run = {
                "family": family,
                "task_sha256": attempt["task_sha256"],
                "objective_id": attempt["objective_id"],
                "action_profile_id": attempt["action_profile_id"],
                "controller_id": attempt["controller_id"],
                "graph_id": attempt["resolved_graph"]["graph_id"],
                "affine_model_sha256": seal(request["predictor_stages"]),
                "source_history_sha256": seal(response["source_history"]),
                "tail_stage_lifts_sha256": seal(
                    [r["tail_state_lift"] for r in response["regions"]]
                ),
                "request_sha256": digest(request_raw),
                "response_sha256": digest(response_raw),
                "attempt_sha256": digest(attempt_raw),
                "raw": "../" + episodes.ROUTE + "/" + folder + "/raw.zip",
                "providers": response["providers"],
                "source_cost": response["source_cost"],
                "candidate": candidate,
                "execution": attempt["physical_states"],
                "dt": request["dt"],
                "candidate_controls": [
                    tail_controls[k * controls : (k + 1) * controls] for k in range(horizon)
                ],
                "predictor_stages": [
                    {key: s[key] for key in ("A", "B", "c")} for s in request["predictor_stages"]
                ],
                "state_bounds": request["state_bounds"],
                "stages": [],
            }
            require(len(response["regions"]) == horizon + 1, "complete region horizon required")
            for k, region in enumerate(response["regions"]):
                require(
                    region["stage"] == k and region["family"] == family,
                    "saved native region stage differs",
                )
                require(
                    region["scope"] == "fixed-feasible-tail intersect finite all-control carrier",
                    "unrecognized conditional region scope",
                )
                projections = []
                for plane in task["planes"]:
                    indices = plane["indices"]
                    saved = next(
                        p
                        for p in receipt["plots"]
                        if p["family"] == family and set(p["raw_indices"]) == set(indices)
                    )
                    require(
                        saved["response_sha256"] == digest(response_raw)
                        and saved["attempt_sha256"] == digest(attempt_raw),
                        "projection receipt source differs",
                    )
                    if k == 0:
                        points = [[candidate[0][i] for i in indices]]
                        method = "initial observed singleton"
                        method_details = {"method": method}
                    else:
                        item = saved["projections"][k - 1]
                        require(item["stage"] == k, "saved projection stage differs")
                        points = [
                            [point[saved["raw_indices"].index(i)] for i in indices]
                            for point in item["points"]
                        ]
                        method = item["method"]
                        method_details = {
                            key: value
                            for key, value in item.items()
                            if key not in {"points", "stage"}
                        }
                    projections.append(
                        {
                            "B": points,
                            "saved_projection_sha256": seal(points),
                            "method": method,
                            "method_details": method_details,
                        }
                    )
                run["stages"].append(
                    {
                        "stage": k,
                        "lower": region["carrier_lower"],
                        "upper": region["carrier_upper"],
                        "membership": region["membership"],
                        "relation": region["relation"],
                        "source_pointer": f"native-query-000-response.jsonl#/regions/{k}",
                        "intersection_identity": region["intersection_identity"],
                        "projections": projections,
                    }
                )
            run["containment_verified"] = True
            task["runs"].append(run)
        # The targets are source objective references, never hard terminal sets.
        require(
            all(run["task_sha256"] == manifest_sha256(source_task) for run in task["runs"]),
            "source task differs from immutable episode task",
        )
        require(
            all(
                run["execution"][0] == [s["initial"] for s in source_task["model"]["states"]]
                and run["dt"] == source_task["episode"]["dt"]
                for run in task["runs"]
            ),
            "source initial observation or time grid differs",
        )
        objective = source_task["objective"]
        task["soft_reference"] = objective.get("source_definition", {}).get("terminal_target")
        if task["soft_reference"] is None:
            task["soft_reference"] = [
                objective["target"]["radius_km"],
                None,
                None,
                objective["target"]["angular_rate_rad_s"],
            ]
        validate_task(task)
        data[name] = task
    return data


def _plot(task, plane_index):
    import matplotlib

    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.rcParams.update(
            {"svg.hashsalt": ROUTE, "font.family": "DejaVu Sans", "svg.fonttype": "none"}
        )
        return _plot_image(task, plane_index)


def _plot_image(task, plane_index):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.patches import Polygon

    if __package__:
        from .figure_style import configure_numeric_axis
    else:
        from figure_style import configure_numeric_axis
    fig, ax = plt.subplots(figsize=(10, 7), layout="constrained")
    indices = task["planes"][plane_index]["indices"]
    # The static export keeps the same roles as the interactive view.
    cmap = LinearSegmentedColormap.from_list("saved-stage", ["#8156a8", "#177a96", "#a96010"])
    norm = Normalize(0, task["horizon"])
    for color, run in zip(
        ["#1769aa", "#8156a8", "#9e5c00", "#c04424", "#18864b"], task["runs"], strict=True
    ):
        for stage in run["stages"]:
            stage_color = cmap(norm(stage["stage"]))
            a, b = indices
            lo, hi = stage["lower"], stage["upper"]
            carrier = [[lo[a], lo[b]], [hi[a], lo[b]], [hi[a], hi[b]], [lo[a], hi[b]]]
            ax.add_patch(
                Polygon(
                    carrier,
                    closed=True,
                    fill=False,
                    edgecolor=stage_color,
                    alpha=0.12,
                    linewidth=0.5,
                )
            )
            points = stage["projections"][plane_index]["B"]
            if len(points) > 2:
                ax.add_patch(
                    Polygon(
                        points,
                        closed=True,
                        fill=False,
                        edgecolor=stage_color,
                        alpha=0.45,
                        linewidth=0.7,
                        linestyle="--",
                    )
                )
            elif points:
                ax.plot(*zip(*points, strict=True), color=stage_color, alpha=0.5, linewidth=0.6)
        ax.plot(
            *zip(*[[p[i] for i in indices] for p in run["candidate"]], strict=True),
            color=color,
            linestyle="--",
            alpha=0.6,
            linewidth=0.8,
        )
        x, y = zip(*[[p[i] for i in indices] for p in run["execution"]], strict=True)
        ax.plot(x, y, color=color, label=run["family"], linewidth=1.5)
        ax.scatter([x[0]], [y[0]], color=color, marker="o", s=18)
        ax.scatter([x[-1]], [y[-1]], color=color, marker="*", s=50)
    target = [task["soft_reference"][i] for i in indices]
    if all(v is not None for v in target):
        ax.scatter(*target, marker="+", color="#3d405b", s=70, label="Soft objective reference")
    ax.set_xlabel(task["planes"][plane_index]["labels"][0])
    ax.set_ylabel(task["planes"][plane_index]["labels"][1])
    ax.set_title(task["title"] + ": query 0, every state stage 0–" + str(task["horizon"]))
    ax.text(
        0.01,
        -0.19,
        "Stage-colored regions: pale outer carrier F; dashed conditional inner B = I.\n"
        "Dashed paths: affine candidates. Solid paths: nonlinear execution. Circle: initial; star: final.\n"
        "I = F ∩ B = B in full state space; no global backward-set or nonlinear enclosure claim.\n"
        "Saved episode source a6b7d1cb; native C++ source 99fe6e3c. Full identities and raw links: plotted-data JSON.",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
    )
    configure_numeric_axis(ax)
    ax.autoscale_view()
    ax.legend(ncol=3, fontsize=9)
    fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, label="Output state stage")
    result = {}
    for ext in ("svg", "png"):
        stream = io.BytesIO()
        fig.savefig(stream, format=ext, dpi=140, metadata={"Date": None} if ext == "svg" else {})
        result[ext] = stream.getvalue()
    plt.close(fig)
    return result


def build(episode_assets):
    data = collect(episode_assets)
    outputs = {}
    for name, task in data.items():
        outputs[f"{ROUTE}/{name}.json"] = (
            json.dumps(task, allow_nan=False, separators=(",", ":")) + "\n"
        ).encode()
        for i in range(len(task["planes"])):
            for ext, raw in _plot(task, i).items():
                outputs[f"{ROUTE}/{name}-plane-{i}.{ext}"] = raw
    for name in ("index.html", "geometry.js", "geometry.css"):
        outputs[ROUTE + "/" + name] = (
            ROOT / "scripts/reports/assets/native-fixed-tail-geometry" / name
        ).read_bytes()
    entry = {
        "family": "Native set-based control",
        "title": "Explore all-stage F/B/I geometry across five families",
        "status": "saved-data-companion",
        "anchor": ROUTE,
        "page": ROUTE + "/index.html",
        "figure": ROUTE + "/syn-nl-lv-01-plane-0.svg",
        "source_page": "https://github.com/butahlecoq/controlled-systems-lab/tree/a6b7d1cb6e655284d7859dfa8f7b010145d463f5",
        "raw_record": ROUTE + "/syn-nl-lv-01.json",
    }
    card = f'<article class="saved-figure" id="{ROUTE}"><h3>{entry["title"]}</h3><a href="{entry["page"]}"><img src="{entry["figure"]}" alt="Five matched native fixed-tail families with all-stage conditional regions and nonlinear execution"></a><p>Select the task, family, layer and output stage. Saved full-state geometry; no global backward-set or nonlinear enclosure claim.</p><p><a href="{entry["page"]}">Explore the saved geometry →</a></p></article>'
    return outputs, entry, card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output directory must be new")
    old, _, _ = episodes.build()
    new, _, _ = build(old)
    for name, raw in {
        **old,
        **new,
        "examples.css": (ROOT / "docs/examples/examples.css").read_bytes(),
        "index.html": (
            '<!doctype html><html lang="en"><meta charset="utf-8"><title>Saved native geometry</title>'
            f'<h1>Saved native geometry</h1><p><a href="{ROUTE}/index.html">Explore all-stage F/B/I geometry</a></p>'
            f'<p><a href="{episodes.ROUTE}/index.html">Original A6 episodes and raw records</a></p></html>'
        ).encode(),
    }.items():
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    print(args.output / ROUTE / "index.html")


if __name__ == "__main__":
    main()
