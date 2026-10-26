"""LlamaIndex reader: one `Document` per PDF section, found by Section Anything."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import section_anything
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document, NodeRelationship, ObjectType, RelatedNodeInfo

from llama_index.readers.section_anything._sections import section_options, section_records

if TYPE_CHECKING:
    from fsspec import AbstractFileSystem

# Metadata the reader sets. Embeddings see only the heading path and the document title; the LLM
# also sees the file name and pages (for citations). The rest is for filtering and debugging.
KEYS = ("file_path", "file_name", "section_index", "title", "number", "level", "heading_path",
        "page_start", "page_end", "start", "end", "flags", "document_title", "mode", "model",
        "document_cost_usd")
EMBED_KEYS = {"heading_path", "document_title"}
LLM_KEYS = EMBED_KEYS | {"file_name", "page_start", "page_end"}


class SectionAnythingReader(BaseReader):
    """Read a PDF as one Document per section (heading, level, pages, character span).

    Args:
        mode: "free" (default: rules only, no model, $0), "quick", "standard" or
            "local:<ollama model>". See the section-anything README for what each sends where.
        include_heading: start each Document with its heading as a Markdown line
            ("## 3.1 Data"). Default True. With False, sections with no text of their own are
            skipped.
        relationships: link the Documents: PARENT (the enclosing section), CHILD, PREVIOUS and
            NEXT. Default True. Ids are "<file path>_part_<n>", the format SimpleDirectoryReader's
            `filename_as_id` uses, so the links survive it.
        **opts: passed to `section_anything.section`: api_key, base_url, model, max_usd,
            prices, over_budget, max_pages, extract_timeout, progress, settings. Anything not
            given falls back to the SECTIONANY_* environment variables.

    Metadata is flat (str, int, float or None), so it fits every vector store: file_path,
    file_name, section_index, title, number, level, heading_path ("3 Method > 3.1 Data"),
    page_start, page_end, start and end (offsets into the library's extracted text), flags
    (comma-separated), document_title, and the run's mode (after any downgrade), model and
    document_cost_usd (the whole document's cost). `extra_info` is merged over it.

    Example:
        .. code-block:: python

            from llama_index.readers.section_anything import SectionAnythingReader

            docs = SectionAnythingReader().load_data("paper.pdf")
            docs[2].metadata["heading_path"]  # '1 Introduction > 1.1 Scope'
    """

    def __init__(self, mode: str = "free", *, include_heading: bool = True, relationships: bool = True,
                 **opts: Any) -> None:
        self.mode = mode
        self.include_heading = include_heading
        self.relationships = relationships
        self._opts = section_options(opts)  # may hold an API key: never logged or put in metadata

    def lazy_load_data(self, file: str | os.PathLike[str], extra_info: dict | None = None,
                       fs: AbstractFileSystem | None = None) -> Iterable[Document]:
        yield from self.load_data(file, extra_info=extra_info, fs=fs)

    def load_data(self, file: str | os.PathLike[str], extra_info: dict | None = None,
                  fs: AbstractFileSystem | None = None) -> list[Document]:
        """Section one PDF. `fs` (an fsspec filesystem, as SimpleDirectoryReader passes for
        remote files) is copied to a temporary local file first."""
        if fs is None or _is_local(fs):
            tree = section_anything.section(file, self.mode, **self._opts)
        else:
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / (PurePosixPath(str(file)).name or "document.pdf")
                with fs.open(str(file), "rb") as src, open(local, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                tree = section_anything.section(local, self.mode, **self._opts)

        path = os.fspath(file)
        records = section_records(tree, self.include_heading)
        docs = []
        for n, rec in enumerate(records):
            meta = {"file_path": path, "file_name": os.path.basename(path), **rec.metadata}
            meta["heading_path"] = " > ".join(meta["heading_path"])
            meta["flags"] = ", ".join(meta["flags"])
            meta.update(extra_info or {})
            docs.append(Document(
                id_=f"{path}_part_{n}", text=rec.text, metadata=meta,
                excluded_embed_metadata_keys=[k for k in KEYS if k not in EMBED_KEYS],
                excluded_llm_metadata_keys=[k for k in KEYS if k not in LLM_KEYS],
            ))
        if self.relationships:
            _link(docs, [rec.parent for rec in records])
        return docs


def _is_local(fs: AbstractFileSystem) -> bool:
    from fsspec.implementations.local import LocalFileSystem

    return isinstance(fs, LocalFileSystem)


def _ref(doc: Document) -> RelatedNodeInfo:
    return RelatedNodeInfo(node_id=doc.id_, node_type=ObjectType.DOCUMENT)


def _link(docs: list[Document], parents: list[int | None]) -> None:
    for n, (doc, parent) in enumerate(zip(docs, parents, strict=True)):
        if parent is not None:
            doc.relationships[NodeRelationship.PARENT] = _ref(docs[parent])
            children = docs[parent].relationships.setdefault(NodeRelationship.CHILD, [])
            children.append(_ref(doc))
        if n > 0:
            doc.relationships[NodeRelationship.PREVIOUS] = _ref(docs[n - 1])
            docs[n - 1].relationships[NodeRelationship.NEXT] = _ref(doc)
