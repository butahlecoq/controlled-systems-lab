"""Stage the immutable PERF-03 HTML evidence bundle into the reviewed Pages site."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


BUNDLE_NAME = "perf03-ts01-single-process-correlation-20261014"
PREFIX = BUNDLE_NAME + "-"
FILES = frozenset({
    "README.md", "SHA256SUMS.txt", "harness-change.patch", "index.html",
    "paired-timings.csv", "profile-summary.json", "profile-symbols.csv", "verify.py",
})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class LocalLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.external_resources = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attr in ("href", "src"):
            value = values.get(attr)
            if value:
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc or value.startswith("//"):
                    self.external_resources = True
                else:
                    self.links.append(parsed.path)
        require(not any(key.lower().startswith("on") for key, _ in attrs), "active HTML event handler")


def validate(source: Path) -> tuple[str, dict[str, bytes]]:
    require(source.name == BUNDLE_NAME and source.is_dir() and not source.is_symlink(),
            "unexpected PERF-03 source bundle")
    require({path.name for path in source.iterdir()} == FILES, "PERF-03 file inventory differs")
    contents: dict[str, bytes] = {}
    for name in sorted(FILES):
        path = source / name
        require(path.is_file() and not path.is_symlink(), "missing or linked PERF-03 file: " + name)
        contents[name] = path.read_bytes()
    manifest = contents["SHA256SUMS.txt"].decode("ascii")
    recorded: dict[str, str] = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "malformed PERF-03 SHA256SUMS entry")
        digest, name = match.groups()
        require(name not in recorded, "duplicate PERF-03 manifest entry")
        recorded[name] = digest
    require(set(recorded) == FILES - {"SHA256SUMS.txt"}, "PERF-03 manifest inventory differs")
    for name, expected in recorded.items():
        require(hashlib.sha256(contents[name]).hexdigest() == expected, "PERF-03 hash mismatch: " + name)
    summary = json.loads(contents["profile-summary.json"])
    require(summary.get("identity", {}).get("source_commit") == "2a5ab835295dfd22f02b19d440bb8158267d985a",
            "PERF-03 pinned source differs")
    require(summary.get("paired_execution", {}).get("assessment", "").startswith("Inconclusive"),
            "PERF-03 timing result must remain inconclusive")
    require("local" in summary.get("profiler", {}).get("trace", {}).get("raw_etl_and_stack_html", "").lower(),
            "PERF-03 local-only ETL limitation missing")
    parser = LocalLinks()
    parser.feed(contents["index.html"].decode("utf-8"))
    require(not parser.external_resources, "PERF-03 HTML must be self-contained")
    require(parser.links and all(link in FILES for link in parser.links), "PERF-03 HTML link escapes bundle")
    route_hash = hashlib.sha256(contents["SHA256SUMS.txt"]).hexdigest()[:16]
    return PREFIX + route_hash, contents


def stage(source: Path, site_dir: Path) -> str:
    route, contents = validate(source)
    require(site_dir.is_dir() and not site_dir.is_symlink(), "staged site directory is missing")
    index_path = site_dir / "index.html"
    require(index_path.is_file() and not index_path.is_symlink(), "staged site index is missing")
    destination = site_dir / route
    require(not destination.exists() and not destination.is_symlink(), "immutable PERF-03 route already exists")
    index = index_path.read_text(encoding="utf-8")
    require(index.count("</ul>") == 1 and route not in index, "Pages index insertion point differs")
    destination.mkdir()
    for name, content in contents.items():
        (destination / name).write_bytes(content)
    row = (f'<li><a href="{route}/index.html">{route}</a> — PERF-03 T-S01 process-scoped profile; '
           f'<a href="{route}/profile-summary.json">profile JSON</a> · '
           f'<a href="{route}/paired-timings.csv">paired timings CSV</a> · '
           f'<a href="{route}/profile-symbols.csv">symbol CSV</a></li>')
    index_path.write_text(index.replace("</ul>", row + "</ul>"), encoding="utf-8", newline="\n")
    staged_parser = LocalLinks()
    staged_parser.feed((destination / "index.html").read_text(encoding="utf-8"))
    require(not staged_parser.external_resources and all((destination / link).is_file() for link in staged_parser.links),
            "staged PERF-03 page has missing or external links")
    return route


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    print(stage(args.source, args.site))


if __name__ == "__main__":
    main()
