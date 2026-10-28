"""Section Anything demo for Hugging Face Spaces: Free mode only.

Free mode reads the PDF's text layer, bookmarks and printed table of contents, then applies
typography and numbering rules on this machine's CPU. No model is called and no API key is used.
Nothing about an upload (file name or text) is logged.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import urllib.request
import uuid
from pathlib import Path

import gradio as gr
import section_anything
from gradio.utils import get_upload_folder
from section_anything import ExtractionTimeout, PdfError, PdfTooLarge, SectionAnythingError, Settings

MAX_MB, MAX_PAGES, TIMEOUT_S = 20, 100, 120
SETTINGS = Settings(max_mb=MAX_MB, max_pages=MAX_PAGES, extract_timeout_seconds=TIMEOUT_S)
log = logging.getLogger("section-anything-space")

REPO = "https://github.com/Omniwot/section-anything"
COLAB = "https://colab.research.google.com/github/Omniwot/section-anything/blob/main/notebooks/quickstart.ipynb"
SITE = "https://omniwot.github.io/section-anything/"
PYPI = "https://pypi.org/project/section-anything/"
# The example is fetched from arXiv on first use, so no binary file lives in either repository.
EXAMPLE_URLS = ("https://arxiv.org/pdf/2304.08485v2", "https://export.arxiv.org/pdf/2304.08485v2")
EXAMPLE = Path(tempfile.gettempdir()) / "section-anything-example" / "2304.08485v2.pdf"
_example_lock = threading.Lock()

HEADER = f"""# Section Anything
Find the sections of a PDF: every heading, its level, the pages it spans and the exact text under it.
[GitHub]({REPO}) · [Colab notebook]({COLAB}) · [Website]({SITE}) · [PyPI]({PYPI}) · `pip install section-anything`"""
PRIVACY = f"""**Privacy.** Free mode runs on this Space's CPU and sends nothing to any model. Your PDF is
processed in memory and in a temporary folder; uploads and their JSON files are deleted within two hours
(an hourly clean-up of files older than an hour) and on every restart. File names and text are not logged.
Don't upload confidential documents: this is a public demo.

