"""Offline tests in Free mode (no model, no network) on a PDF generated at test time."""

from __future__ import annotations

import asyncio

import pytest
import section_anything
from langchain_core.documents import Document

from langchain_section_anything import SectionAnythingLoader

KEYS = {"source", "section_index", "title", "number", "level", "heading_path", "page_start", "page_end",
        "start", "end", "flags", "document_title", "mode", "model", "document_cost_usd"}


def test_one_document_per_section(paper_pdf):
    docs = SectionAnythingLoader(paper_pdf).load()
    assert all(isinstance(d, Document) for d in docs)
    assert [d.metadata["heading_path"] for d in docs] == [
        ["A Study of Sectioning"], ["1 Introduction"], ["1 Introduction", "1.1 Scope"],
        ["2 Methods"], ["2 Methods", "2.1 Data"], ["3 Results"],
    ]
    scope = docs[2]
    assert set(scope.metadata) == KEYS
    assert scope.metadata["source"] == str(paper_pdf)
    assert (scope.metadata["number"], scope.metadata["title"], scope.metadata["level"]) == ("1.1", "Scope", 2)
    assert (scope.metadata["page_start"], scope.metadata["page_end"]) == (1, 1)
    assert docs[4].metadata["page_start"] == 2
    assert scope.metadata["document_title"] == "A Study of Sectioning"
    assert (scope.metadata["mode"], scope.metadata["model"], scope.metadata["document_cost_usd"]) == ("free", None, 0.0)
    assert docs[0].metadata["flags"] == ["doc_title"]


def test_text_is_the_library_body_export(paper_pdf):
    """With headings, the Documents put together are exactly `section-anything --body`."""
    docs = SectionAnythingLoader(paper_pdf).load()
    tree = section_anything.section(paper_pdf)
    assert "\n\n".join(d.page_content for d in docs) + "\n" == tree.to_markdown(body=True)
    assert docs[2].page_content.startswith("### 1.1 Scope\n\nSectioning splits a long document")
    assert docs[2].page_content.count("1.1 Scope") == 1
    for d, sec in zip(docs, tree.sections, strict=True):
        assert (d.metadata["start"], d.metadata["end"]) == (sec["start"], sec["end"])


def test_without_headings_skips_sections_with_no_text(paper_pdf):
    docs = SectionAnythingLoader(paper_pdf, include_heading=False).load()
    titles = [d.metadata["title"] for d in docs]
    assert titles == ["Introduction", "Scope", "Data", "Results"]  # the title and "2 Methods" have no text
    assert docs[0].page_content.startswith("Sectioning splits a long document")
    assert docs[2].metadata["heading_path"] == ["2 Methods", "2.1 Data"]  # the skipped heading stays in the path
    assert all(d.page_content.strip() and "#" not in d.page_content for d in docs)


def test_several_files_and_lazy_loading(paper_pdf, tmp_path):
    other = tmp_path / "copy.pdf"
    other.write_bytes(paper_pdf.read_bytes())
    loader = SectionAnythingLoader([paper_pdf, str(other)])
    it = loader.lazy_load()
    assert next(it).metadata["source"] == str(paper_pdf)
    docs = loader.load()
    assert len(docs) == 12 and docs[-1].metadata["source"] == str(other)


def test_async_load(paper_pdf):
    docs = asyncio.run(SectionAnythingLoader(paper_pdf).aload())
    assert len(docs) == 6 and docs[1].metadata["title"] == "Introduction"


def test_options_pass_through(paper_pdf):
    with pytest.raises(section_anything.PdfTooLarge):
        SectionAnythingLoader(paper_pdf, max_pages=1).load()
    with pytest.raises(section_anything.ConfigError, match="needs an API key"):
        SectionAnythingLoader(paper_pdf, mode="quick").load()  # refused before any call
    with pytest.raises(section_anything.UnpricedModelError):
        SectionAnythingLoader(paper_pdf, mode="quick", api_key="sk-test-not-real", model="no-such-model").load()


def test_unknown_option_fails_early(paper_pdf):
    with pytest.raises(TypeError, match="max_usd_per_doc"):
        SectionAnythingLoader(paper_pdf, max_usd_per_doc=1.0)


def test_api_key_never_reaches_documents(paper_pdf):
    key = "sk-test-not-real-0123456789"
    loader = SectionAnythingLoader(paper_pdf, api_key=key)  # free mode: the key is unused
    docs = loader.load()
    assert key not in repr(loader)
    assert all(key not in repr(d) for d in docs)


def test_real_pdf(real_pdf):
    docs = SectionAnythingLoader(real_pdf).load()
    assert len(docs) >= 5
    assert all(1 <= d.metadata["page_start"] <= d.metadata["page_end"] for d in docs)
