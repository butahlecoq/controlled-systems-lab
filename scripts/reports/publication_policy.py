"""Small registry for schema-v3 publication adapters."""
from __future__ import annotations

from dataclasses import dataclass
import re
from types import ModuleType


@dataclass(frozen=True)
class PublicationPolicy:
    kind: str
    source_pattern: str
    publisher: ModuleType
    native_digest: bool = False
    svg_files: tuple[str, ...] = ()
    generated_svg: bool = False
    extra_html_files: tuple[str, ...] = ()
    include_source_evidence: bool = False
    include_parent_archive: bool = False
    extra_page_files: tuple[str, ...] = ()
    committed_archive: bool = False
    adapt_allow_test: bool = False
    render_allow_test: bool = False
    archive_allow_test: bool = False
    raw_json_link: bool = True
    csv_name: str = "trials.csv"
    trial_label: str = "Measured tables"
    figure_name: str = ""
    extra_links: tuple[tuple[str, str], ...] = ()

    def accepts_source_id(self, source_id: object) -> bool:
        return isinstance(source_id, str) and re.fullmatch(self.source_pattern, source_id) is not None


_POLICIES: dict[str, PublicationPolicy] = {}


def register(policy: PublicationPolicy) -> PublicationPolicy:
    if policy.kind in _POLICIES:
        raise ValueError(f"duplicate publication kind registration: {policy.kind}")
    _POLICIES[policy.kind] = policy
    return policy


def for_kind(kind: str) -> PublicationPolicy:
    try:
        return _POLICIES[kind]
    except KeyError as error:
        raise ValueError(f"unsupported registered publication kind: {kind}") from error


def registered_kinds() -> frozenset[str]:
    return frozenset(_POLICIES)


def maybe_for_kind(kind: str) -> PublicationPolicy | None:
    return _POLICIES.get(kind)
