"""Convert READoc PDFs with Docling (branch with `demote_unmatched_headings`) and save the heading
hierarchy for each option setting and outline.

One conversion per PDF: default `PdfPipelineOptions`, `generate_parsed_pages=True`,
`HeadingHierarchyOptions(enabled=True, demote_unmatched_headings=True)`. Just before the
heading-hierarchy stage runs, a wrapper copies the document, parsed pages and outline, and runs the
same stage on deep copies with:

  off / on            the full outline
  off_deep / on_deep  the outline without its deepest level (only when it has 2 or more levels)
  off_top / on_top    the top outline level only

The outline is read only by this stage, so running it with a reduced outline is the same as
converting a PDF with that outline. Writes <out_dir>/<id>.<variant>.md and <out_dir>/runs.jsonl.

usage: python run_docling.py <out_dir> <pdf> [<pdf> ...]
"""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import HeadingHierarchyOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.stages.heading_hierarchy.heading_hierarchy_model import HeadingHierarchyModel
from docling_core.types.doc.document import SectionHeaderItem

OFF = HeadingHierarchyOptions(enabled=True)
ON = HeadingHierarchyOptions(enabled=True, demote_unmatched_headings=True)
SNAP: dict = {}


def headings(doc) -> list[tuple[str, int]]:
    return [(it.text, it.level) for it, _ in doc.iterate_items() if isinstance(it, SectionHeaderItem)]


class Wrapper:
    def __init__(self, inner):
        self.inner = inner
        self.options = inner.options

    def __call__(self, conv_res):
        outline = list(conv_res._pdf_outline or [])
        levels = sorted({b.level for b in outline if (b.title or "").strip()})
        scenarios = {"": outline, "_top": [b for b in outline if levels and b.level == levels[0]]}
        if len(levels) >= 2:
            scenarios["_deep"] = [b for b in outline if b.level != levels[-1]]
        for suffix, bookmarks in scenarios.items():
            for name, opts in (("off", OFF), ("on", ON)):
                doc = conv_res.document.model_copy(deep=True)
                fake = SimpleNamespace(document=doc, pages=conv_res.pages, _pdf_outline=bookmarks)
                SNAP[name + suffix] = HeadingHierarchyModel(opts)(fake)
        SNAP["outline_levels"] = len(levels)
        return self.inner(conv_res)  # the pipeline's own run: option on, full outline


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    opts = PdfPipelineOptions()
    opts.generate_parsed_pages = True
    opts.heading_hierarchy_options = ON
    conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    conv.initialize_pipeline(InputFormat.PDF)
    pipe = conv._get_pipeline(InputFormat.PDF)
    pipe.heading_hierarchy_model = Wrapper(pipe.heading_hierarchy_model)
    for pdf in map(Path, sys.argv[2:]):
        if (out / f"{pdf.stem}.on.md").exists():
            continue
        SNAP.clear()
        t = time.time()
        res = conv.convert(str(pdf), raises_on_error=False)
        rec = {"id": pdf.stem, "seconds": round(time.time() - t, 1), "outline_levels": SNAP.get("outline_levels")}
        if "on" in SNAP:
            # The pipeline's own output must equal the side run with the same option and outline.
            rec["pipeline_equals_side_run"] = headings(res.document) == headings(SNAP["on"])
            for name, doc in SNAP.items():
                if not isinstance(doc, int):
                    doc.save_as_markdown(out / f"{pdf.stem}.{name}.md")
        with open(out / "runs.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
