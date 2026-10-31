"""Exports to Unstructured's element dicts and Docling's DoclingDocument, and their chunkers on them.

The structure tests need no extra package. The round trips skip unless `unstructured` or
`docling-core` (with semchunk, for `HybridChunker`) is installed; Docling's chunker runs with a
whitespace tokenizer, so no tokenizer model is downloaded.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from typing import Any

import pytest

import section_anything
from section_anything.api import SectionTree
from section_anything.errors import ConfigError
from section_anything.export import heading_text, section_bodies
from section_anything.structure import furniture_of

HEADINGS = ["A Study of Sectioning", "1 Introduction", "1.1 Scope", "2 Methods", "3 Results"]


def bodies_by_heading(tree: SectionTree) -> dict[str, list[str]]:
    paras = section_bodies(tree.extraction, tree.resolved, furniture_of(tree.extraction))
    return {heading_text(s): b for s, b in zip(tree.sections, paras, strict=True) if "front_matter" not in s["flags"]}


def docling_paths(tree: SectionTree) -> list[list[str]]:
    """Per heading, in order: the `meta.headings` Docling's chunkers give its section's text, the
    document title (a TitleItem, level 0 to Docling) first, then the section's `heading_path`."""
    title = next((heading_text(s) for s in tree.sections if "doc_title" in s["flags"]), None)
    return [[title, *s["heading_path"]] if title is not None and "doc_title" not in s["flags"] else list(s["heading_path"])
            for s in tree.sections if "front_matter" not in s["flags"]]


def hand_built_tree() -> SectionTree:
    def sec(number, title, level, page, flags=()):
        return {"number": number, "title": title, "level": level, "page_start": page, "page_end": page,
                "start": 0, "end": 1, "flags": list(flags)}

    return SectionTree(
        sections=[sec("", "Front matter", 1, 1, ["front_matter"]), sec("", "My Paper", 1, 1, ["doc_title"]),
                  sec("1", "Intro", 1, 1), sec("1.1", "Scope", 2, 2), sec("", "Deep", 7, 3)],
        mode="free", model=None, pages=3, usage={"calls": 0, "cost_usd": 0.0}, seconds=0.0,
    )


# -- Unstructured: structure, no package needed --------------------------------------------------


def test_unstructured_elements_follow_the_tree(paper_pdf):
    tree = section_anything.section(paper_pdf)
    els = tree.to_unstructured_elements()
    assert json.loads(json.dumps(els)) == els  # plain JSON
    assert tree.to_unstructured_elements() == els  # deterministic

    titles = [e for e in els if e["type"] == "Title"]
    assert [t["text"] for t in titles] == HEADINGS
    assert {e["type"] for e in els} == {"Title", "NarrativeText"}
    assert [t["metadata"]["category_depth"] for t in titles] == [0, 0, 1, 0, 0]
    assert [t["metadata"]["page_number"] for t in titles] == [1, 1, 1, 2, 2]
    ids = [e["element_id"] for e in els]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"[0-9a-f]{32}", i) for i in ids)

    # Parents: 1.1 Scope under 1 Introduction; top-level headings (and the title) have none.
    by_text = {t["text"]: t for t in titles}
    assert by_text["1.1 Scope"]["metadata"]["parent_id"] == by_text["1 Introduction"]["element_id"]
    assert [t["text"] for t in titles if "parent_id" not in t["metadata"]] == [h for h in HEADINGS if h != "1.1 Scope"]

    # Each paragraph sits under the Title before it, and the paragraphs are the section bodies.
    got: dict[str, list[str]] = {}
    current = None
    for e in els:
        if e["type"] == "Title":
            current = e
            got[e["text"]] = []
        else:
            assert e["metadata"]["parent_id"] == current["element_id"]
            assert "category_depth" not in e["metadata"]
            got[current["text"]].append(e["text"])
    assert got == bodies_by_heading(tree)
    assert all(e["metadata"]["filetype"] == "application/pdf" and "filename" not in e["metadata"] for e in els)