**Limits:** {MAX_PAGES} pages and {MAX_MB} MB per PDF, with a text layer (scanned PDFs need OCR first)."""
EXAMPLE_NOTE = """*Visual Instruction Tuning*, Liu et al., [arXiv:2304.08485](https://arxiv.org/abs/2304.08485) (v2),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Downloaded from arXiv when you click; not modified."""


def pages(s: dict) -> str:
    return str(s["page_start"]) if s["page_start"] == s["page_end"] else f"{s['page_start']}–{s['page_end']}"


def heading(s: dict) -> str:
    return f"{s['number']} {s['title']}".strip() or "(front matter)"


def section_view(i: int | None, doc: dict | None):
    if not doc or i is None:
        return gr.Textbox(value="", label="Section text")
    s = doc["sections"][i]
    label = f"Level {s['level']} · pages {pages(s)} · characters {s['start']:,}–{s['end']:,} of tree.text"
    return gr.Textbox(value=doc["text"][s["start"]:s["end"]], label=label)


def fail(message: str = ""):
    status = f"**Could not section this PDF.** {message}" if message else ""
    return status, "", [], gr.Dropdown(choices=[], value=None), section_view(None, None), None, None


def run(path: str | None, progress=gr.Progress()):  # noqa: B008 (how Gradio injects progress)
    if not path:
        return fail()
    try:
        with open(path, "rb") as f:
            if b"%PDF-" not in f.read(1024):
                return fail("This file is not a PDF.")
        tree = section_anything.section(path, mode="free", settings=SETTINGS,
                                        progress=lambda frac, msg: progress(frac, desc=msg))
    except PdfTooLarge as exc:
        return fail(f"{str(exc).split(' (')[0]}. This demo takes up to {MAX_PAGES} pages and {MAX_MB} MB; "
                    f"install the library to run bigger files on your own machine.")
    except ExtractionTimeout:
        return fail(f"Reading the text took longer than {TIMEOUT_S} s and was stopped. Try a smaller PDF, "
                    "or run the library on your own machine.")
    except PdfError as exc:
        if "no text layer" in str(exc):
            return fail("This PDF has no text layer (it looks scanned). Section Anything reads the text "
                        "layer, so run OCR first, for example with OCRmyPDF.")
        return fail(f"{str(exc).split(' (')[0]}.")
    except (SectionAnythingError, OSError) as exc:
        log.warning("sectioning failed: %s", type(exc).__name__)  # the type only: no file name or text
        return fail("Text extraction failed on this PDF.")
    secs, s = tree.sections, tree.summary()
    status = f"**{s['pages']} pages · {s['sections']} sections · {s['seconds']:.1f} s** (Free mode: no model, $0)"
    body = [i for i, x in enumerate(secs) if not {"front_matter", "doc_title"} & set(x["flags"])]
    if not body:
        status += (". No headings found: Free mode needs bookmarks, a printed table of contents or clear "
                   "heading typography.")
    first = body[0] if body else (0 if secs else None)
    rows = [[x["level"], x["number"], x["title"], pages(x), ", ".join(x["flags"])] for x in secs]
    choices = [("\u2003" * (x["level"] - 1) + f"{heading(x)} · p. {pages(x)}", i) for i, x in enumerate(secs)]
    doc = {"text": tree.text, "sections": secs}
    data = tree.to_dict()
    data["sections"] = [{**x, "text": tree.text[x["start"]:x["end"]]} for x in secs]
    stem = re.sub(r"[^\w.-]+", "_", Path(path).stem)[:60] or "document"
    out = Path(get_upload_folder()) / f"sa-{uuid.uuid4().hex}" / f"{stem}.sections.json"
    out.parent.mkdir(parents=True, exist_ok=True)  # inside Gradio's cache, so delete_cache removes it
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return (status, tree.to_markdown(), rows, gr.Dropdown(choices=choices, value=first),
            section_view(first, doc), str(out), doc)


def load_example() -> str:
    with _example_lock:
        if EXAMPLE.exists():
            return str(EXAMPLE)
        for url in EXAMPLE_URLS:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "section-anything-space"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = r.read(MAX_MB * 1024 * 1024 + 1)
            except OSError as exc:
                log.warning("example download failed: %s", type(exc).__name__)
                continue
            if data.startswith(b"%PDF-") and len(data) <= MAX_MB * 1024 * 1024:
                EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
                tmp = EXAMPLE.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.replace(EXAMPLE)
                return str(EXAMPLE)
    raise gr.Error("Could not download the example from arXiv right now. Try again, or upload a PDF.")


with gr.Blocks(title="Section Anything", delete_cache=(3600, 3600), analytics_enabled=False) as demo:
    gr.Markdown(HEADER)
    gr.Markdown(PRIVACY)
    with gr.Row():
        pdf = gr.File(label="PDF", file_types=[".pdf"], type="filepath", scale=2)
        with gr.Column(scale=1):
            example = gr.Button("Try the example paper")
            gr.Markdown(EXAMPLE_NOTE)
    status = gr.Markdown()
    with gr.Row():
        tree_md = gr.Code(label="Heading tree: tree.to_markdown()", language="markdown", interactive=False,
                          lines=14, max_lines=30)
        with gr.Column():
            picker = gr.Dropdown(label="Section", choices=[], interactive=True)
            text = gr.Textbox(label="Section text", lines=14, max_lines=30, interactive=False, buttons=["copy"])
    table = gr.Dataframe(headers=["Level", "Number", "Title", "Pages", "Flags"], label="Sections",
                         datatype=["number", "str", "str", "str", "str"], interactive=False, wrap=True,
                         max_height=480)
    json_file = gr.File(label="JSON: the CLI's --format json output plus each section's text",
                        interactive=False)
    doc = gr.State(time_to_live=3600)

    pdf.change(run, inputs=pdf, outputs=[status, tree_md, table, picker, text, json_file, doc])
    picker.change(section_view, inputs=[picker, doc], outputs=text)
    example.click(load_example, outputs=pdf)

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2, max_size=20).launch(max_file_size=f"{MAX_MB}mb")
