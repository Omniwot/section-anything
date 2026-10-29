"""Section Anything demo for Hugging Face Spaces.

Free mode runs live on any uploaded PDF: it reads the text layer, bookmarks and printed table of
contents, then applies typography and numbering rules on this machine's CPU.

Quick check and Standard need a model. This Space has no API key and calls no model: for three example
papers only, it shows runs computed once by the maintainers and saved in examples/ (make_examples.py).
Their section text is sliced from this Space's own extraction of the downloaded paper, and only where
the slice matches the saved run's hash and heading.

Nothing about an upload (file name or text) is logged.
"""

from __future__ import annotations

import hashlib
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
from section_anything import ExtractionTimeout, PdfError, PdfTooLarge, SectionAnythingError, SectionTree, Settings
from section_anything.markers import canon

MAX_MB, MAX_PAGES, TIMEOUT_S = 20, 100, 120
SETTINGS = Settings(max_mb=MAX_MB, max_pages=MAX_PAGES, extract_timeout_seconds=TIMEOUT_S)
log = logging.getLogger("section-anything-space")

REPO = "https://github.com/Omniwot/section-anything"
COLAB = "https://colab.research.google.com/github/Omniwot/section-anything/blob/main/notebooks/quickstart.ipynb"
SITE = "https://omniwot.github.io/section-anything/"
PYPI = "https://pypi.org/project/section-anything/"
MODES = {"Free": "free", "Quick check": "quick", "Standard": "standard"}
LABEL = {v: k for k, v in MODES.items()}
SECTION_KEYS = ("number", "title", "level", "page_start", "page_end", "start", "end", "flags")

# The example papers are fetched from arXiv on first use, so no PDF lives in either repository.
HERE = Path(__file__).parent
EXAMPLES = [json.loads((HERE / "examples" / f"{i}.json").read_text(encoding="utf-8"))
            for i in ("2304.08485v2", "2209.07299v2", "2305.06327v1")]
EXAMPLE_DIR = Path(tempfile.gettempdir()) / "section-anything-example"
_locks = {ex["id"]: threading.Lock() for ex in EXAMPLES}
_live: dict[str, dict] = {}  # example id -> this process's Free run and extracted text

HEADER = f"""# Section Anything
Find the sections of a PDF: every heading, its level, the pages it spans and the exact text under it.
[GitHub]({REPO}) · [Colab notebook]({COLAB}) · [Website]({SITE}) · [PyPI]({PYPI}) · `pip install section-anything`"""
PRIVACY = f"""**Privacy.** Free mode runs on this Space's CPU and sends nothing to any model. This Space has no
API key and calls no model: Quick check and Standard are shown only for the three example papers, as saved
runs. Your PDF is processed in memory and in a temporary folder; uploads and their JSON files are deleted
within two hours (an hourly clean-up of files older than an hour) and on every restart. File names and text
are not logged. Don't upload confidential documents: this is a public demo.

**Limits:** {MAX_PAGES} pages and {MAX_MB} MB per PDF, with a text layer (scanned PDFs need OCR first)."""
EXAMPLES_NOTE = f"""**Example papers.** Free runs live here. Quick check and Standard (both on gpt-6-luna) are
saved runs: computed once by us, never on this Space. Three examples, not a benchmark: over 905 held-out
READoc arXiv papers the [README]({REPO}#results) reports heading-tree TEDS of 70.0 for Standard, 68.0 for
Quick check and 60.0 for Free."""
NO_MODEL = (f"Quick check and Standard call a model, so this Space runs them only as saved runs on the three "
            f"example papers. For your own PDFs, [install the library]({REPO}#install) and use your own API key.")
HIDDEN = ("(Text not shown: this part of the PDF came out of this Space's extraction differently from the saved "
          "run's, so the saved character range would not give this section's text. The heading, level and "
          "pages above are the saved run's.)")


def pages(s: dict) -> str:
    return str(s["page_start"]) if s["page_start"] == s["page_end"] else f"{s['page_start']}–{s['page_end']}"


