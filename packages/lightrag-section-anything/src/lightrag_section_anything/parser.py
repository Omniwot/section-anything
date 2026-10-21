"""LightRAG parser engines: PDF -> Section Anything sections -> sidecar blocks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lightrag.parser.native_base import NativeExtractRuntime, NativeParserBase

if TYPE_CHECKING:
    from lightrag.sidecar.ir import IRDoc


class SectionAnyParser(NativeParserBase):
    """Mode from ``SECTIONANY_MODE`` (free | quick | standard | local:<model>)."""

    engine_name = "sectionany"
    empty_content_label = "Section Anything"
    mode: str | None = None  # None: read SECTIONANY_MODE at parse time

    def validate_source(self, source: Path, file_path: str) -> None:
        super().validate_source(source, file_path)
        if source.suffix.lower() != ".pdf":
            raise ValueError(f"{self.engine_name} parses PDF files only: {file_path}")

    def validate_source_blocking(self, source: Path, file_path: str) -> None:
        """Size and page caps (SECTIONANY_MAX_MB, SECTIONANY_MAX_PAGES), checked without parsing any
        page content."""
        from section_anything import PdfError, Settings, check_pdf

        try:
            check_pdf(source, Settings())
        except PdfError as e:
            raise ValueError(f"{file_path}: {e}") from None

    def extract(self, source: Path, *, parsed_dir: Path, asset_dir: Path, base_name: str,
                runtime: NativeExtractRuntime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        from section_anything.structure import furniture_of

        from lightrag_section_anything import __version__
        from lightrag_section_anything.blocks import build_blocks
        from lightrag_section_anything.core import section_pdf

        tree = section_pdf(source, self.mode)
        ext = tree.extraction
        blocks, doc_title = build_blocks(ext, tree.resolved, furniture_of(ext),
                                         synthetic_titles=os.getenv("SECTIONANY_SYNTHETIC_TITLES") == "true")
        if not any(b["content"].strip() for b in blocks):
            raise ValueError("no text extracted; scanned PDFs need an OCR engine, e.g. name.[mineru-P].pdf")
        usage = tree.usage
        warnings = {
            "sectionany_mode": tree.mode, "sectionany_model": tree.model or "", "sectionany_cost_usd": tree.cost_usd,
            "sectionany_calls": usage.get("calls", 0), "sectionany_tokens_in": usage.get("input_tokens", 0),
            "sectionany_tokens_out": usage.get("output_tokens", 0), "sectionany_seconds": tree.seconds,
            "sectionany_sections": len(tree.sections),
            "sectionany_flagged": sum(bool(s.get("flags")) for s in tree.sections),
        }
        if tree.downgraded:
            warnings["sectionany_downgraded"] = tree.downgraded
        audit = {**warnings, "pages": tree.pages,
                 "sections": [{k: s.get(k) for k in ("number", "title", "level", "page_start", "page_end", "flags")}
                              for s in tree.sections]}
        (parsed_dir / f"{Path(base_name).name}.sectionany.json").write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=1))
        metadata = {"doc_title": doc_title, "split_option": {
            "engine_version": __version__, "mode": tree.mode, "model": tree.model or "", "cost_usd": tree.cost_usd,
            "sections": len(tree.sections)}}
        return blocks, warnings, metadata

    def build_ir(self, blocks: list[dict[str, Any]], *, document_name: str, asset_dir_name: str,
                 metadata: dict[str, Any]) -> IRDoc:
        from lightrag.sidecar.ir import IRBlock, IRDoc, IRPosition

        ir_blocks = [
            IRBlock(content_template=b["content"], heading=b["heading"], level=b["level"],
                    parent_headings=list(b["parent_headings"]), session_type=b["session_type"],
                    is_title_block=b["is_title_block"],
                    positions=[IRPosition(type=p["type"], anchor=p["anchor"], range=p["range"]) for p in b["positions"]])
            for b in blocks
        ]
        return IRDoc(document_name=document_name, document_format="pdf",
                     doc_title=metadata.get("doc_title") or Path(document_name).stem,
                     split_option=metadata.get("split_option", {}), blocks=ir_blocks,
                     bbox_attributes={"origin": "LEFTBOTTOM"})

    def surface_warnings(self, warnings: dict[str, Any], source: Path) -> dict[str, Any] | None:
        return dict(warnings)  # mode, model, cost and counts go to doc_status


class FreeParser(SectionAnyParser):
    engine_name = "sectionany_free"
    mode = "free"


class QuickParser(SectionAnyParser):
    engine_name = "sectionany_quick"
    mode = "quick"


class StandardParser(SectionAnyParser):
    engine_name = "sectionany_standard"
    mode = "standard"


class LocalParser(SectionAnyParser):
    engine_name = "sectionany_local"
    mode = "local"