def test_unstructured_coordinates_are_on_the_page(paper_pdf):
    els = section_anything.section(paper_pdf).to_unstructured_elements()
    for e in els:
        c = e["metadata"]["coordinates"]
        assert c["system"] == "PixelSpace" and (c["layout_width"], c["layout_height"]) == (612.0, 792.0)
        (x0, top), (_, bottom), (x1, _), _ = c["points"]
        assert 0 <= x0 < x1 <= 612 and 0 <= top < bottom <= 792
    intro = next(i for i, e in enumerate(els) if e["text"] == "1 Introduction")
    head, para = els[intro]["metadata"]["coordinates"]["points"], els[intro + 1]["metadata"]["coordinates"]["points"]
    assert head[1][1] <= para[0][1]  # the heading's bottom is above its paragraph's top (y grows down)


def test_unstructured_filename(paper_pdf):
    tree = section_anything.section(paper_pdf)
    els = tree.to_unstructured_elements(paper_pdf)
    assert {e["metadata"]["filename"] for e in els} == {"paper.pdf"}
    assert {e["metadata"]["file_directory"] for e in els} == {str(paper_pdf.parent)}
    first = els[0]  # Unstructured's own id: sha256(filename, text, page, position on the page)[:32]
    assert first["element_id"] == hashlib.sha256(b"paper.pdfA Study of Sectioning10").hexdigest()[:32]
    assert len({e["element_id"] for e in els}) == len(els)


def test_unstructured_front_matter_has_no_title(front_matter_pdf):
    tree = section_anything.section(front_matter_pdf)
    assert "front_matter" in tree.sections[0]["flags"]
    els = tree.to_unstructured_elements()
    assert [e["text"] for e in els if e["type"] == "Title"] == ["1 Introduction", "2 Methods"]
    first_title = next(i for i, e in enumerate(els) if e["type"] == "Title")
    assert first_title > 0
    assert all(e["type"] == "NarrativeText" and "parent_id" not in e["metadata"] for e in els[:first_title])


def test_exports_without_extraction_have_headings_only():
    els = hand_built_tree().to_unstructured_elements()
    assert [(e["type"], e["text"], e["metadata"]["category_depth"], e["metadata"]["page_number"]) for e in els] == [
        ("Title", "My Paper", 0, 1), ("Title", "1 Intro", 0, 1), ("Title", "1.1 Scope", 1, 2), ("Title", "Deep", 6, 3),
    ]
    assert els[2]["metadata"]["parent_id"] == els[1]["element_id"]
    assert els[3]["metadata"]["parent_id"] == els[2]["element_id"]
    assert all("coordinates" not in e["metadata"] for e in els)


def test_docling_extra_missing(monkeypatch):
    for name in ("docling_core", "docling_core.types", "docling_core.types.doc"):
        monkeypatch.setitem(sys.modules, name, None)  # import fails as if not installed
    with pytest.raises(ConfigError, match=re.escape("pip install 'section-anything[docling]'")):
        hand_built_tree().to_docling_document()


# -- Docling: structure (needs docling-core) ---------------------------------------------------------


def test_docling_document_follows_the_tree(paper_pdf):
    pytest.importorskip("docling_core")
    from docling_core.types.doc import DoclingDocument, SectionHeaderItem, TextItem, TitleItem

    tree = section_anything.section(paper_pdf)
    doc = tree.to_docling_document(paper_pdf)
    assert doc.name == "paper" and doc.origin.filename == "paper.pdf" and doc.origin.mimetype == "application/pdf"
    digest = hashlib.sha256(paper_pdf.read_bytes()).hexdigest()
    assert doc.origin.binary_hash == int(digest, 16) & 0xFFFFFFFFFFFFFFFF  # as Docling hashes the file
    assert sorted(doc.pages) == [1, 2] and doc.pages[1].size.width == 612.0

    items = [it for it, _level in doc.iterate_items()]
    heads = [it for it in items if isinstance(it, TitleItem | SectionHeaderItem)]
    assert [h.text for h in heads] == HEADINGS
    assert isinstance(heads[0], TitleItem)
    assert [h.level for h in heads[1:]] == [1, 2, 1, 1]
    by_text = {h.text: h for h in heads}
    assert by_text["1.1 Scope"].parent.resolve(doc) is by_text["1 Introduction"]
    assert all(h.parent.cref == "#/body" for h in heads if h.text != "1.1 Scope")

    got = {h.text: [c.resolve(doc).text for c in h.children if not isinstance(c.resolve(doc), SectionHeaderItem)]
           for h in heads}
    assert got == bodies_by_heading(tree)
    for it in items:
        assert isinstance(it, TextItem) and it.prov
        for p in it.prov:
            assert p.page_no in doc.pages and 0 <= p.bbox.l < p.bbox.r <= 612 and 0 <= p.bbox.b < p.bbox.t <= 792
        assert it.prov[0].charspan[0] == 0 and it.prov[-1].charspan[1] == len(it.text)

    # Docling's own Markdown of the document is ours (title '#', level n '#' x (n + 1)).
    assert doc.export_to_markdown() + "\n" == tree.to_markdown(body=True)
    again = DoclingDocument.model_validate_json(doc.model_dump_json())  # valid, serialisable
    assert again.export_to_markdown() == doc.export_to_markdown()