def heading(s: dict) -> str:
    return f"{s['number']} {s['title']}".strip() or "(front matter)"


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def heading_at(text: str, sec: dict) -> bool | None:
    """Same check as make_examples.py: the printed heading is where the span starts (None: nothing to check)."""
    flags = sec.get("flags") or []
    if "front_matter" in flags or "generated_title" in flags or not (sec.get("title") or "").strip():
        return None
    title = canon(sec["title"])[:60]
    return bool(title) and title in canon(text[sec["start"]:sec["start"] + 400 + len(sec["title"])])


def text_matches(text: str, sec: dict) -> bool:
    """The live slice is the saved run's section: the same text, or the same lines in another order (pdfminer
    can order table cells differently from one extraction to the next), with the heading where it was."""
    if sec["end"] > len(text):
        return False
    part = text[sec["start"]:sec["end"]]
    if sha16(part) != sec["sha"] and sha16("\n".join(sorted(part.split("\n")))) != sec["lines_sha"]:
        return False
    return sec["heading_check"] is not True or heading_at(text, sec) is True


def section_view(i: int | None, doc: dict | None):
    if not doc or i is None:
        return gr.Textbox(value="", label="Section text")
    s = doc["sections"][i]
    label = f"Level {s['level']} · pages {pages(s)} · characters {s['start']:,}–{s['end']:,} of tree.text"
    shown = doc["shown"] is None or doc["shown"][i]
    return gr.Textbox(value=doc["text"][s["start"]:s["end"]] if shown else HIDDEN, label=label)


def write_json(data: dict, stem: str) -> str:
    out = Path(get_upload_folder()) / f"sa-{uuid.uuid4().hex}" / f"{stem}.sections.json"
    out.parent.mkdir(parents=True, exist_ok=True)  # inside Gradio's cache, so delete_cache removes it
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


def render(status: str, secs: list[dict], text: str, markdown: str, json_path: str | None,
           shown: list[bool] | None = None):
    """The outputs shared by every view: status, heading tree, table, picker, section text, JSON, state."""
    body = [i for i, x in enumerate(secs) if not {"front_matter", "doc_title"} & set(x["flags"])]
    first = body[0] if body else (0 if secs else None)
    rows = [[x["level"], x["number"], x["title"], pages(x), ", ".join(x["flags"])] for x in secs]
    choices = [(" " * (x["level"] - 1) + f"{heading(x)} · p. {pages(x)}", i) for i, x in enumerate(secs)]
    doc = {"text": text, "sections": secs, "shown": shown}
    return (status, markdown, rows, gr.Dropdown(choices=choices, value=first), section_view(first, doc),
            json_path, doc)


def fail(message: str = ""):
    status = f"**Could not section this PDF.** {message}" if message else ""
    return status, "", [], gr.Dropdown(choices=[], value=None), section_view(None, None), None, None


def free_run(path: str, progress) -> dict:
    """Free mode on this CPU. Raises gr.Error with a message for the visitor."""
    try:
        with open(path, "rb") as f:
            if b"%PDF-" not in f.read(1024):
                raise gr.Error("This file is not a PDF.", print_exception=False)
        tree = section_anything.section(path, mode="free", settings=SETTINGS,
                                        progress=lambda frac, msg: progress(frac, desc=msg))
    except PdfTooLarge as exc:
        raise gr.Error(f"{str(exc).split(' (')[0]}. This demo takes up to {MAX_PAGES} pages and {MAX_MB} MB; "
                       f"install the library to run bigger files on your own machine.", print_exception=False) from None
    except ExtractionTimeout:
        raise gr.Error(f"Reading the text took longer than {TIMEOUT_S} s and was stopped. Try a smaller PDF, "
                       "or run the library on your own machine.", print_exception=False) from None
    except PdfError as exc:
        if "no text layer" in str(exc):
            raise gr.Error("This PDF has no text layer (it looks scanned). Section Anything reads the text "
                           "layer, so run OCR first, for example with OCRmyPDF.", print_exception=False) from None
        raise gr.Error(f"{str(exc).split(' (')[0]}.", print_exception=False) from None
    except (SectionAnythingError, OSError) as exc:
        log.warning("sectioning failed: %s", type(exc).__name__)  # the type only: no file name or text
        raise gr.Error("Text extraction failed on this PDF.", print_exception=False) from None
    data = tree.to_dict()
    data["sections"] = [{**x, "text": tree.text[x["start"]:x["end"]]} for x in tree.sections]
    return {"text": tree.text, "sections": tree.sections, "markdown": tree.to_markdown(), "data": data,
            "pages": tree.pages, "seconds": tree.seconds}


