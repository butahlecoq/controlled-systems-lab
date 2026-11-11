"""Shared HTML framing for mutable learning and report companion pages."""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
STYLE = ROOT / "docs/examples/examples.css"


def stylesheet() -> bytes:
    """Return the one stylesheet staged beside the mutable examples."""
    return STYLE.read_bytes()


def stylesheet_link(href: str = "examples.css") -> str:
    return '<link rel="stylesheet" href="' + escape(href, quote=True) + '">'


def focusable_code_blocks(markup: str, label: str = "Scrollable code example") -> str:
    """Make each horizontally scrollable pre block keyboard reachable and named."""
    escaped_label = escape(label, quote=True)
    index = 0

    def add_focus(match: re.Match[str]) -> str:
        nonlocal index
        index += 1
        opening, body = match.group(1) or "", match.group(2)
        name = escaped_label if index == 1 else f"{escaped_label} {index}"
        attributes = opening
        if re.search(r"\btabindex\s*=", attributes, flags=re.IGNORECASE):
            attributes = re.sub(r"\btabindex\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
                                'tabindex="0"', attributes, flags=re.IGNORECASE)
        else:
            attributes += ' tabindex="0"'
        if not re.search(r"\brole\s*=", attributes, flags=re.IGNORECASE):
            attributes += ' role="region"'
        if not re.search(r"\baria-label\s*=", attributes, flags=re.IGNORECASE):
            attributes += f' aria-label="{name}"'
        return f'<pre{attributes}>{body}</pre>'

    return re.sub(r"<pre(\s[^>]*)?>(.*?)</pre>",
                  lambda match: add_focus(match), markup, flags=re.IGNORECASE | re.DOTALL)


def code_block(content: str, label: str) -> str:
    """Render a named code region that keyboard users can scroll."""
    return (f'<pre tabindex="0" role="region" aria-label="{escape(label, quote=True)}">'
            f'<code>{escape(content)}</code></pre>')


def breadcrumbs(items: Iterable[tuple[str, str]], *, current_href: str | None = None) -> str:
    """Render named route steps; the final item is the current page."""
    links = list(items)
    parts = ['<nav class="breadcrumbs" aria-label="Breadcrumb"><ol>']
    for index, (label, href) in enumerate(links):
        if index == len(links) - 1:
            current = escape(label)
            if current_href is not None:
                current = '<a href="' + escape(current_href, quote=True) + '">' + current + '</a>'
            parts.append('<li aria-current="page">' + current + '</li>')
        else:
            parts.append('<li><a href="' + escape(href, quote=True) + '">' + escape(label) + '</a></li>')
    parts.append('</ol></nav>')
    return ''.join(parts)


def lesson_neighbors(previous: tuple[str, str] | None,
                     following: tuple[str, str] | None) -> str:
    """Render accessible previous/next topic links where a sequence exists."""
    if previous is None and following is None:
        return ''
    parts = ['<nav class="lesson-neighbors" aria-label="Lesson navigation">']
    if previous is None:
        parts.append('<span></span>')
    else:
        label, href = previous
        parts.append('<a rel="prev" href="' + escape(href, quote=True) + '"><span>Previous</span>'
                     '<strong>' + escape(label) + '</strong></a>')
    if following is None:
        parts.append('<span></span>')
    else:
        label, href = following
        parts.append('<a rel="next" href="' + escape(href, quote=True) + '"><span>Next</span>'
                     '<strong>' + escape(label) + '</strong></a>')
    parts.append('</nav>')
    return ''.join(parts)


def page_start(title: str, *, stylesheet_href: str | None = None,
               crumbs: Iterable[tuple[str, str]] = (), main_class: str = "page-content",
               current_href: str | None = None) -> str:
    """Start a responsive standalone page using the shared site appearance."""
    escaped_title = escape(title)
    nav = breadcrumbs(crumbs, current_href=current_href) if crumbs else ''
    stylesheet_tag = (stylesheet_link(stylesheet_href) if stylesheet_href is not None
                      else '<style>\n' + stylesheet().decode("utf-8") + '\n</style>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escaped_title + '</title>'
            + stylesheet_tag + '</head><body><a class="skip" href="#main">Skip to content</a>'
            '<main id="main" class="' + escape(main_class, quote=True) + '">' + nav)


def page_end(neighbors: str = "") -> str:
    return neighbors + '</main></body></html>'
