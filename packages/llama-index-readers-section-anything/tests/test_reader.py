"""Offline tests in Free mode (no model, no network) on a PDF generated at test time."""

from __future__ import annotations

import asyncio

import pytest
import section_anything
from llama_index.core import SimpleDirectoryReader
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document, MetadataMode, NodeRelationship
from llama_index.core.vector_stores.utils import node_to_metadata_dict

from llama_index.readers.section_anything import SectionAnythingReader

KEYS = {"file_path", "file_name", "section_index", "title", "number", "level", "heading_path", "page_start",
        "page_end", "start", "end", "flags", "document_title", "mode", "model", "document_cost_usd"}


def test_one_document_per_section(paper_pdf):
    reader = SectionAnythingReader()
    assert isinstance(reader, BaseReader)
    docs = reader.load_data(paper_pdf)
    assert all(isinstance(d, Document) for d in docs)
    assert [d.metadata["heading_path"] for d in docs] == [
        "A Study of Sectioning", "1 Introduction", "1 Introduction > 1.1 Scope",
        "2 Methods", "2 Methods > 2.1 Data", "3 Results",
    ]
    scope = docs[2]
    assert set(scope.metadata) == KEYS
    assert scope.metadata["file_path"] == str(paper_pdf) and scope.metadata["file_name"] == "paper.pdf"
    assert (scope.metadata["number"], scope.metadata["title"], scope.metadata["level"]) == ("1.1", "Scope", 2)
    assert (scope.metadata["page_start"], scope.metadata["page_end"]) == (1, 1)
    assert (scope.metadata["mode"], scope.metadata["model"], scope.metadata["document_cost_usd"]) == ("free", None, 0.0)
    assert docs[0].metadata["flags"] == "doc_title"
    assert scope.id_ == f"{paper_pdf}_part_2"


def test_metadata_is_flat_for_vector_stores(paper_pdf):
    for doc in SectionAnythingReader().load_data(paper_pdf):
        node_to_metadata_dict(doc, flat_metadata=True)  # raises on lists or dicts


def test_embeddings_see_the_heading_path_only(paper_pdf):
    scope = SectionAnythingReader().load_data(paper_pdf)[2]
    embed = scope.get_content(MetadataMode.EMBED)
    assert "heading_path: 1 Introduction > 1.1 Scope" in embed
    assert "page_start" not in embed and "file_path" not in embed and "mode:" not in embed
    llm = scope.get_content(MetadataMode.LLM)
    assert "page_start: 1" in llm and "file_name: paper.pdf" in llm and "section_index" not in llm


def test_text_is_the_library_body_export(paper_pdf):
    docs = SectionAnythingReader().load_data(paper_pdf)
    tree = section_anything.section(paper_pdf)
    assert "\n\n".join(d.text for d in docs) + "\n" == tree.to_markdown(body=True)
    assert docs[2].text.startswith("### 1.1 Scope\n\nSectioning splits a long document")


def test_relationships(paper_pdf):
    docs = SectionAnythingReader().load_data(paper_pdf)
    rel = NodeRelationship
    methods, data = docs[3], docs[4]
    assert data.relationships[rel.PARENT].node_id == methods.id_
    assert [c.node_id for c in methods.relationships[rel.CHILD]] == [data.id_]
    assert rel.PARENT not in methods.relationships  # top level; the title is not a parent
    assert data.relationships[rel.PREVIOUS].node_id == methods.id_
    assert methods.relationships[rel.NEXT].node_id == data.id_
    assert rel.PREVIOUS not in docs[0].relationships and rel.NEXT not in docs[-1].relationships
    plain = SectionAnythingReader(relationships=False).load_data(paper_pdf)
    assert all(not d.relationships for d in plain)


def test_without_headings_skips_sections_with_no_text(paper_pdf):
    docs = SectionAnythingReader(include_heading=False).load_data(paper_pdf)
    assert [d.metadata["title"] for d in docs] == ["Introduction", "Scope", "Data", "Results"]
    assert docs[2].metadata["heading_path"] == "2 Methods > 2.1 Data"
    assert NodeRelationship.PARENT not in docs[2].relationships  # its parent has no Document
    assert docs[1].relationships[NodeRelationship.PARENT].node_id == docs[0].id_


def test_simple_directory_reader(paper_pdf):
    reader = SectionAnythingReader()
    docs = SimpleDirectoryReader(input_files=[paper_pdf], file_extractor={".pdf": reader},
                                 filename_as_id=True).load_data()
    assert len(docs) == 6
    assert docs[2].metadata["heading_path"] == "1 Introduction > 1.1 Scope"
    assert "file_size" in docs[2].metadata  # SimpleDirectoryReader's own metadata is merged
    ids = {d.id_ for d in docs}  # filename_as_id keeps the ids, so the links still resolve
    assert all(d.relationships[NodeRelationship.PREVIOUS].node_id in ids for d in docs[1:])


def test_extra_info_and_async(paper_pdf):
    docs = asyncio.run(SectionAnythingReader().aload_data(paper_pdf, extra_info={"collection": "papers"}))
    assert len(docs) == 6 and all(d.metadata["collection"] == "papers" for d in docs)


def test_fsspec_filesystem(paper_pdf):
    from fsspec.implementations.memory import MemoryFileSystem

    fs = MemoryFileSystem()
    fs.pipe("/bucket/remote.pdf", paper_pdf.read_bytes())
    docs = SectionAnythingReader().load_data("/bucket/remote.pdf", fs=fs)
    assert len(docs) == 6 and docs[0].metadata["file_name"] == "remote.pdf"


def test_options_pass_through(paper_pdf):
    with pytest.raises(section_anything.PdfTooLarge):
        SectionAnythingReader(max_pages=1).load_data(paper_pdf)
    with pytest.raises(section_anything.ConfigError, match="needs an API key"):
        SectionAnythingReader(mode="quick").load_data(paper_pdf)  # refused before any call
    with pytest.raises(section_anything.UnpricedModelError):
        SectionAnythingReader(mode="quick", api_key="sk-test-not-real", model="no-such-model").load_data(paper_pdf)
    with pytest.raises(TypeError, match="max_usd_per_doc"):
        SectionAnythingReader(max_usd_per_doc=1.0)


def test_api_key_never_reaches_documents(paper_pdf):
    key = "sk-test-not-real-0123456789"
    reader = SectionAnythingReader(api_key=key)  # free mode: the key is unused
    docs = reader.load_data(paper_pdf)
    assert key not in repr(reader)
    assert all(key not in d.model_dump_json() for d in docs)


def test_real_pdf(real_pdf):
    docs = SectionAnythingReader().load_data(real_pdf)
    assert len(docs) >= 5
    assert all(1 <= d.metadata["page_start"] <= d.metadata["page_end"] for d in docs)