def free_status(run: dict, live_note: str = "") -> str:
    status = (f"**{run['pages']} pages · {len(run['sections'])} sections · {run['seconds']:.1f} s** "
              f"(Free mode{live_note}: no model, $0)")
    if not any(not {"front_matter", "doc_title"} & set(x["flags"]) for x in run["sections"]):
        status += (". No headings found: Free mode needs bookmarks, a printed table of contents or clear "
                   "heading typography.")
    return status


# --- Uploads: Free, live -------------------------------------------------------------------------

def upload_view(cur: dict, mode: str):
    run = cur["free"]
    status = free_status(run)
    if MODES.get(mode, "free") != "free":
        status = f"{NO_MODEL} Showing Free.\n\n{status}"
    return render(status, run["sections"], run["text"], run["markdown"], cur["json"])


def run_upload(path: str | None, mode: str, progress=gr.Progress()):  # noqa: B008 (how Gradio injects progress)
    hide = gr.Column(visible=False)
    if not path:
        return (*fail(), None, hide, "", [])
    try:
        run = free_run(path, progress)
    except gr.Error as exc:
        return (*fail(exc.message), None, hide, "", [])
    stem = re.sub(r"[^\w.-]+", "_", Path(path).stem)[:60] or "document"
    cur = {"kind": "upload", "free": run, "json": write_json(run.pop("data"), stem)}
    return (*upload_view(cur, mode), cur, hide, "", [])


# --- Example papers: Free live, Quick check and Standard saved ------------------------------------

