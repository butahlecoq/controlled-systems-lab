"""Build the progressive learning book from its authored chapter manifest."""

from __future__ import annotations

import argparse
import ast
from html import escape
import json
from pathlib import Path
import re
import sys

try:
    import site_design
    import site_additions
    import mathematical_notation
except ModuleNotFoundError as error:
    if error.name not in {"site_design", "site_additions", "mathematical_notation"}:
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import site_design
    import site_additions
    import mathematical_notation


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/catalogue/learning-book-v1.json"
INVENTORY = ROOT / "docs/catalogue/module-composition-inventory-v1.json"
CHAPTER_ROOT = ROOT / "docs/examples/learning/chapters"
BOOK_PATH = "learn"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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
    parts.append(f'<p class="learning-status">{escape(chapter["status_label"])}</p>')
    parts.append(chapter_html)
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
            "<p>The inventory lists declared module contracts. A chapter claims a module only when it links to an executable installed consumer source. An inventory entry without a lesson link is reference-only in this book.</p>",
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
        page.append(f'<li id="module-{number}"><h2><code>{escape(module_id)}</code></h2>')
        page.append(
            f"<p><strong>Inventory group.</strong> {escape(str(module.get('group', 'unspecified')))}. "
        )
        page.append(f"<strong>Role.</strong> {escape(str(title))}.</p>")
        page.append(
            f"<p><strong>Input.</strong> <code>{escape(str(module.get('input', 'unspecified')))}</code>. "
        )
        page.append(
            f"<strong>Output.</strong> <code>{escape(str(module.get('output', 'unspecified')))}</code>.</p>"
        )
        source = module.get("source", {}).get("path")
        if source:
            page.append(
                f"<p><strong>Implementation source.</strong> <code>{escape(source)}</code>.</p>"
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