def test_docling_paragraph_across_pages(across_pages_pdf):
    pytest.importorskip("docling_core")
    doc = section_anything.section(across_pages_pdf).to_docling_document()
    assert doc.origin is None and doc.name == "document"
    split = [t for t in doc.texts if len(t.prov) > 1]
    assert len(split) == 1
    para = split[0]
    assert [p.page_no for p in para.prov] == [1, 2]
    (a, b), (c, d) = (p.charspan for p in para.prov)
    assert a == 0 and b + 1 == c and d == len(para.text)
    assert para.text[c:d] == "then ends on the second page here."


def test_docling_front_matter_and_no_extraction(front_matter_pdf):
    pytest.importorskip("docling_core")
    from docling_core.types.doc import SectionHeaderItem, TitleItem

    doc = section_anything.section(front_matter_pdf).to_docling_document()
    items = [it for it, _level in doc.iterate_items()]
    assert not isinstance(items[0], SectionHeaderItem) and items[0].parent.cref == "#/body"
    assert [it.text for it in items if isinstance(it, SectionHeaderItem)] == ["1 Introduction", "2 Methods"]

    doc = hand_built_tree().to_docling_document()
    heads = [it for it, _level in doc.iterate_items()]
    assert [(type(h).__name__, getattr(h, "level", None), h.text) for h in heads] == [
        (TitleItem.__name__, None, "My Paper"), ("SectionHeaderItem", 1, "1 Intro"),
        ("SectionHeaderItem", 2, "1.1 Scope"), ("SectionHeaderItem", 7, "Deep"),
    ]
    assert heads[3].parent.resolve(doc) is heads[2] and not doc.pages and all(not h.prov for h in heads)


# -- Round trips through the other libraries' chunkers ----------------------------------------------


def test_unstructured_chunk_by_title_starts_at_our_headings(paper_pdf):
    pytest.importorskip("unstructured")
    from unstructured.chunking.title import chunk_by_title
    from unstructured.documents.elements import Title
    from unstructured.staging.base import elements_from_dicts, elements_from_json

    tree = section_anything.section(paper_pdf)
    dicts = tree.to_unstructured_elements(paper_pdf)
    elements = elements_from_dicts(dicts)
    assert json.loads(json.dumps([e.to_dict() for e in elements])) == dicts  # every field survives
    assert [e.to_dict() for e in elements_from_json(text=json.dumps(dicts))] == [e.to_dict() for e in elements]
    assert [e.metadata.category_depth for e in elements if isinstance(e, Title)] == [0, 0, 1, 0, 0]

    chunks = chunk_by_title(elements, max_characters=300, combine_text_under_n_chars=0)
    starts = []
    for c in chunks:
        orig = c.metadata.orig_elements
        titles = [o for o in orig if isinstance(o, Title)]
        assert len(titles) <= 1 and (not titles or orig[0] is titles[0])  # no chunk crosses a heading
        if titles:
            starts.append(titles[0].text)
            assert c.text.startswith(titles[0].text) and not c.metadata.is_continuation
        assert len(c.text) <= 300
    assert starts == HEADINGS
    assert len(chunks) == 13 and sum(bool(c.metadata.is_continuation) for c in chunks) == 4

    # Unstructured's defaults merge short sections into one chunk; each chunk still starts at a heading.
    merged = chunk_by_title(elements)
    assert len(merged) < len(chunks)
    assert all(any(c.text.startswith(h) for h in HEADINGS) or c.metadata.is_continuation for c in merged)


