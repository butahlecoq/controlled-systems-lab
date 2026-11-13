"""Check maintained HTML mathematics and exact historical-route exemptions."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

REGISTRY = Path(__file__).with_name("mathematical-presentation-routes.json")
ROOT = Path(__file__).resolve().parents[2]
NESTED_NUMBERS = re.compile(r"\[\s*\[\s*[+−\-\d.]")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}


class PresentationParser(HTMLParser):
    def __init__(self, exempt_ids: set[str]):
        super().__init__()
        self.exempt_ids = exempt_ids
        self.stack: list[dict] = []
        self.findings: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        attributes = dict(attrs)
        secondary = bool(self.stack and self.stack[-1]["secondary"])
        secondary |= tag in {"script", "style", "template"}
        secondary |= tag == "details" and "open" not in attributes
        secondary |= attributes.get("id") in self.exempt_ids
        secondary |= "lesson-reproduction" in attributes.get("class", "").split()
        self.stack.append({"tag": tag, "secondary": secondary,
                           "line": self.getpos()[0], "text": [], "rows": [], "cells": [],
                           "caption": ""})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.stack and self.stack[-1]["secondary"]:
            return
        for node in self.stack:
            node["text"].append(data)
        if NESTED_NUMBERS.search(data):
            self.add("numeric-nested-list", self.getpos()[0],
                     "Render this numeric array as a labelled matrix/set; keep exact data secondary.")

    def add(self, kind, line, message):
        finding = {"kind": kind, "line": line, "message": message}
        if finding not in self.findings:
            self.findings.append(finding)

    def close(self):
        super().close()
        while self.stack:
            self.handle_endtag(self.stack[-1]["tag"])

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1)
                      if self.stack[i]["tag"] == tag), None)
        if index is None:
            return
        node = self.stack[index]
        del self.stack[index:]
        if node["secondary"]:
            return
        text = "".join(node["text"]).strip()
        if tag in {"p", "pre", "code", "td", "th", "li", "dd", "div"}:
            if NESTED_NUMBERS.search(text):
                self.add("numeric-nested-list", node["line"],
                         "Render this numeric array as a labelled matrix/set; keep exact data secondary.")
        if tag == "pre":
            try:
                value = json.loads(text)
            except ValueError:
                value = None
            if isinstance(value, (dict, list)):
                self.add("primary-json", node["line"],
                         "Move exact JSON into closed data details or a source-owned reference section.")
        if tag in {"td", "th"}:
            row = next((parent for parent in reversed(self.stack) if parent["tag"] == "tr"), None)
            if row is not None:
                row["cells"].append(text)
        if tag == "tr":
            table = next((parent for parent in reversed(self.stack)
                          if parent["tag"] == "table"), None)
            if table is not None:
                table["rows"].append(node["cells"])
        if tag == "caption":
            table = next((parent for parent in reversed(self.stack)
                          if parent["tag"] == "table"), None)
            if table is not None:
                table["caption"] = text
        if tag == "table" and len(node["rows"]) >= 3:
            headers, *rows = node["rows"]
            normalized = [header.casefold().strip() for header in headers]
            if "coordinates" in normalized or re.search(r"\bcoordinates\b", node["caption"], re.I):
                for column, header in enumerate(normalized):
                    if header in {"meaning", "role"}:
                        values = [row[column] for row in rows if len(row) > column]
                        if len(values) >= 2 and len(set(values)) == 1 and values[0]:
                            self.add("constant-coordinate-role", node["line"],
                                     "Remove the repeated coordinate role column; put full points/IDs "
                                     "in closed data details and show the mathematical result first.")


def inspect_html(source: str, exempt_ids: set[str] | None = None) -> list[dict]:
    parser = PresentationParser(exempt_ids or set())
    parser.feed(source)
    parser.close()
    return parser.findings


def local_route(base: str, href: str) -> str | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    route = posixpath.normpath(posixpath.join(base, parsed.path))
    if route.startswith(("../", "/")):
        raise ValueError("presentation route escapes site root: " + href)
    return route if route.endswith(".html") else None


def discovered_routes(site: Path) -> set[str]:
    """Use producer inventories, so a newly emitted lesson cannot bypass classification."""
    routes: set[str] = set()
    gallery = site / "examples/visual-coverage.json"
    if gallery.is_file():
        routes.add("examples/index.html")
        for entry in json.loads(gallery.read_text())["entries"]:
            for key in ("page", "walkthrough_page"):
                if key in entry:
                    route = local_route("examples", entry[key])
                    if route:
                        routes.add(route)
    manifest = site / "learn/chapter-manifest.json"
    if manifest.is_file():
        routes.update({"learn/index.html", "learn/module-catalogue.html"})
        for chapter in json.loads(manifest.read_text())["chapters"]:
            route = local_route("learn", chapter["id"] + ".html")
            if route:
                routes.add(route)
    figures = site / "examples/closed-loop/figure-index.json"
    if figures.is_file():
        for figure in json.loads(figures.read_text())["figures"]:
            if figure.get("availability") == "ready":
                route = local_route("", figure["href"])
                if route:
                    routes.add(route)
    return routes


def declared_source_routes(repository_root: Path) -> dict[str, list[str]]:
    """Read current producer declarations even when a preview predates their staging."""
    if __package__:
        from . import pages_route_retirement
    else:
        import pages_route_retirement

    declarations = {
        **pages_route_retirement.EXAMPLE_ROUTE_PRODUCERS,
        **pages_route_retirement.STANDALONE_REPORT_ROUTE_PRODUCERS,
    }
    return {route: owners for route, owners in declarations.items()
            if route.endswith(".html")
            and all((repository_root / owner).is_file() for owner in owners)}


def audit_site(site: Path, ledger: dict, required_routes: set[str] | None = None,
               repository_root: Path | None = None) -> dict:
    site = site.resolve()
    entries = {entry["route"]: entry for entry in ledger["routes"]}
    findings = []
    for inventory in ledger.get("required_inventories", []):
        if not (site / inventory).is_file():
            findings.append({"route": inventory, "kind": "missing-inventory",
                             "message": "Composed-site producer inventory is required for route coverage."})
    if len(entries) != len(ledger["routes"]):
        findings.append({"route": "", "kind": "duplicate-route", "message": "Duplicate registry route."})
    source_routes = declared_source_routes(repository_root or ROOT) if (
        repository_root is not None or ledger.get("require_source_declared_routes")) else {}
    required = discovered_routes(site) | (required_routes or set()) | set(source_routes)
    actual = {str(path.relative_to(site)) for path in site.rglob("*.html") if path.is_file()}
    for route in sorted(required - actual):
        findings.append({"route": route, "kind": "missing-route",
                         "message": "Producer inventory requires this HTML page."})
    for route in sorted(actual | required):
        entry = entries.get(route)
        if not entry or not entry.get("owner"):
            findings.append({"route": route, "kind": "unclassified-route",
                             "message": "Register the source owner and maintained/frozen disposition."})
            continue
        if route not in actual:
            continue
        path = site / route
        if not path.resolve().is_relative_to(site):
            findings.append({"route": route, "kind": "escaping-route",
                             "message": "HTML symlink escapes site root."})
            continue
        content = path.read_bytes()
        if entry["disposition"] == "frozen":
            if not entry.get("witness") or hashlib.sha256(content).hexdigest() != entry.get("sha256"):
                findings.append({"route": route, "kind": "frozen-bytes-changed",
                                 "owner": entry["owner"],
                                 "message": "Historical HTML differs from its exact recorded witness; "
                                 "preserve it and revise the maintained companion."})
        elif entry["disposition"] == "maintained":
            for finding in inspect_html(content.decode("utf-8"), set(entry.get("reference_ids", []))):
                findings.append({"route": route, "owner": entry["owner"], **finding})
        else:
            findings.append({"route": route, "kind": "invalid-disposition",
                             "message": "Use maintained or frozen with an exact byte witness."})
    return {"schema": "csl.mathematical-presentation-audit/1", "passed": not findings,
            "html_pages": len(actual), "required_pages": len(required),
            "source_declared_pages": len(source_routes), "findings": findings}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if not args.site_root.is_dir():
        parser.error("--site-root must be an existing composed site directory")
    result = audit_site(args.site_root, json.loads(args.registry.read_text()))
    if args.json_output:
        args.json_output.write_text(json.dumps(result, indent=2) + "\n")
    for finding in result["findings"]:
        location = finding["route"] + (":" + str(finding["line"]) if "line" in finding else "")
        print(f"{location}: {finding['kind']}: {finding['message']}")
    print(f"Mathematical presentation: {'PASS' if result['passed'] else 'FAIL'}; "
          f"{result['html_pages']} HTML pages, {len(result['findings'])} findings")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
