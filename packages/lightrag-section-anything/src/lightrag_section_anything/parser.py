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
        import pypdfium2 as pdfium

        from lightrag_section_anything.core import _core

        max_mb = float(os.getenv("SECTIONANY_MAX_MB", "100"))
        if source.stat().st_size > max_mb * 1_000_000:
            raise ValueError(f"{file_path}: larger than SECTIONANY_MAX_MB={max_mb:g}")
        _core()  # makes the sectioning core importable
        from app.sectioning.extract import PDFIUM_LOCK  # PDFium is not thread-safe: every use takes this lock

        try:
            with PDFIUM_LOCK:
                pdf = pdfium.PdfDocument(str(source))
                try:
                    n = len(pdf)
                finally:
                    pdf.close()
        except Exception as e:
            raise ValueError(f"cannot open PDF {file_path}: {e}") from e
        cap = int(os.getenv("SECTIONANY_MAX_PAGES", "500"))
        if n > cap:
            raise ValueError(f"{file_path}: {n} pages is over SECTIONANY_MAX_PAGES={cap}")

    def extract(self, source: Path, *, parsed_dir: Path, asset_dir: Path, base_name: str,
                runtime: NativeExtractRuntime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        from lightrag_section_anything.blocks import build_blocks
        from lightrag_section_anything.core import section_pdf

        res = section_pdf(source, self.mode)
        from app.sectioning.structure import furniture_of  # importable once section_pdf loaded the core

        blocks, doc_title = build_blocks(res.ext, res.sections, furniture_of(res.ext),
                                         synthetic_titles=os.getenv("SECTIONANY_SYNTHETIC_TITLES") == "true")
        if not any(b["content"].strip() for b in blocks):
            raise ValueError("no text extracted; scanned PDFs need an OCR engine, e.g. name.[mineru-P].pdf")
        warnings = {
            "sectionany_mode": res.mode, "sectionany_model": res.model or "", "sectionany_cost_usd": res.cost_usd,
            "sectionany_calls": res.calls, "sectionany_tokens_in": res.tokens_in, "sectionany_tokens_out": res.tokens_out,
            "sectionany_seconds": res.seconds, "sectionany_sections": len(res.sections),
            "sectionany_flagged": sum(bool(s.get("flags")) for s in res.sections),
        }
        if res.downgraded:
            warnings["sectionany_downgraded"] = res.downgraded
        audit = {**warnings, "pages": len(res.ext.pages),
                 "sections": [{k: s.get(k) for k in ("number", "title", "level", "page_start", "page_end", "flags")}
                              for s in res.sections]}
        (parsed_dir / f"{Path(base_name).name}.sectionany.json").write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=1))
        from lightrag_section_anything import __version__

        metadata = {"doc_title": doc_title, "split_option": {
            "engine_version": __version__, "mode": res.mode, "model": res.model or "", "cost_usd": res.cost_usd,
            "sections": len(res.sections)}}
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