def test_docling_hybrid_chunker_headings_match_heading_path(paper_pdf):
    pytest.importorskip("docling_core")
    pytest.importorskip("semchunk")
    hybrid = pytest.importorskip("docling_core.transforms.chunker.hybrid_chunker")
    from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
    from docling_core.types.doc import SectionHeaderItem, TitleItem

    class Words(BaseTokenizer):
        """Counts whitespace-separated words: no tokenizer download."""

        max_tokens: int = 40

        def count_tokens(self, text: str) -> int:
            return len(text.split())

        def get_max_tokens(self) -> int:
            return self.max_tokens

        def get_tokenizer(self) -> Any:
            return self.count_tokens

    tree = section_anything.section(paper_pdf)
    doc = tree.to_docling_document()
    section_of = {}  # text item -> heading of its section
    for it, _level in doc.iterate_items():
        if isinstance(it, TitleItem | SectionHeaderItem):
            head = it.text
        else:
            section_of[it.self_ref] = head

    chunker = hybrid.HybridChunker(tokenizer=Words())
    chunks = list(chunker.chunk(doc))
    expected = dict(zip(HEADINGS, docling_paths(tree), strict=True))
    words: dict[str, list[str]] = {}
    for c in chunks:
        heads = {section_of[d.self_ref] for d in c.meta.doc_items}
        assert len(heads) == 1  # no chunk crosses a heading
        head = heads.pop()
        assert c.meta.headings == expected[head]
        assert Words().count_tokens(chunker.contextualize(c)) <= 40
        words.setdefault(head, []).extend(c.text.split())
    assert expected["1.1 Scope"] == ["A Study of Sectioning", "1 Introduction", "1.1 Scope"]
    assert words == {h: " ".join(b).split() for h, b in bodies_by_heading(tree).items() if b}  # all text, once
    assert len(chunks) == 12


def test_unstructured_export_on_real_paper(readoc_pdf):
    """End to end on a real PDF (SECTIONANY_TEST_PDF): unique ids, parents before children."""
    tree = section_anything.section(readoc_pdf)
    els = tree.to_unstructured_elements(readoc_pdf)
    ids = [e["element_id"] for e in els]
    assert len(set(ids)) == len(ids)
    titles: set[str] = set()
    for e in els:
        parent = e["metadata"].get("parent_id")
        assert parent is None or parent in titles
        if e["type"] == "Title":
            titles.add(e["element_id"])
    assert len(titles) == sum("front_matter" not in s["flags"] for s in tree.sections)


def test_docling_export_on_real_paper(readoc_pdf):
    """End to end on a real PDF (SECTIONANY_TEST_PDF): Docling's heading context is ours."""
    pytest.importorskip("docling_core")
    chunker = pytest.importorskip("docling_core.transforms.chunker.hierarchical_chunker")
    from docling_core.types.doc import SectionHeaderItem, TitleItem

    tree = section_anything.section(readoc_pdf)
    doc = tree.to_docling_document(readoc_pdf)
    section_of, heads = {}, []
    head = None  # front matter: no heading
    for it, _level in doc.iterate_items():
        if isinstance(it, TitleItem | SectionHeaderItem):
            head = it.self_ref
            heads.append(head)
        else:
            section_of[it.self_ref] = head
    expected = {None: [], **dict(zip(heads, docling_paths(tree), strict=True))}
    for c in chunker.HierarchicalChunker().chunk(doc):  # HybridChunker's first pass
        refs = {section_of[d.self_ref] for d in c.meta.doc_items}
        assert len(refs) == 1
        assert (c.meta.headings or []) == expected[refs.pop()]
