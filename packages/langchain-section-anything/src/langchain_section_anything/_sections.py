"""Section Anything result -> one record (text and metadata) per section.

Shared by the LangChain and LlamaIndex integrations; the two copies are kept identical.

A section's text is the library's own body export (what ``section-anything --body`` prints): the
lines from its heading to the next section's heading, with running headers and footers removed,
the heading lines left out and the rest reflowed into paragraphs.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import section_anything
from section_anything.export import heading_text, markdown_hashes, section_bodies
from section_anything.structure import furniture_of


def section_options(opts: dict[str, Any]) -> dict[str, Any]:
    """Check pass-through options against `section_anything.section`'s own keyword options
    (api_key, base_url, model, max_usd, prices, over_budget, max_pages, extract_timeout, progress,
    settings), so a typo fails when the loader is built, not after a PDF is read."""
    params = inspect.signature(section_anything.asection).parameters.values()
    allowed = {p.name for p in params if p.kind is p.KEYWORD_ONLY}
    unknown = sorted(set(opts) - allowed)
    if unknown:
        raise TypeError(f"unknown option(s) {', '.join(unknown)}; section-anything accepts {', '.join(sorted(allowed))}")
    return dict(opts)


@dataclass
class SectionRecord:
    text: str
    metadata: dict[str, Any]
    parent: int | None  # position (in the returned list) of the nearest enclosing section, if any


def section_records(tree: Any, include_heading: bool = True) -> list[SectionRecord]:
    """One record per section of a `SectionTree`, in reading order.

    `heading_path` lists the headings from the outermost enclosing section down to this one
    (["3 Method", "3.1 Data"]); the document title and front matter are not part of it. With
    `include_heading`, the text starts with the heading as a Markdown line ("## 3.1 Data"), so
    joining all texts gives `tree.to_markdown(body=True)`. Without it, sections with no text of
    their own (a heading directly followed by a subheading) are skipped."""
    sections, resolved = tree.sections, tree.resolved
    bodies = section_bodies(tree.extraction, resolved, furniture_of(tree.extraction)) if resolved else []
    if len(bodies) != len(sections):  # pragma: no cover - the library returns both lists together
        raise ValueError("the section tree holds no extraction; call section_anything.section(...)")
    doc_title = next((heading_text(s) for s in sections if "doc_title" in s["flags"]), None)

    records: list[SectionRecord] = []
    path: list[tuple[int, str]] = []  # enclosing headings (level, heading)
    kept: list[tuple[int, int]] = []  # enclosing headings that have a record (level, position)
    for k, (sec, paras) in enumerate(zip(sections, bodies, strict=True)):
        flags = list(sec["flags"])
        heading = heading_text(sec)
        level = int(sec["level"] or 1)
        nested = "front_matter" not in flags and "doc_title" not in flags
        if nested:
            path = [p for p in path if p[0] < level]
            kept = [p for p in kept if p[0] < level]
            path.append((level, heading))
            heading_path = [h for _lv, h in path]
        else:
            heading_path = [heading] if "doc_title" in flags else []

        parts = list(paras)
        if include_heading and "front_matter" not in flags:
            parts.insert(0, f"{markdown_hashes(sec)} {heading}")
        text = "\n\n".join(parts)
        if not text.strip():
            continue
        parent = kept[-1][1] if nested and kept else None
        records.append(SectionRecord(text=text, parent=parent, metadata={
            "section_index": k,
            "title": sec["title"],
            "number": sec["number"],
            "level": sec["level"],
            "heading_path": heading_path,
            "page_start": sec["page_start"],
            "page_end": sec["page_end"],
            "start": sec["start"],
            "end": sec["end"],
            "flags": flags,
            "document_title": doc_title,
            "mode": tree.mode,
            "model": tree.model,
            "document_cost_usd": tree.cost_usd,
        }))
        if nested:
            kept.append((level, len(records) - 1))
    return records
