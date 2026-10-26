"""LangChain document loader: one `Document` per PDF section, found by Section Anything."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import Any

import section_anything
from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from langchain_section_anything._sections import section_options, section_records

PathLike = str | os.PathLike[str]


class SectionAnythingLoader(BaseLoader):
    """Load PDFs as one Document per section (heading, level, pages, character span).

    Args:
        file_path: a PDF path, or several.
        mode: "free" (default: rules only, no model, $0), "quick", "standard" or
            "local:<ollama model>". See the section-anything README for what each sends where.
        include_heading: start each Document with its heading as a Markdown line
            ("## 3.1 Data"). Default True. With False, sections with no text of their own are
            skipped.
        **opts: passed to `section_anything.section`: api_key, base_url, model, max_usd,
            prices, over_budget, max_pages, extract_timeout, progress, settings. Anything not
            given falls back to the SECTIONANY_* environment variables.

    Metadata per Document: source, section_index, title, number, level, heading_path (list,
    outermost first, ending with this section), page_start, page_end, start and end (offsets
    into the library's extracted text), flags, document_title, and the run's mode (after any
    downgrade), model and document_cost_usd (the whole document's cost).

    Example:
        .. code-block:: python

            from langchain_section_anything import SectionAnythingLoader

            docs = SectionAnythingLoader("paper.pdf").load()
            docs[2].metadata["heading_path"]  # ['1 Introduction', '1.1 Scope']
    """

    def __init__(self, file_path: PathLike | Iterable[PathLike], mode: str = "free", *,
                 include_heading: bool = True, **opts: Any) -> None:
        if isinstance(file_path, str | os.PathLike):
            self.file_paths: list[PathLike] = [file_path]
        else:
            self.file_paths = list(file_path)
        self.mode = mode
        self.include_heading = include_heading
        self._opts = section_options(opts)  # may hold an API key: never logged or put in metadata

    def lazy_load(self) -> Iterator[Document]:
        """Section each PDF and yield its sections in reading order."""
        for path in self.file_paths:
            tree = section_anything.section(path, self.mode, **self._opts)
            source = os.fspath(path)
            for rec in section_records(tree, self.include_heading):
                yield Document(page_content=rec.text, metadata={"source": source, **rec.metadata})
