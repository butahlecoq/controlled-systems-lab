"""Build the progressive learning book from its authored chapter manifest."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import quote

try:
    import learning_model_tracks
    import mathematical_notation
    import site_additions
    import site_design
    import source_index_names
except ModuleNotFoundError as error:
    if error.name not in {
        "site_design",
        "site_additions",
        "mathematical_notation",
        "learning_model_tracks",
        "source_index_names",
    }:
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import learning_model_tracks
    import mathematical_notation
    import site_additions
    import site_design
    import source_index_names


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/catalogue/learning-book-v1.json"
INVENTORY = ROOT / "docs/catalogue/module-composition-inventory-v1.json"
CHAPTER_ROOT = ROOT / "docs/examples/learning/chapters"
BOOK_PATH = "learn"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _repository_href(path: str) -> str:
    return "https://github.com/butahlecoq/controlled-systems-lab/blob/main/" + quote(
        path, safe="/._-"
    )


def _module_test_declarations(modules: list[dict]) -> list[str]:
    """Resolve each source-backed module to its CMake-owned focused test declaration."""
    cmake_files = list((ROOT / "src").rglob("Module.cmake"))
    owners: set[str] = set()
    for module in modules:
        source = module.get("source", {}).get("path", "")
        if source.startswith("src/"):
            relative_source = source[4:]
            for module_file in cmake_files:
                if relative_source in module_file.read_text(encoding="utf-8"):
                    test_file = module_file.with_name("Tests.cmake")
                    if test_file.is_file():
                        owners.add(test_file.relative_to(ROOT).as_posix())
        elif source.startswith("include/csl/"):
            area = source.split("/", 3)[2]
            test_file = ROOT / "src" / area / "Tests.cmake"
            if test_file.is_file():
                owners.add(test_file.relative_to(ROOT).as_posix())
    return sorted(owners)


def _module_interface(module: dict) -> tuple[str, str, str]:
    """Describe the real provider seam or direct route for one inventory entry."""
    kind = module["kind"]
    identity = module["identity"].get("id", "")
    source = module.get("source", {}).get("path", "")
    ports = {
        "LPPort": "include/csl/registry/registry.hpp",
        "HullReducerPort": "include/csl/geometry/hull_reducer.hpp",
        "SourceIndexHullPort": "include/csl/geometry/source_index_hull.hpp",
        "ApproximationPort": "include/csl/registry/registry.hpp",
        "StrategyRegistration / StrategyPort": "include/csl/registry/registry.hpp",
        "ConversionPort": "include/csl/registry/registry.hpp",
        "GeometryPort": "include/csl/registry/registry.hpp",
        "ConvexPort": "include/csl/registry/registry.hpp",
        "HistoryOptimizerPort": "include/csl/optimization/history_optimizer.hpp",
    }
    if kind == "registered_provider":
        if identity.startswith(("csl.lp.", "phase-one-")):
            name = "LPPort"
        elif identity.startswith("csl.hull.source."):
            name = "SourceIndexHullPort"
        elif identity.startswith("csl.hull."):
            name = "HullReducerPort"
        elif (
            identity.startswith("csl.approximation.")
            or identity == "csl.geometry.zonotope.axis-cover"
        ):
            name = "ApproximationPort"
        elif identity.startswith("csl.synthesis."):
            name = "StrategyRegistration / StrategyPort"
        elif identity.startswith("csl.conversion."):
            name = "ConversionPort"
        elif identity.startswith("csl.geometry."):
            name = "GeometryPort"
        elif identity.startswith("csl.convex."):
            name = "ConvexPort"
        elif identity.startswith(("csl.nlp.", "csl.conic.")):
            name = "HistoryOptimizerPort"
        else:
            raise ValueError(f"{identity}: registered provider has no documented interface mapping")
        return (
            name,
            ports[name],
            "Registered provider; implementation source is linked in this entry.",
        )
    if kind == "internal_registration_factory":
        name = "ApproximationPort"
        return name, ports[name], "Factory that creates the typed provider registration."
    if kind == "public_representation_type":
        return (
            "Public representation type",
            source,
            "Data type, not an interchangeable algorithm provider.",
        )
    if kind == "public_function_route":
        return (
            "Direct public function",
            source,
            "Public API route; no provider substitution is declared.",
        )
    if kind == "external_program_route":
        return (
            "External program route",
            source,
            "Executable or script entry; no C++ provider seam is declared.",
        )
    raise ValueError(f"{identity or source}: unsupported inventory kind {kind!r}")


def _module_ids(inventory: dict) -> set[str]:
    result = set()
    for module in inventory["modules"]:
        identity = module["identity"]
        result.add(identity.get("id") or identity.get("symbol"))
    return result


MODULE_SOURCE_WITNESSES = {
    "csl.geometry.projection-materializer": "make_projection_registration",
}


def _module_has_source_witness(module_id: str, sources: list[Path]) -> bool:
    code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sources
        if path.suffix in {".cpp", ".cc", ".cxx"}
    )
    witness = MODULE_SOURCE_WITNESSES.get(module_id, module_id)
    if witness in code:
        return True
    if not module_id.startswith("csl::"):
        return False
    symbol = module_id.rsplit("::", 1)[-1]
    if symbol == "solve":
        namespace = module_id.rsplit("::", 1)[0]
        return namespace in code and re.search(r"\bsolve\s*\(", code) is not None
    return re.search(r"\b" + re.escape(symbol) + r"\b", code) is not None


def _cpp_game_initializer(path: Path, declaration: str):
    source = path.read_text(encoding="utf-8")
    start = source.index(declaration) + len(declaration) - 1
    depth = 0
    for end in range(start, len(source)):
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
            if depth == 0:
                break
    else:
        raise ValueError(f"unclosed game fixture in {path}")
    text = re.sub(r"\b(?:Stage|StateIndex|StateId|Terminal)\s*", "", source[start : end + 1])
    text = text.translate(str.maketrans({"{": "[", "}": "]"}))
    text = re.sub(r"\btrue\b", "True", text)
    text = re.sub(r"\bfalse\b", "False", text)
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"invalid game fixture in {path}") from error


def _validate_finite_controller_tables(chapter: dict) -> None:
    if chapter.get("id") != "finite-controller-consumers":
        return
    sources = {
        entry["source"]: (ROOT / entry["source"]).resolve()
        for entry in chapter.get("source_witnesses", [])
    }
    feedback = _cpp_game_initializer(sources["tests/installed/finite_feedback_client.cpp"], "Game{")
    if len(feedback) != 4:
        raise ValueError("finite feedback fixture must contain states, stages, safety and target")
    state_count, stages, terminal_safe, terminal_target = feedback
    if len(stages) != 1:
        raise ValueError("finite feedback lesson expects one stage")
    stage_safe, action_count, disturbance_count, successors = stages[0]
    if action_count != 1 or disturbance_count != 1:
        raise ValueError("finite feedback lesson expects one action and one disturbance")
    tables = {table["label"]: table["rows"] for table in chapter.get("mathematical_tables", [])}

    def number_text(value) -> str:
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)

    expected_transition = [
        [str(state), "yes" if stage_safe[state] else "no", str(successors[state][0][0][0])]
        for state in range(state_count)
    ]
    expected_terminal = [
        [
            str(state),
            "yes" if terminal_safe[state] else "no",
            "yes" if terminal_target[state] else "no",
        ]
        for state in range(state_count)
    ]
    if (
        tables.get("Finite feedback game. The disturbance is selected after the action.")
        != expected_transition
    ):
        raise ValueError("finite feedback transition table differs from its executable fixture")
    if tables.get("Finite feedback terminal layer") != expected_terminal:
        raise ValueError("finite feedback terminal table differs from its executable fixture")

    minimax = _cpp_game_initializer(
        sources["tests/installed/finite_causal_minimax_client.cpp"], "Game game{"
    )
    stages, terminal, initial = minimax
    if len(stages) != 1:
        raise ValueError("causal minimax lesson expects one stage")
    state_count, action_count, disturbance_count, stage_safe, successors = stages[0]
    terminal_count, terminal_safe, costs = terminal
    if state_count != 1 or action_count != 2 or disturbance_count != 1 or initial != [0]:
        raise ValueError("causal minimax lesson expects the checked one-state, two-action fixture")
    expected_costs = [
        [
            str(action),
            str(successors[0][action][0][0]),
            number_text(costs[successors[0][action][0][0]]),
        ]
        for action in range(action_count)
    ]
    expected_terminal_costs = [
        [str(state), "yes" if terminal_safe[state] else "no", number_text(costs[state])]
        for state in range(terminal_count)
    ]
    if (
        tables.get("Finite causal-minimax cost game. Each action has one disturbance outcome.")
        != expected_costs
    ):
        raise ValueError("causal minimax action table differs from its executable fixture")
    expected_stage = [["0", "yes" if stage_safe[0] else "no", "yes"]]
    if tables.get("Causal-minimax stage 0 state") != expected_stage:
        raise ValueError("causal minimax stage table differs from its executable fixture")
    if tables.get("Causal-minimax terminal layer") != expected_terminal_costs:
        raise ValueError("causal minimax terminal table differs from its executable fixture")
    best_action = min(range(action_count), key=lambda action: costs[successors[0][action][0][0]])
    best_successor = successors[0][best_action][0][0]
    expected_decisions = [
        ["finite feedback", "action 0 from state 0", "state 0 is winning at stage 0"],
        [
            "causal minimax",
            f"action {best_action} from state 0",
            f"minimum terminal cost is {number_text(costs[best_successor])}",
        ],
    ]
    if tables.get("Decisions returned by the clients") != expected_decisions:
        raise ValueError("finite controller decisions differ from the executable fixtures")


def validate(manifest: dict, inventory: dict, figure_index: dict | None = None) -> list[dict]:
    if manifest.get("schema") != "csl.learning-book/1":
        raise ValueError("unsupported learning book manifest schema")
    if inventory.get("schema") != "csl.module-composition-inventory/1":
        raise ValueError("unsupported module inventory schema")
    chapters = manifest.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("chapter order must be a nonempty list")
    ids = [chapter.get("id") for chapter in chapters]
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value)
        for value in ids
    ):
        raise ValueError("chapter IDs must be lowercase URL-safe slugs")
    if len(set(ids)) != len(ids):
        raise ValueError("chapter IDs must be unique")
    by_id = set(ids)
    position = {chapter_id: index for index, chapter_id in enumerate(ids)}
    known_modules = _module_ids(inventory)
    if figure_index and figure_index.get("schema") != "csl.closed-loop.figure-index/1":
        raise ValueError("unsupported closed-loop figure index schema")
    figure_entries = (figure_index or {}).get("figures", [])
    if not isinstance(figure_entries, list):
        raise ValueError("figure index figures must be a list")
    figure_ids = [item.get("id") for item in figure_entries]
    if any(not isinstance(value, str) or not value for value in figure_ids) or len(
        set(figure_ids)
    ) != len(figure_ids):
        raise ValueError("figure index IDs must be nonempty and unique")
    known_figures = {item["id"]: item for item in figure_entries}
    for chapter in chapters:
        if chapter.get("role") not in {"educational", "evidence"}:
            raise ValueError(f"{chapter['id']}: invalid educational/evidence role")
        if chapter.get("status") not in {"ready", "pending"}:
            raise ValueError(f"{chapter['id']}: invalid chapter status")
        example_sources = chapter.get("example_sources")
        if not isinstance(example_sources, list) or not example_sources:
            raise ValueError(f"{chapter['id']}: chapter needs source paths for its example or data")
        for example in example_sources:
            path = (ROOT / example).resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                raise ValueError(f"{chapter['id']}: missing or unsafe example source {example}")
            if path.suffix == ".json":
                try:
                    source_document = _read_json(path)
                except (OSError, json.JSONDecodeError):
                    source_document = None
                if (
                    isinstance(source_document, dict)
                    and source_document.get("schema") == "csl.closed-loop.task/1"
                ):
                    _validate_model_track_contract(chapter, example, source_document)
        unknown_prerequisites = set(chapter.get("prerequisites", [])) - by_id
        if unknown_prerequisites:
            raise ValueError(
                f"{chapter['id']}: unknown prerequisites {sorted(unknown_prerequisites)}"
            )
        if any(
            position[parent] >= position[chapter["id"]]
            for parent in chapter.get("prerequisites", [])
        ):
            raise ValueError(f"{chapter['id']}: prerequisites must precede the chapter")
        module_ids = set(chapter.get("module_ids", []))
        unknown_modules = module_ids - known_modules
        if unknown_modules:
            raise ValueError(f"{chapter['id']}: unknown module IDs {sorted(unknown_modules)}")
        if module_ids:
            if chapter.get("kind") != "installed consumer":
                raise ValueError(
                    f"{chapter['id']}: module claims require an installed consumer lesson"
                )
            example_sources = chapter.get("example_sources", [])
            if not example_sources:
                raise ValueError(
                    f"{chapter['id']}: module claims require executable example_sources"
                )
            source_paths = []
            for example in example_sources:
                path = (ROOT / example).resolve()
                if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                    raise ValueError(
                        f"{chapter['id']}: missing or unsafe consumer source {example}"
                    )
                source_paths.append(path)
            for module_id in module_ids:
                if not _module_has_source_witness(module_id, source_paths):
                    raise ValueError(
                        f"{chapter['id']}: module {module_id} has no executable source witness"
                    )
        elif chapter.get("kind") not in {
            "analytic illustration",
            "installed consumer",
            "saved evidence",
        }:
            raise ValueError(f"{chapter['id']}: invalid lesson kind")
        source = CHAPTER_ROOT / chapter["source"]
        if not source.is_file() or source.parent.resolve() != CHAPTER_ROOT.resolve():
            raise ValueError(f"{chapter['id']}: missing or unsafe authored chapter source")
        body = source.read_text(encoding="utf-8")
        if "<h1" in body.lower():
            raise ValueError(f"{chapter['id']}: source must not add a second page h1")
        if chapter["status"] == "ready" and chapter.get("kind") == "saved evidence":
            sources = chapter.get("example_sources", [])
            if not sources:
                raise ValueError(f"{chapter['id']}: saved evidence needs example_sources")
            for source_name in sources:
                source_path = (ROOT / source_name).resolve()
                if not source_path.is_relative_to(ROOT.resolve()) or not source_path.is_file():
                    raise ValueError(
                        f"{chapter['id']}: missing or unsafe saved evidence source {source_name}"
                    )
        if chapter["status"] == "ready":
            for field in (
                "mathematical_input",
                "command",
                "expected_output",
                "intermediate_geometry",
                "support_limits",
            ):
                if not chapter.get(field):
                    raise ValueError(f"{chapter['id']}: ready chapter missing {field}")
            if not chapter.get("mathematical_displays") and not chapter.get("mathematical_tables"):
                raise ValueError(
                    f"{chapter['id']}: ready chapter needs a primary mathematical display"
                )
        for witness in chapter.get("source_witnesses", []):
            witness_path = (ROOT / witness["source"]).resolve()
            if not witness_path.is_relative_to(ROOT.resolve()) or not witness_path.is_file():
                raise ValueError(
                    f"{chapter['id']}: missing or unsafe source witness {witness['source']}"
                )
            witness_text = witness_path.read_text(encoding="utf-8")
            for fragment in witness.get("contains", []):
                if fragment not in witness_text:
                    raise ValueError(
                        f"{chapter['id']}: source fixture changed in {witness['source']}: {fragment}"
                    )
        _validate_finite_controller_tables(chapter)
        for figure_id in chapter.get("figure_ids", []):
            item = known_figures.get(figure_id)
            if item is None:
                raise ValueError(
                    f"{chapter['id']}: figure {figure_id} is absent from the figure index"
                )
            if item.get("availability") not in {"ready", "pending", "unsupported"}:
                raise ValueError(f"{chapter['id']}: figure {figure_id} has invalid availability")
            if item.get("availability") == "ready" and not item.get("href"):
                raise ValueError(f"{chapter['id']}: ready figure {figure_id} has no href")
            if item.get("availability") == "ready" and (
                not isinstance(item.get("layer_scopes"), list)
                or not isinstance(item.get("missing_layers"), list)
            ):
                raise ValueError(
                    f"{chapter['id']}: ready figure {figure_id} needs included and missing scopes"
                )
            if item.get("availability") != "ready" and not item.get("reason"):
                raise ValueError(f"{chapter['id']}: unavailable figure {figure_id} needs a reason")
    ownership = [module_id for chapter in chapters for module_id in chapter.get("module_ids", [])]
    if len(ownership) != len(set(ownership)):
        raise ValueError("a module ID appears in more than one chapter")
    for index, chapter in enumerate(chapters):
        chapter["previous"] = ids[index - 1] if index else None
        chapter["next"] = ids[index + 1] if index + 1 < len(ids) else None
    return chapters


@lru_cache(maxsize=1)
def _saved_result_model_ids() -> dict[str, tuple[str, ...]]:
    identities: dict[str, set[str]] = {}
    for path in ROOT.glob("reports/closed-loop-pilot/*/attempts/*/attempt.json"):
        attempt = _read_json(path)
        task_id = attempt.get("task_id")
        model_id = attempt.get("model_id")
        if isinstance(task_id, str) and isinstance(model_id, str):
            identities.setdefault(task_id, set()).add(model_id)
    return {task_id: tuple(sorted(model_ids)) for task_id, model_ids in identities.items()}


@lru_cache(maxsize=1)
def _saved_result_prediction_ids() -> dict[str, tuple[str, ...]]:
    identities: dict[str, set[str]] = {}
    for path in ROOT.glob(
        "reports/closed-loop-pilot/closed-loop-pilot-v1/raw/attempts/**/check-input.json"
    ):
        record = _read_json(path)
        task = record.get("task") or {}
        task_id = task.get("task_id")
        prediction = task.get("prediction") or {}
        prediction_id = prediction.get("affine_model_id")
        if isinstance(task_id, str) and isinstance(prediction_id, str):
            identities.setdefault(task_id, set()).add(prediction_id)
    return {
        task_id: tuple(sorted(prediction_ids)) for task_id, prediction_ids in identities.items()
    }


def _validate_model_track_contract(chapter: dict, source_path: str, task: dict) -> None:
    """Check the model/predictor identities already owned by a closed-loop task contract."""
    task_id = task.get("task_id")
    model = task.get("model")
    if not isinstance(task_id, str) or not isinstance(model, dict):
        raise ValueError(f"{chapter['id']}: incomplete closed-loop model track in {source_path}")
    model_id = model.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"{chapter['id']}: plant model track has no stable model_id")
    source_identity = task.get("source") or {}
    source_model_id = source_identity.get("model_id")
    if source_model_id and source_model_id != model_id:
        raise ValueError(
            f"{chapter['id']}: source model_id {source_model_id!r} differs from plant track {model_id!r}"
        )
    states = model.get("states")
    controls = model.get("controls")
    equations = model.get("equations")
    prediction = task.get("prediction")
    if not isinstance(states, list) or not states or not isinstance(controls, list):
        raise ValueError(f"{chapter['id']}: model track needs ordered states and controls")
    if not isinstance(equations, list) or not equations:
        raise ValueError(f"{chapter['id']}: model track needs its defining equations")
    if not isinstance(prediction, dict) or not isinstance(prediction.get("affine_model_id"), str):
        raise ValueError(f"{chapter['id']}: predictor track needs an affine_model_id")

    # The published capability catalogue is an independent task-to-model crosswalk.
    capabilities_path = ROOT / "docs/catalogue/closed-loop-pilot-capabilities-v1.json"
    capabilities = _read_json(capabilities_path)
    matching = [
        graph for graph in capabilities.get("graphs", []) if graph.get("task_id") == task_id
    ]
    if matching and any(graph.get("model_id") != model_id for graph in matching):
        raise ValueError(
            f"{chapter['id']}: task/model identity disagrees with the published capability catalogue"
        )
    saved_model_ids = _saved_result_model_ids().get(task_id, ())
    if saved_model_ids and any(saved_model_id != model_id for saved_model_id in saved_model_ids):
        raise ValueError(
            f"{chapter['id']}: task/model identity disagrees with saved execution records"
        )
    saved_prediction_ids = _saved_result_prediction_ids().get(task_id, ())
    prediction_id = prediction["affine_model_id"]
    if saved_prediction_ids and any(
        saved_prediction_id != prediction_id for saved_prediction_id in saved_prediction_ids
    ):
        raise ValueError(
            f"{chapter['id']}: predictor identity disagrees with saved execution records"
        )


def _task_contracts(chapters: list[dict]) -> list[tuple[dict, str, dict]]:
    by_task_id: dict[str, tuple[dict, str, dict]] = {}
    for chapter in chapters:
        for source in chapter.get("example_sources", []):
            path = ROOT / source
            if path.suffix != ".json":
                continue
            contract = _read_json(path)
            if contract.get("schema") == "csl.closed-loop.task/1":
                task_id = contract.get("task_id")
                previous = by_task_id.get(task_id)
                if previous is None or chapter["id"].endswith("-capstone"):
                    by_task_id[task_id] = (chapter, source, contract)
    return list(by_task_id.values())


def _track_anchor(model_id: str) -> str:
    return "track-" + re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")


def _control_domain_bounds(bounds: object) -> str:
    if not isinstance(bounds, list) or not bounds:
        return "unspecified"
    intervals = []
    for interval in bounds:
        if not isinstance(interval, list) or len(interval) != 2:
            return "unspecified"
        intervals.append("[" + ", ".join(str(value) for value in interval) + "]")
    return " × ".join(intervals)


def _model_tracks_section(chapter: dict) -> str:
    tracks = [(source, contract) for owner, source, contract in _task_contracts([chapter])]
    if not tracks:
        return ""

    parts = ['<section class="model-tracks"><h2>System identity and model tracks</h2>']
    parts.append(
        "<p>The task contract is the source of truth for these formulations. Plant identity, "
        "prediction model, and reachable-set representation are separate choices.</p>"
    )
    for contract_path, task in tracks:
        model = task["model"]
        prediction = task["prediction"]
        episode = task.get("episode", {})
        anchor = _track_anchor(model["model_id"])
        parts.append(f'<article id="{escape(anchor, quote=True)}">')
        parts.append(
            f'<h3 id="{escape(anchor + "-plant", quote=True)}">Plant track <code>'
            + escape(model["model_id"])
            + "</code></h3><p><strong>Task.</strong> <code>"
            + escape(task["task_id"])
            + "</code>; <strong>source case.</strong> "
            + escape(str(model.get("case_id", "unspecified")))
            + ".</p>"
        )
        parts.append(
            '<p><strong>State ordering and coordinates.</strong></p><div class="scroll model-table" tabindex="0" role="region" aria-label="State coordinates"><table><thead><tr><th>Index</th><th>State</th><th>Initial</th><th>Unit</th><th>Bounds</th><th>Scale</th></tr></thead><tbody>'
        )
        for index, state in enumerate(model["states"], start=1):
            parts.append(
                "<tr><td>"
                + str(index)
                + "</td><td>"
                + escape(str(state.get("name", "")))
                + "</td><td>"
                + escape(str(state.get("initial", "unspecified")))
                + "</td><td>"
                + escape(str(state.get("unit", "unspecified")))
                + "</td><td>"
                + escape(str(state.get("bounds", "unspecified")))
                + "</td><td>"
                + escape(str(state.get("scale", "unspecified")))
                + "</td></tr>"
            )
        parts.append("</tbody></table></div><p><strong>Controls.</strong></p><ul>")
        for control in model["controls"]:
            parts.append(
                "<li><code>"
                + escape(str(control.get("name", "u")))
                + "</code> ∈ "
                + escape(str(control.get("bounds", "unspecified")))
                + " "
                + escape(str(control.get("unit", "")))
                + "</li>"
            )
        parts.append("</ul>")
        parts.append("<p><strong>Disturbances.</strong> ")
        parts.append(
            escape(str(task.get("disturbances", "Not specified by this task contract."))) + "</p>"
        )
        domains = task.get("control_domains", {})
        if domains:
            parts.append("<p><strong>Named task control domains.</strong></p><ul>")
            for name, domain in domains.items():
                profile = domain.get("problem_id", "")
                if "actions" in domain:
                    values = "; ".join(
                        "(" + ", ".join(str(value) for value in action) + ")"
                        for action in domain["actions"]
                    )
                    descriptor = "finite actions " + values
                else:
                    bounds = _control_domain_bounds(domain.get("bounds"))
                    descriptor = "control domain " + bounds
                parts.append(
                    "<li><strong>"
                    + escape(str(name))
                    + "</strong> <code>"
                    + escape(str(profile))
                    + "</code>: "
                    + escape(descriptor)
                    + "; "
                    + escape(str(domain.get("semantics", "semantics unspecified")))
                    + ".</li>"
                )
            parts.append("</ul>")
        parts.append('<p><strong>Plant equations.</strong></p><div class="equation-list">')
        for equation in model["equations"]:
            parts.append("<p>" + escape(equation) + "</p>")
        parts.append("</div>")
        if model.get("parameters"):
            parts.append(
                '<p><strong>Parameters.</strong></p><div class="scroll"><table><thead><tr><th>Parameter</th><th>Value</th><th>Unit</th></tr></thead><tbody>'
            )
            for name, parameter in model["parameters"].items():
                parts.append(
                    "<tr><td><code>"
                    + escape(str(name))
                    + "</code></td><td>"
                    + escape(str(parameter.get("value", "unspecified")))
                    + "</td><td>"
                    + escape(str(parameter.get("unit", "unspecified")))
                    + "</td></tr>"
                )
            parts.append("</tbody></table></div>")
        parts.append(
            "<p><strong>Domain.</strong> "
            + escape(str(model.get("domain", "not stated in the task contract")))
            + ".</p>"
        )
        source_identity = task.get("source") or {}
        if source_identity.get("path"):
            parts.append(
                '<p><strong>Source provenance.</strong> <a href="'
                + escape(_repository_href(source_identity["path"]), quote=True)
                + '"><code>'
                + escape(source_identity["path"])
                + "</code></a>; SHA-256 <code>"
                + escape(str(source_identity.get("sha256", "not recorded")))
                + "</code>.</p>"
            )
        parts.append(
            f'<h3 id="{escape(anchor + "-prediction", quote=True)}">Prediction track <code>'
            + escape(prediction["affine_model_id"])
            + "</code></h3><p><strong>Plant.</strong> "
            + escape(str(prediction.get("plant", "unspecified")))
            + ". <strong>Transformation.</strong> "
            + escape(str(prediction.get("discretization", "unspecified")))
            + ".</p><p><strong>Producer.</strong> <code>"
            + escape(str(prediction.get("producer", "unspecified")))
            + "</code>. <strong>Qualification.</strong> "
            + escape(str(prediction.get("validity", "not stated")))
            + ".</p>"
        )
        parts.append(
            "<p><strong>Time grid.</strong> "
            + escape(str(episode.get("intervals", "unspecified")))
            + " intervals over "
            + escape(str(episode.get("final_time", "unspecified")))
            + " "
            + escape(str(episode.get("time_unit", "unspecified")))
            + "; Δt = "
            + escape(str(episode.get("dt", "unspecified")))
            + ". Execution: "
            + escape(str((episode.get("execution") or {}).get("method", "unspecified")))
            + ".</p>"
        )
        objective = task.get("objective", {})

        def flatten_objective(prefix: str, value) -> list[tuple[str, object]]:
            if not isinstance(value, dict):
                return [(prefix, value)]
            fields = []
            for key, nested in value.items():
                fields.extend(flatten_objective(f"{prefix}.{key}" if prefix else key, nested))
            return fields

        objective_fields = flatten_objective("", objective)
        objective_fields = [
            (key, value) for key, value in objective_fields if key not in {"objective_id", "kind"}
        ]
        if objective_fields:
            parts.append(
                '<p><strong>Objective definition.</strong></p><div class="scroll"><table><thead><tr><th>Term</th><th>Definition/data</th></tr></thead><tbody>'
            )
            for key, value in objective_fields:
                rendered = (
                    "["
                    + "; ".join(
                        ", ".join(str(cell) for cell in row) if isinstance(row, list) else str(row)
                        for row in value
                    )
                    + "]"
                    if isinstance(value, list)
                    and value
                    and any(isinstance(row, list) for row in value)
                    else ", ".join(str(item) for item in value)
                    if isinstance(value, list)
                    else str(value)
                )
                parts.append(
                    '<tr><th scope="row"><code>'
                    + escape(key)
                    + "</code></th><td>"
                    + escape(rendered)
                    + "</td></tr>"
                )
            parts.append("</tbody></table></div>")
        terminal = task.get("terminal_condition")
        if terminal:
            terminal_summary = (
                "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in terminal.items())
                if isinstance(terminal, dict)
                else str(terminal)
            )
            parts.append(
                "<p><strong>Terminal condition.</strong> " + escape(terminal_summary) + ".</p>"
            )
        closed_loop = episode.get("closed_loop", {})
        closed_loop_summary = (
            "; ".join(f"{key.replace('_', ' ')}: {value}" for key, value in closed_loop.items())
            if isinstance(closed_loop, dict)
            else str(closed_loop)
        )
        parts.append(
            "<p><strong>Objective track.</strong> <code>"
            + escape(str(objective.get("objective_id", "unspecified")))
            + "</code> — "
            + escape(str(objective.get("kind", "unspecified")))
            + ".</p><p><strong>Closed-loop semantics.</strong> "
            + escape(closed_loop_summary)
            + ".</p><p><strong>Observation supplied to the controller.</strong> "
            + escape(str(closed_loop.get("observation", "Not specified by this task contract.")))
            + ".</p><p><strong>State and terminal constraints.</strong> State bounds are listed above; "
            + escape(str(terminal or "No terminal condition is specified."))
            + '. Objective targets are not feasibility constraints unless the contract says otherwise.</p><p><a href="'
            + escape(_repository_href(contract_path), quote=True)
            + '">Open the task contract and full objective/constraint definition</a>.</p>'
        )
        parts.append("</article>")
    parts.append("</section>")
    return "".join(parts)


def _model_tracks_page(chapters: list[dict], figure_index: dict | None = None) -> str:
    page = [
        site_design.page_start(
            "System formulations and model tracks",
            stylesheet_href="../examples/examples.css",
            crumbs=[
                ("Learn", "../index.html"),
                ("Learning book", "index.html"),
                ("Model tracks", "model-tracks.html"),
            ],
            main_class="page-content learning-reference",
            current_href="model-tracks.html",
        ),
        '<p class="eyebrow">Generated reference · source contracts</p><h1>System formulations and model tracks</h1>',
        "<p>Compare the dynamics before comparing controllers. The capstone contracts identify the plant, the model used to predict its motion and the objective. Below them, the native catalogues link forward reachability cases and discrete tracking models to their equations, inputs and recorded checks.</p>",
    ]
    sections = [("capstone-formulations", "Closed-loop capstones")]
    available = {chapter["id"] for chapter in chapters}
    if "native-forward-models" in available:
        sections.append(("reachability-formulations", "Forward reachability cases"))
    if "native-model-tracking-first-pass" in available:
        sections.append(("discrete-formulations", "Discrete linear models"))
    page.append(
        '<nav aria-label="Model families">'
        + " · ".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in sections)
        + "</nav>"
    )
    page.extend(
        [
            '<h2 id="capstone-formulations">Closed-loop capstones</h2>',
            '<div class="scroll" tabindex="0" role="region" aria-label="System model track comparison"><table><caption>System model track comparison</caption><thead><tr><th>System / task</th><th>Plant track</th><th>Prediction track</th><th>State/control dimensions</th><th>Prediction transformation</th><th>Task contract</th></tr></thead><tbody>',
        ]
    )
    figures_by_id: dict[str, dict] = {}
    figures_by_task: dict[str, list[dict]] = {}
    for figure in (figure_index or {}).get("figures", []):
        figure_id = figure.get("id")
        if isinstance(figure_id, str):
            figures_by_id[figure_id] = figure
        task_id = figure.get("task_id")
        if isinstance(task_id, str):
            figures_by_task.setdefault(task_id, []).append(figure)
    for chapter, source, task in _task_contracts(chapters):
        model = task["model"]
        prediction = task["prediction"]
        page.append(
            '<tr><th scope="row"><a href="'
            + escape(chapter["id"] + ".html", quote=True)
            + '">'
            + escape(chapter["title"])
            + "</a><br><code>"
            + escape(task["task_id"])
            + "</code></th><td>"
            + '<a href="'
            + escape(
                chapter["id"] + ".html#" + _track_anchor(model["model_id"]) + "-plant",
                quote=True,
            )
            + '"><code>'
            + escape(model["model_id"])
            + '</code></a></td><td><a href="'
            + escape(
                chapter["id"] + ".html#" + _track_anchor(model["model_id"]) + "-prediction",
                quote=True,
            )
            + '"><code>'
            + escape(prediction["affine_model_id"])
            + "</code></a></td><td>"
            + str(len(model["states"]))
            + " / "
            + str(len(model["controls"]))
            + "</td><td>"
            + escape(str(prediction.get("discretization", "unspecified")))
            + '</td><td><a href="'
            + escape(_repository_href(source), quote=True)
            + '">Task contract</a>'
        )
        visual_links = [
            figures_by_id[figure_id]
            for figure_id in chapter.get("figure_ids", [])
            if figure_id in figures_by_id
            and figures_by_id[figure_id].get("availability") == "ready"
            and figures_by_id[figure_id].get("href")
        ]
        visual_ids = {figure.get("id") for figure in visual_links}
        visual_links.extend(
            figure
            for figure in figures_by_task.get(task["task_id"], [])
            if figure.get("availability") == "ready"
            and figure.get("href")
            and figure.get("id") not in visual_ids
        )
        if visual_links:
            page.append("<br><strong>Visuals:</strong> ")
            page.append(
                " · ".join(
                    '<a href="../'
                    + escape(figure["href"], quote=True)
                    + '">'
                    + escape(str(figure.get("title") or figure["id"]))
                    + "</a>"
                    for figure in visual_links
                )
            )
        page.append("</td></tr>")
    page.append(
        "</tbody></table></div><p>Identical mathematics requires matching the plant and predictor track IDs and their definitions, along with the task’s controls, time grid and objective. A shared system name alone does not establish equivalence.</p>"
    )
    page.append(learning_model_tracks.native_sections(ROOT, chapters))
    page.append(site_design.page_end())
    return "".join(page)


def _chapter_page(
    chapter: dict,
    chapters: list[dict],
    chapter_html: str,
    figure_index: dict | None = None,
    inventory: dict | None = None,
) -> str:
    crumbs = [
        ("Learn", "../index.html"),
        ("Learning book", "index.html"),
        (chapter["title"], f"{chapter['id']}.html"),
    ]
    parts = [
        site_design.page_start(
            chapter["title"],
            stylesheet_href="../examples/examples.css",
            crumbs=crumbs,
            main_class="page-content learning-page",
            current_href=f"{chapter['id']}.html",
        )
    ]
    parts.append(f'<p class="eyebrow">{escape(chapter["group_label"])}</p>')
    parts.append(f"<h1>{escape(chapter['title'])}</h1>")
    role_label = "Educational material" if chapter["role"] == "educational" else "Saved evidence"
    parts.append(
        f'<p class="learning-status">{escape(chapter["status_label"])} · '
        f"Evidence class: {escape(role_label)}; {escape(chapter['kind'])}.</p>"
    )
    parts.append(chapter_html)
    parts.append(_model_tracks_section(chapter))
    displays = chapter.get("mathematical_displays", [])
    tables = chapter.get("mathematical_tables", [])
    if displays or tables or chapter.get("mathematical_conclusion"):
        parts.append('<section class="learning-math"><h2>Mathematical input</h2>')
        for display in displays:
            rows = display.get("rows")
            if not isinstance(rows, list) or not rows:
                raise ValueError(f"{chapter['id']}: mathematical display needs nonempty rows")
            label = escape(display["label"])
            parts.append(
                '<figure class="learning-math-display"><figcaption>'
                + label
                + '</figcaption><div class="scroll" tabindex="0" role="region" aria-label="'
                + escape(display["label"], quote=True)
                + '">'
                + mathematical_notation.matrix_html(rows, display["label"])
                + "</div></figure>"
            )
        for table in tables:
            columns = table.get("columns")
            rows = table.get("rows")
            if (
                not columns
                or not isinstance(rows, list)
                or any(len(row) != len(columns) for row in rows)
            ):
                raise ValueError(
                    f"{chapter['id']}: mathematical table needs matching columns and rows"
                )
            parts.append(
                '<div class="scroll" tabindex="0" role="region" aria-label="'
                + escape(table["label"], quote=True)
                + '"><table><caption>'
                + escape(table["label"])
                + "</caption><thead><tr>"
                + "".join('<th scope="col">' + escape(str(column)) + "</th>" for column in columns)
                + "</tr></thead><tbody>"
            )
            for row in rows:
                parts.append(
                    "<tr>"
                    + "".join("<td>" + escape(str(value)) + "</td>" for value in row)
                    + "</tr>"
                )
            parts.append("</tbody></table></div>")
        if chapter.get("mathematical_conclusion"):
            parts.append(
                '<p class="math-input"><strong>Result.</strong> '
                + escape(chapter["mathematical_conclusion"])
                + "</p>"
            )
        parts.append("</section>")
    if chapter.get("module_ids"):
        module_numbers = {}
        for number, module in enumerate((inventory or {}).get("modules", []), start=1):
            identity = module["identity"]
            module_numbers[identity.get("id") or identity.get("symbol")] = number
        parts.append("<section><h2>Modules exercised by this consumer</h2><ul>")
        for module_id in chapter["module_ids"]:
            number = module_numbers[module_id]
            parts.append(
                f'<li><a href="module-catalogue.html#module-{number}"><code>{escape(module_id)}</code></a></li>'
            )
        parts.append("</ul></section>")
    if chapter.get("status") == "ready":
        parts.append('<section class="lesson-reproduction"><h2>Reproduce this result</h2>')
        parts.append(
            '<details class="lesson-input-details"><summary>Full input description and JSON</summary><p>'
            + escape(chapter["mathematical_input"])
            + '</p><p><a href="chapter-manifest.json">Open the structured chapter manifest JSON</a></p></details>'
        )
        parts.append(
            '<h3>Command</h3><pre tabindex="0" role="region" aria-label="Copyable command"><code>'
            + escape(chapter["command"])
            + "</code></pre>"
        )
        parts.append(
            '<h3>Expected output</h3><pre tabindex="0" role="region" aria-label="Expected visible output"><code>'
            + escape(chapter["expected_output"])
            + "</code></pre>"
        )
        parts.append(
            f"<p><strong>Intermediate geometry.</strong> {escape(chapter['intermediate_geometry'])}</p>"
        )
        parts.append(
            f"<p><strong>Support limits.</strong> {escape(chapter['support_limits'])}</p></section>"
        )
    if chapter.get("records"):
        parts.append("<section><h2>Source records</h2><ul>")
        for record in chapter["records"]:
            parts.append(
                '<li><a style="overflow-wrap:anywhere" href="'
                + escape(record["href"], quote=True)
                + '">'
                + escape(record["label"])
                + "</a></li>"
            )
        parts.append("</ul></section>")
    if chapter.get("figure_ids"):
        figures = {item["id"]: item for item in (figure_index or {}).get("figures", [])}
        parts.append("<section><h2>Recorded figures</h2><ul>")
        for figure_id in chapter["figure_ids"]:
            figure = figures[figure_id]
            label = figure.get("title") or figure_id
            if figure.get("availability") == "ready":

                def site_href(href: str) -> str:
                    return href if href.startswith(("https://", "http://", "/")) else "../" + href

                parts.append(
                    '<li><a href="'
                    + escape(site_href(figure["href"]), quote=True)
                    + '">'
                    + escape(label)
                    + "</a>"
                )
                scopes = figure.get("layer_scopes", [])
                missing = figure.get("missing_layers", [])
                if scopes:
                    parts.append(
                        "<p><strong>Included scopes.</strong> "
                        + escape("; ".join(scopes))
                        + ".</p>"
                    )
                if missing:
                    parts.append(
                        "<p><strong>Missing layers.</strong> "
                        + escape("; ".join(missing))
                        + ".</p>"
                    )
                assets = [
                    ("Plotted coordinates", figure.get("plotted_data_href")),
                    ("SVG", figure.get("svg_href")),
                    ("PNG", figure.get("png_href")),
                ]
                links = [(name, site_href(href)) for name, href in assets if href]
                if links:
                    parts.append(
                        "<p>"
                        + " · ".join(
                            '<a href="' + escape(href, quote=True) + '">' + escape(name) + "</a>"
                            for name, href in links
                        )
                        + "</p>"
                    )
                parts.append("</li>")
            else:
                parts.append(
                    "<li>"
                    + escape(label)
                    + ' <span class="chapter-state">'
                    + escape(figure.get("reason", "Figure is not published."))
                    + "</span></li>"
                )
        parts.append("</ul></section>")
    parts.append('<section class="lesson-trace"><h2>Sources and checks</h2>')
    parts.append(
        "<p><strong>Evidence class.</strong> "
        + escape(role_label)
        + "; content kind: "
        + escape(chapter["kind"])
        + ". The support limits above define what this lesson does and does not establish.</p>"
    )
    parts.append("<h3>Repository source paths</h3><ul>")
    for source in chapter["example_sources"]:
        parts.append(
            '<li><a href="'
            + escape(_repository_href(source), quote=True)
            + '"><code>'
            + escape(source)
            + "</code></a></li>"
        )
    parts.append("</ul><h3>Verification paths</h3><ul>")
    check_paths = {"tests/reporting/test_learning_book.py"}
    check_paths.update(
        source for source in chapter["example_sources"] if source.startswith("tests/")
    )
    modules_by_id = {
        module["identity"].get("id") or module["identity"].get("symbol"): module
        for module in (inventory or {}).get("modules", [])
    }
    chapter_modules = [modules_by_id[module_id] for module_id in chapter.get("module_ids", [])]
    check_paths.update(_module_test_declarations(chapter_modules))
    for check_path in sorted(check_paths):
        parts.append(
            '<li><a href="'
            + escape(_repository_href(check_path), quote=True)
            + '"><code>'
            + escape(check_path)
            + "</code></a></li>"
        )
    parts.append(
        "</ul><p>The learning-book test checks lesson structure and links; it is not a numerical "
        "algorithm verifier.</p></section>"
    )
    previous = chapter.get("previous")
    following = chapter.get("next")
    by_id = {item["id"]: item for item in chapters}
    prev_item = (by_id[previous]["title"], f"{previous}.html") if previous else None
    next_item = (by_id[following]["title"], f"{following}.html") if following else None
    parts.append(site_design.lesson_neighbors(prev_item, next_item))
    parts.append(site_design.page_end())
    return "".join(parts)


def _module_catalogue_page(manifest: dict, inventory: dict) -> str:
    page = [
        site_design.page_start(
            "Module inventory and lesson evidence",
            stylesheet_href="../examples/examples.css",
            crumbs=[
                ("Learn", "../index.html"),
                ("Learning book", "index.html"),
                ("Module inventory", "module-catalogue.html"),
            ],
            main_class="page-content learning-reference",
            current_href="module-catalogue.html",
        )
    ]
    page.extend(
        [
            '<p class="eyebrow">Generated reference</p><h1>Module inventory and lesson evidence</h1>',
            "<p>The inventory lists declared method identities, roles, inputs and outputs, implementation paths, build requirements, assurance and set relations. "
            "A <code>registered_provider</code> is an adapter at a typed seam; direct-function and representation entries are not presented as interchangeable providers. "
            "A chapter claims a module only when its manifest links an executable installed consumer source. An entry without a chapter link is reference-only in this book. "
            '<a href="module-inventory.json">Open the machine-readable inventory</a>.</p>',
        ]
    )
    chapter_links = {}
    for chapter in manifest["chapters"]:
        for module_id in chapter.get("module_ids", []):
            chapter_links.setdefault(module_id, []).append(chapter)
    page.append('<ol class="module-catalogue">')
    for number, module in enumerate(inventory["modules"], start=1):
        identity = module["identity"]
        module_id = identity.get("id") or identity.get("symbol")
        title = module.get("role", module.get("group", "Module"))
        display_name = (
            source_index_names.display_name_for_identity(module_id) if module_id else None
        )
        heading = (
            f"{escape(display_name)} <code>{escape(module_id)}</code>"
            if display_name
            else f"<code>{escape(module_id)}</code>"
        )
        page.append(f'<li id="module-{number}"><h2>{heading}</h2>')
        page.append(
            f"<p><strong>Topic.</strong> {escape(str(module.get('group', 'unspecified')))}. "
            f"<strong>Entry kind.</strong> <code>{escape(str(module.get('kind', 'unspecified')))}</code>. "
            f"<strong>Role.</strong> {escape(str(title))}. "
            f"<strong>Build.</strong> {escape(str(module.get('build', 'unspecified')))}.</p>"
        )
        source = module.get("source", {}).get("path")
        if source:
            page.append(
                "<p><strong>Declared source path.</strong> "
                f'<a href="{escape(_repository_href(source), quote=True)}"><code>{escape(source)}</code></a>.</p>'
            )
        page.append(
            f"<p><strong>Input → output.</strong> <code>{escape(str(module.get('input', 'unspecified')))}</code> "
            f"→ <code>{escape(str(module.get('output', 'unspecified')))}</code>. "
            f"<strong>Dimension.</strong> {escape(str(module.get('dimension', 'unspecified')))}. "
            f"<strong>Assurance.</strong> {escape(str(module.get('assurance', 'unspecified')))}. "
            f"<strong>Relation.</strong> {escape(str(module.get('relation', 'unspecified')))}.</p>"
        )
        interface, interface_path, interface_note = _module_interface(module)
        page.append(
            "<p><strong>Actual interface or route.</strong> "
            f'<a href="{escape(_repository_href(interface_path), quote=True)}"><code>{escape(interface)}</code></a>. '
            f"{escape(interface_note)}</p>"
        )
        operations = module.get("operations", [])
        dependencies = module.get("dependencies", [])
        if operations or dependencies:
            page.append(
                "<p><strong>Operations.</strong> "
                + escape("; ".join(str(item) for item in operations) or "none declared")
                + ". <strong>Dependencies.</strong> "
                + escape("; ".join(str(item) for item in dependencies) or "none declared")
                + ".</p>"
            )
        test_declarations = _module_test_declarations([module])
        if test_declarations:
            page.append(
                "<p><strong>Focused test declarations.</strong> "
                + "; ".join(
                    '<a href="'
                    + escape(_repository_href(path), quote=True)
                    + '"><code>'
                    + escape(path)
                    + "</code></a>"
                    for path in test_declarations
                )
                + ".</p>"
            )
        else:
            page.append(
                "<p><strong>Focused tests.</strong> No module-owned C++ test declaration was resolved; "
                "the linked chapter and its source-specific checks define the available evidence.</p>"
            )
        linked = chapter_links.get(module_id, [])
        if linked:
            page.append(
                "<p><strong>Executable lesson.</strong> "
                + ", ".join(
                    f'<a href="{escape(chapter["id"])}.html">{escape(chapter["title"])}</a>'
                    for chapter in linked
                )
                + ".</p>"
            )
        else:
            page.append(
                "<p>Reference-only in this book. No chapter claims that a consumer example executes this module.</p>"
            )
        page.append("</li>")
    page.append("</ol>")
    page.append(site_design.page_end())
    return "".join(page)


def build(
    site: Path, manifest_path: Path = MANIFEST, figure_index_path: Path | None = None
) -> dict:
    manifest = _read_json(manifest_path)
    inventory = _read_json(INVENTORY)
    figures = (
        _read_json(figure_index_path) if figure_index_path and figure_index_path.is_file() else None
    )
    chapters = validate(manifest, inventory, figures)
    site_files: dict[str, bytes] = {}
    links: dict[str, str] = {}
    for chapter in chapters:
        source = CHAPTER_ROOT / chapter["source"]
        markup = source.read_text(encoding="utf-8")
        site_files[f"{BOOK_PATH}/{chapter['id']}.html"] = _chapter_page(
            chapter, chapters, markup, figures, inventory
        ).encode("utf-8")
        links[chapter["id"]] = (
            '<li class="book-chapter"><span class="chapter-state">'
            + escape(chapter["status_label"])
            + '</span> <a href="'
            + escape(f"{chapter['id']}.html", quote=True)
            + '">'
            + escape(chapter["title"])
            + "</a><p>"
            + escape(chapter["summary"])
            + "</p></li>"
        )
    groups = []
    for group in manifest["groups"]:
        entries = [chapter for chapter in chapters if chapter["group"] == group["id"]]
        if not entries:
            continue
        groups.append(
            "<section><h2>"
            + escape(group["label"])
            + "</h2><ol>"
            + "".join(links[chapter["id"]] for chapter in entries)
            + "</ol></section>"
        )
    page = [
        site_design.page_start(
            manifest["title"],
            stylesheet_href="../examples/examples.css",
            crumbs=[("Learn", "../index.html"), ("Learning book", "index.html")],
            main_class="page-content learning-book",
            current_href="index.html",
        )
    ]
    page.extend(
        [
            '<p class="eyebrow">Progressive guide</p><h1>',
            escape(manifest["title"]),
            '</h1><p class="lede">',
            escape(manifest["intro"]),
            "</p>",
        ]
    )
    page.extend(groups)
    page.append(
        '<p><a href="module-catalogue.html">Browse the module inventory and lesson evidence</a></p>'
    )
    page.append(
        '<p><a href="model-tracks.html">Compare system formulations and model tracks</a></p>'
    )
    page.append('<p><a href="../index.html">Return to the examples and reports</a></p>')
    page.append(site_design.page_end())
    site_files[f"{BOOK_PATH}/index.html"] = "".join(page).encode("utf-8")
    site_files[f"{BOOK_PATH}/chapter-manifest.json"] = (
        json.dumps({"schema": manifest["schema"], "chapters": chapters}, indent=2).encode("utf-8")
        + b"\n"
    )
    site_files[f"{BOOK_PATH}/module-inventory.json"] = (
        json.dumps(inventory, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    site_files[f"{BOOK_PATH}/module-catalogue.html"] = _module_catalogue_page(
        manifest, inventory
    ).encode("utf-8")
    site_files[f"{BOOK_PATH}/model-tracks.html"] = _model_tracks_page(chapters, figures).encode(
        "utf-8"
    )
    if figures:
        site_files["examples/closed-loop/figure-index.json"] = (
            json.dumps(figures, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        for entry in figures["figures"]:
            if entry["availability"] != "ready":
                continue
            for field in ("href", "plotted_data_href", "svg_href", "png_href"):
                href = entry.get(field)
                if not href:
                    continue
                if not href.startswith("examples/closed-loop/"):
                    raise ValueError(f"figure {entry['id']} has a non-local asset route in {field}")
                source = ROOT / "docs" / href
                if source.is_symlink() or not source.is_file():
                    raise ValueError(f"figure {entry['id']} is missing source asset {href}")
                site_files[href] = source.read_bytes()
    campaign_id = "examples/closed-loop/campaign-2026-11-18"
    campaign_source = ROOT / "docs" / campaign_id
    campaign_manifest = campaign_source / "provenance-manifest.json"
    campaign_sidecar = campaign_manifest.with_suffix(".json.sha256")
    if campaign_manifest.is_file() and not campaign_manifest.is_symlink():
        manifest_bytes = campaign_manifest.read_bytes()
        manifest = json.loads(manifest_bytes)
        expected_sidecar = (
            f"{hashlib.sha256(manifest_bytes).hexdigest()}  {campaign_manifest.name}\n"
        )
        if (
            campaign_sidecar.is_symlink()
            or campaign_sidecar.read_text(encoding="utf-8") != expected_sidecar
        ):
            raise ValueError(
                "full-profile campaign publication manifest hash is missing or invalid"
            )
        expected_files = manifest.get("files_sha256")
        if not isinstance(expected_files, dict):
            raise ValueError("full-profile campaign manifest has no file hash map")
        actual_files = {
            path.relative_to(campaign_source).as_posix()
            for path in campaign_source.rglob("*")
            if path.is_file() and path not in {campaign_manifest, campaign_sidecar}
        }
        if actual_files != set(expected_files):
            raise ValueError("full-profile campaign files differ from the publication manifest")
        campaign_root = campaign_source.resolve()
        for relative, expected_digest in expected_files.items():
            relative_path = Path(relative)
            source = campaign_source / relative_path
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or source.is_symlink()
                or not source.is_file()
                or not source.resolve().is_relative_to(campaign_root)
            ):
                raise ValueError(f"unsafe full-profile campaign asset: {relative}")
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected_digest:
                raise ValueError(f"full-profile campaign asset hash differs: {relative}")
            site_files[f"{campaign_id}/{relative}"] = source.read_bytes()
        site_files[f"{campaign_id}/provenance-manifest.json"] = manifest_bytes
        site_files[f"{campaign_id}/provenance-manifest.json.sha256"] = campaign_sidecar.read_bytes()
    replace_existing = frozenset(path for path in site_files if (Path(site) / path).exists())
    plan = site_additions.prepare(site, site_files, replace_existing=replace_existing)
    site_additions.commit(plan)
    return {
        "chapters": len(chapters),
        "ready": sum(c["status"] == "ready" for c in chapters),
        "pending": sum(c["status"] == "pending" for c in chapters),
        "modules": len(_module_ids(inventory)),
        "path": str(Path(site) / BOOK_PATH),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--figure-index", type=Path)
    args = parser.parse_args()
    result = build(args.site, args.manifest, args.figure_index)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
