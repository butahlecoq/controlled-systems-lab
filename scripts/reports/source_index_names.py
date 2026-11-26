"""Load the canonical display names and compatibility aliases for legacy geometry."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
NAMES_PATH = ROOT / "docs/catalogue/source-index-geometry-names.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    """Return the documented name/alias map without changing any stable identity."""
    return json.loads(NAMES_PATH.read_text(encoding="utf-8"))


def _entry(section: str, key: str) -> dict[str, Any]:
    if section == "family":
        entry = load()[section]
        if key not in {entry["key"], "family"}:
            raise KeyError(f"unknown source-index geometry name: {section}/{key}")
    else:
        entry = next((item for item in load()[section] if item["key"] == key), None)
    if entry is None:
        raise KeyError(f"unknown source-index geometry name: {section}/{key}")
    return entry


def family() -> dict[str, Any]:
    return _entry("family", "family")


def routine(key: str) -> dict[str, Any]:
    return _entry("routines", key)


def example(key: str) -> dict[str, Any]:
    return _entry("examples", key)


def report_family(key: str) -> dict[str, Any]:
    return _entry("report_families", key)


def display_name(key: str) -> str:
    for section in ("routines", "examples", "report_families", "family"):
        try:
            return str(_entry(section, key)["display_name"])
        except KeyError:
            continue
    raise KeyError(f"unknown source-index geometry display name: {key}")


def display_name_for_identity(identity: str) -> str | None:
    """Resolve a stable provider ID or C++ symbol to its descriptive display name.

    Routine entries take precedence over the family entry because the family lists
    the routine provider IDs as a summary. A routine-level identity therefore keeps
    its more specific display name.
    """
    for entries in (load()["routines"], [load()["family"]]):
        for entry in entries:
            if (
                identity in entry.get("provider_ids", [])
                or identity in entry.get("public_symbols", [])
                or identity in entry.get("namespaces", [])
            ):
                return str(entry["display_name"])
    return None


def is_reducer_cli_alias(value: str) -> bool:
    return value in routine("kpabep")["cli_aliases"]