def fetch(ex: dict) -> str:
    path = EXAMPLE_DIR / f"{ex['id']}.pdf"
    if path.exists():
        return str(path)
    for url in ex["pdf_urls"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "section-anything-space"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read(MAX_MB * 1024 * 1024 + 1)
        except OSError as exc:
            log.warning("example download failed: %s", type(exc).__name__)
            continue
        if data.startswith(b"%PDF-") and len(data) <= MAX_MB * 1024 * 1024:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
            return str(path)
    raise gr.Error("Could not download the example from arXiv right now. Try again, or upload a PDF.")


def live_example(ex: dict, progress) -> dict:
    """Download the example and run Free on it once per process; the text also serves the saved runs."""
    with _locks[ex["id"]]:
        if ex["id"] not in _live:
            run = free_run(fetch(ex), progress)
            saved = [[s[k] for k in ("number", "title", "level", "page_start")] for s in ex["runs"]["free"]["sections"]]
            run["same_as_saved"] = saved == [[s[k] for k in ("number", "title", "level", "page_start")]
                                             for s in run["sections"]]
            _live[ex["id"]] = run
        return _live[ex["id"]]


def example_info(ex: dict) -> tuple[str, list[list]]:
    arxiv = ex["id"]
    info = (f"*{ex['title']}*, {ex['authors']}, [arXiv:{arxiv}]({ex['arxiv']}), "
            f"[{ex['licence']}]({ex['licence_url']}). Downloaded from arXiv when you click; not modified.\n\n"
            f"**Why this paper:** {ex['why']}")
    rows = []
    for mode in ("free", "quick", "standard"):
        r = ex["runs"][mode]
        teds = f"{r['readoc_teds']:.1f}" if r.get("readoc_teds") is not None else "no answer key"
        cost = "$0" if not r["cost_usd"] else f"${r['cost_usd']:.4f}"
        rows.append([LABEL[mode], len(r["sections"]), teds, cost, f"{r['seconds']:.1f} s"])
    return info, rows


def example_view(ex: dict, mode: str, live: dict):
    mode = MODES.get(mode, "free")
    stem = f"{ex['id']}.{mode}"
    if mode == "free":
        note = "" if live["same_as_saved"] else (f". The saved Free run found {len(ex['runs']['free']['sections'])} "
                                                  "sections")
        status = free_status(live, ", run live on this Space") + note
        return render(status, live["sections"], live["text"], live["markdown"], write_json(live["data"], stem))
    run = ex["runs"][mode]
    text = live["text"]
    secs = [{k: s[k] for k in SECTION_KEYS} for s in run["sections"]]
    shown = [text_matches(text, s) for s in run["sections"]]
    tree = SectionTree(sections=secs, mode=mode, model=run["model"], pages=ex["pages"], usage=run["usage"],
                       seconds=run["seconds"])
    status = (f"**Saved run, section-anything {run['section_anything']}, {run['model']}, {run['date']}, cost "
              f"${run['cost_usd']:.4f}** · {len(secs)} sections · {run['calls']} model "
              f"call{'s' if run['calls'] != 1 else ''} · {run['seconds']:.1f} s on our machine. Computed once, "
              f"not on this Space: nothing is sent to a model here.")
    if not all(shown):
        status += (f"\n\nText shown for {sum(shown)} of {len(secs)} sections: the rest came out of this Space's "
                   "extraction differently from the saved run's, so only their headings are shown.")
    summary = tree.summary()
    data = {"section_anything": run["section_anything"], **summary, "usage": run["usage"],
            "saved_run": {"date": run["date"], "computed_on": "the maintainers' machine, not this Space"},
            "sections": [{**s, "text": text[s["start"]:s["end"]] if ok else None} for s, ok in zip(secs, shown, strict=True)]}
    return render(status, secs, text, tree.to_markdown(), write_json(data, stem), shown)


def example_handler(k: int):
    ex = EXAMPLES[k]

    def run_example(mode: str, progress=gr.Progress()):  # noqa: B008
        info, rows = example_info(ex)
        live = live_example(ex, progress)
        cur = {"kind": "example", "id": ex["id"]}
        return (*example_view(ex, mode, live), cur, gr.Column(visible=True), info, rows, fetch(ex))

    return run_example


def switch_mode(mode: str, cur: dict | None, progress=gr.Progress()):  # noqa: B008
    if not cur:
        status = "" if MODES.get(mode, "free") == "free" else f"Pick one of the three example papers. {NO_MODEL}"
        return status, "", [], gr.Dropdown(choices=[], value=None), section_view(None, None), None, None
    if cur["kind"] == "upload":
        return upload_view(cur, mode)
    ex = next(e for e in EXAMPLES if e["id"] == cur["id"])
    return example_view(ex, mode, live_example(ex, progress))


with gr.Blocks(title="Section Anything", delete_cache=(3600, 3600), analytics_enabled=False) as demo:
    gr.Markdown(HEADER)
    gr.Markdown(PRIVACY)
    with gr.Row():
        pdf = gr.File(label="PDF", file_types=[".pdf"], type="filepath", scale=2)
        with gr.Column(scale=1):
            mode = gr.Radio(list(MODES), value="Free", label="Mode",
                            info="Free runs live on any PDF. Quick check and Standard: saved runs on the examples.")
            buttons = [gr.Button(ex["button"], size="sm") for ex in EXAMPLES]
            gr.Markdown(EXAMPLES_NOTE)
    with gr.Column(visible=False) as ex_panel:
        ex_info = gr.Markdown()
        ex_table = gr.Dataframe(headers=["Mode", "Sections", "READoc heading-tree TEDS on this paper", "Cost",
                                         "Time (our machine)"],
                                datatype=["str", "number", "str", "str", "str"], interactive=False,
                                label=f"Saved runs on this paper (section-anything "
                                      f"{EXAMPLES[0]['runs']['quick']['section_anything']})")
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
    current = gr.State(time_to_live=3600)

    view = [status, tree_md, table, picker, text, json_file, doc]
    pdf.upload(run_upload, inputs=[pdf, mode], outputs=[*view, current, ex_panel, ex_info, ex_table],
               api_name="free_upload")
    for k, button in enumerate(buttons):
        button.click(example_handler(k), inputs=mode, outputs=[*view, current, ex_panel, ex_info, ex_table, pdf],
                     api_name=f"example_{k + 1}")
    mode.change(switch_mode, inputs=[mode, current], outputs=view, api_name="switch_mode")
    picker.change(section_view, inputs=[picker, doc], outputs=text, api_name=False)

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2, max_size=20).launch(max_file_size=f"{MAX_MB}mb")
