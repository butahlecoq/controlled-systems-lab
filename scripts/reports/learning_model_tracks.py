"""Render the learning book's crosswalk from existing native model and result records."""

from __future__ import annotations

import csv
import io
import json
import re
from html import escape
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

TRACKING = "native-model-tracking-first-pass-v1"


def _discrete_models(report_root: Path) -> str:
    route = f"../examples/{TRACKING}"
    with ZipFile(report_root / TRACKING / f"{TRACKING}.zip") as archive:

        def rows(name: str) -> list[dict[str, str]]:
            with (
                archive.open(name) as raw,
                io.TextIOWrapper(raw, encoding="utf-8", newline="") as text,
            ):
                return list(csv.DictReader(text))

        models = rows("raw/catalogue.csv")
        outcome_rows = rows("checks/independent_results.csv")
        results = {row["model"]: row for row in outcome_rows}
        members = set(archive.namelist())
    ids = [model["model"] for model in models]
    if len(ids) != len(set(ids)) or len(results) != len(outcome_rows) or set(ids) != results.keys():
        raise ValueError("discrete model and tracking result identities disagree")

    figures = {}
    for member in sorted(members):
        match = re.fullmatch(r"figures/(model-\d+)-state-[\d-]+\.svg", member)
        if match:
            figures.setdefault(match[1], member)
    items = []
    for model in models:
        ident = model["model"]
        match = re.fullmatch(r"catalogue-2026/model-(\d+)/1", ident)
        if match is None:
            raise ValueError(f"unrecognized native discrete model identity {ident}")
        index = int(match[1])
        folder = f"model-{index:02d}"
        result = results[ident]
        passed = result["status"] == "passed"
        if not passed and result["status"] != "failure_preserved":
            raise ValueError(f"unrecognized tracking check for {ident}")
        record = f"raw/{folder}/" + ("run.txt" if passed else "native-refusal.json")
        if record not in members:
            raise ValueError(f"tracking outcome link is missing for {ident}")
        plot = figures.get(folder)
        plot_link = f' · <a href="{route}/{escape(plot)}">Observed trajectory</a>' if plot else ""
        matrix_label = quote(f"{index}. {model['title']} · {model['source_title']}", safe="")
        profile = {
            "authored nominal tracking": "Authored tracking task",
            "source21 literal": "Source-defined MPC task",
        }.get(result["profile"], result["profile"])
        items.append(
            f'<details id="discrete-model-{index}"><summary>{escape(model["title"])} · '
            f"{escape(result['state_dimension'])} states, {escape(result['control_dimension'])} controls</summary>"
            f"<p><code>{escape(ident)}</code> · Δt = {escape(model['time_step'])} {escape(model['time_unit'])}. "
            f'<a href="../examples/native-discrete-models.html#model-{index}">Coordinates and source qualification</a>.</p>'
            f'<p><a href="{route}/index.html#:~:text={matrix_label}">Matrices and initial vectors</a> · '
            f'{escape(profile)} · <a href="{route}/{record}">'
            f"{'Checked run' if passed else 'Preserved solver refusal'}</a>{plot_link}.</p></details>"
        )
    return (
        '<section id="discrete-formulations"><h2>Discrete linear models</h2>'
        "<p>Each model supplies xₖ₊₁ = Axₖ + Buₖ + Gwₖ + a, its initial state and its time step. "
        "The model records carry discrete coefficients. A continuous-time approximation error requires separate evidence. Each tracking task specifies its own objective, horizon and observations. "
        "Open a model to see the task used and its outcome.</p>"
        f'<p><a href="{route}/index.html">Matrices and initial vectors for all models</a> · '
        f'<a href="{route}/raw/coordinates.csv">Ordered coordinates and units</a> · '
        f'<a href="{route}/checks/independent_results.csv">Independent checks</a></p>'
        + "".join(items)
        + "</section>"
    )


def native_sections(repository_root: Path, chapters: list[dict]) -> str:
    report_root = repository_root / "reports/algorithm-results"
    sections = []
    for chapter in chapters:
        if chapter["id"] == "native-model-tracking-first-pass":
            sections.append(_discrete_models(report_root))
        if chapter["id"] != "native-forward-models":
            continue
        items = []
        for record in chapter["records"]:
            relative = record.get("formulation_record")
            if not relative:
                continue
            path = report_root / relative
            if path.suffix == ".json":
                ids = json.loads(path.read_bytes())["case_ids"]
            else:
                ids = re.findall(r"^case=(\S+)", path.read_text(), flags=re.MULTILINE)
            if not ids:
                raise ValueError(f"no native formulation identities in {relative}")
            identities = ", ".join(f"<code>{escape(ident)}</code>" for ident in ids)
            items.append(
                f'<li><a href="{escape(record["href"], quote=True)}">{escape(record["label"])}</a>'
                f"<p>{escape(record['formulation_note'])}</p><p>{identities}</p></li>"
            )
        sections.append(
            '<section id="reachability-formulations"><h2>Forward reachability cases</h2>'
            "<p>Each case specifies dynamics, an initial set, admissible inputs and a horizon. "
            "The linked lessons give the equations, numerical assumptions and all-stage projections.</p><ul>"
            + "".join(items)
            + "</ul></section>"
        )
    return "".join(sections)
