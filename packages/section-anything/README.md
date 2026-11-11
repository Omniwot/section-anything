# section-anything

> **Pre-release (0.1).** The API may change before 1.0.

Find the sections of a PDF: every heading, its level, the pages it spans and its exact
character range in the extracted text. One call, with a dial from free rules to an LLM that
reads the whole document, and a hard cost cap on every paid run.

```python
import section_anything

tree = section_anything.section("paper.pdf", mode="quick")
print(tree.to_markdown())
# # A Study of Sectioning
# ## 1 Introduction
# ### 1.1 Scope
# ## 2 Methods
print(tree.sections[1])
# {'number': '1', 'title': 'Introduction', 'level': 1, 'page_start': 1, 'page_end': 1,
#  'start': 22, 'end': 484, 'flags': []}
print(tree.summary())  # mode, model, pages, sections, calls, tokens, cost_usd, seconds
```

## Install

Python 3.11+:

```sh
pip install section-anything
pip install "section-anything[anthropic]" # optional: Claude models on Anthropic's own API
pip install "section-anything[docling]"   # optional: tree.to_docling_document()
pip install "section-anything[langfuse]"  # optional Langfuse tracing
pip install "section-anything[mcp]"       # optional MCP server: section-anything-mcp
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/section-anything"
# from a checkout of the repository:
pip install -e ./packages/section-anything
```

Dependencies: pdfplumber and pdfminer.six (MIT), pypdfium2 (Apache-2.0 / BSD-3-Clause),
RapidFuzz (MIT), openai (Apache-2.0), pydantic and pydantic-settings (MIT). No PyMuPDF (AGPL).
The `anthropic` extra adds Anthropic's Python SDK (Apache-2.0), the `docling` extra docling-core (MIT).

## Modes

| Mode | What runs | Sent to a model | Cost per 1,000 pages |
|---|---|---|---|
| `free` (default) | PDF bookmarks or the printed table of contents as the outline, then typography and numbering rules; headings a complete-looking outline does not list are dropped | nothing | $0 |
| `quick` | the rules propose candidate heading lines; a small model keeps the real ones and sets levels | candidate lines and a 70-character peek at the next line | about $0.07 (`gpt-6-luna`) |
| `standard` | a model reads every line, with font hints, and marks where sections start and end | the document text | about $0.16 (`gpt-6-luna`, the default); $2.90 with `gpt-6.1-sol` |
| `local:<model>` | `quick`, answered by a local [Ollama](https://ollama.com) model | nothing leaves the machine | $0 |
| `auto` | `free`, then `quick` only when Free is unsure of its headings | nothing, or what `quick` sends | $0 for documents Free is sure of, `quick`'s cost for the rest |

Costs are measured averages at the built-in list prices; your documents may differ. The
`quick` and `standard` READoc scores below were measured with the default model, `gpt-6-luna`.

To run `standard` on the larger `gpt-6.1-sol`, set `SECTIONANY_STANDARD_MODEL=gpt-6.1-sol` or
pass `model="gpt-6.1-sol"` (`--model gpt-6.1-sol` on the command line). It costs about 18 times
as much. In one development-set comparison on READoc (98 papers and 100 READMEs, same code) it scored
5.8 points higher on READMEs (95% CI +2.1 to +9.6) and 0.9 higher on papers (CI -0.3 to +2.1,
not significant). This has not been confirmed on held-out documents.

`auto` runs `free` first and gives every heading a `confidence` (see Output). When Free found
fewer than three headings, or their mean confidence is below 0.72 (`SECTIONANY_AUTO_THRESHOLD`),
the document goes to `quick` instead; `tree.auto` says which mode ran and why. It needs the same
API key as `quick` and stays within the same per-document cap. On READoc documents not used to
choose the threshold (an earlier version was scored on them once), it sent 28% of 905 arXiv papers
to `quick` and scored 68.4, level with `quick` (68.0; +0.5, 95% CI -0.5 to +1.6) and above `free`
(60.1); it sent 3.5% of 1,124 READMEs and scored 81.6, level with `free` (81.4) and above `quick`
(70.8). That is 29% of `quick`'s cost on those papers and 3% on those READMEs. Other kinds of
documents (laws, manuals, reports) have not been tested on held-out documents yet.

### Optional collection tuning (`heading_guidance`)

When you section many long documents of one type (one publisher's manuals, one series of
standards, one kind of legal instrument), you can give `standard` a short guidance text on what
the sections of that type look like. It is appended to the model's instructions on every call;
with no guidance (the default) the instructions are unchanged. `quick` (also `auto`'s quick step
and `local:<model>`) ignores it and logs one warning: with Claude Haiku 5.5's own sheets `quick` was
level overall (-0.012, 95% CI -0.046 to +0.020, 40 documents) but dropped real sections on UK Acts
(-0.134, CI -0.214 to -0.059).

Write the sheet once from two to five sample PDFs of the type, then use it with `standard`:

```python
from section_anything import Settings, section, write_guidance

sheet = write_guidance(["samples/a.pdf", "samples/b.pdf", "samples/c.pdf"], max_usd=1.00)
open("manuals-guidance.md", "w").write(sheet)
tree = section("manual.pdf", "standard", settings=Settings(heading_guidance=sheet))
```

```sh
section-anything guidance samples/*.pdf -o manuals-guidance.md --max-usd 1
SECTIONANY_HEADING_GUIDANCE="$(cat manuals-guidance.md)" section-anything manual.pdf --mode standard
```

`write_guidance` gives the model the full text of every sample, in the form `standard` shows it
(every line, numbered, with size and bold tags), and asks for a sheet of at most about 1,400 words
on what counts as a section in that type, which look-alikes do not, and hard cases. It always
includes two rules: a numbered paragraph or provision is a section even without a title, and index
letters, running heads and contents entries are not. Samples longer than one call (about 90,000
characters) are read in parts and the partial sheets merged; headings copied from one sample are
replaced by placeholders. It uses the `standard` model by default (`model=` or `--model` to change
it; write the sheet with the model you will run it on) and works with OpenAI-compatible models and
Claude models (the `anthropic` extra). The whole job is estimated first and refused when the
estimate is over `max_usd` (default the per-document cap, $0.50); each call is checked against the
cap again. Fewer than two samples log a warning. **The samples must represent the documents you
will run the sheet on**, including their less common parts (appendices, annexes, back matter).

These are the prompts measured in our tests: a model read the full text of two to five sample
documents of one type and wrote the sheet (at most about 1,400 words). Measured with
`standard` and the default `keep_strong`, section F1 against hand-checked section keys (research
findings F069 and F075, pre-registered):

- Claude Haiku 5.5 with sheets it wrote itself: +0.081 (95% CI +0.037 to +0.127) on 39 held-out
  documents of four types (UK Acts, RFCs, theses, GNU manuals); gpt-6-luna with its own sheets:
  +0.028 (CI +0.006 to +0.053) on 40.
- Claude Haiku 5.5 on 12 regulations of six publishers' formats (two test documents each): 0.836
  -> 0.931 (+0.096, CI +0.008 to +0.204). Almost all of the gain came from numbered provisions
  printed without titles, which the sheet told the model are sections.

A sheet can also make results worse. In the same regulations test one EU sheet, written from
samples whose annexes were mostly templates and tables, led the model to skip numbered groups in
another regulation's annex (that group's recall -0.084). In an earlier round, sheets gpt-6-luna
wrote from a prompt that did not say untitled numbered paragraphs are sections lowered its heading
F1 (-0.034, CI -0.064 to -0.006, 40 documents). Write a sheet from samples that represent the
documents you will run it on, check it on a few documents you know before relying on it, and
keep it general (no titles copied from the samples). It adds its length to every call's input, and the cost estimate counts it.

## Command line

```sh
section-anything paper.pdf                                   # free, Markdown headings
section-anything paper.pdf --mode quick --format json        # JSON with spans and cost
section-anything paper.pdf --mode standard --max-usd 0.5     # cap this document at $0.50
section-anything paper.pdf --mode local:qwen3:4b --body      # headings plus section text
section-anything paper.pdf --format json --body              # JSON with each section's text
section-anything paper.pdf --docling paper.json              # Docling's labels as hints (below)
section-anything guidance a.pdf b.pdf -o sheet.md            # guidance sheet for standard (above)
```

The result goes to stdout (or `-o FILE`), a one-line summary with the cost to stderr. Exit codes:
0 done, 2 configuration (for example no API key), 3 refused by the cost cap, 4 the PDF could not
be read. In folder mode (below): 0 every PDF done or skipped, 4 one or more PDFs failed (the others
are written), 2 configuration, before any PDF is read. API keys are read from the environment only,
never from the command line.

## Many PDFs

```python
from section_anything import section_many

for r in section_many(["a.pdf", "b.pdf", "c.pdf"], "quick", max_usd_total=2.00, max_usd=0.10):
    if r.ok:
        print(r.path, len(r.tree.sections), f"${r.cost_usd:.4f}")
    else:
        print(r.path, type(r.error).__name__, r.error)
```

- `section_many(pdfs, mode, *, max_usd_total=None, on_error="record", progress=None, **options)`
  takes paths and returns an iterator of `DocumentResult`: `path`, `tree` (or `None`), `error` (the
  exception, or `None`), `cost_usd` and `max_usd` (the cap the document ran with). Each PDF is read
  when its result is asked for, so outputs can be written as the run goes and breaking the loop stops
  it; `list(...)` collects them all. Other options go to `section` (`model`, `max_usd`,
  `over_budget`, `settings`, ...). `asection_many` is the async form.
- **Total budget.** With `max_usd_total`, each PDF's cap is the smaller of its own (`max_usd` or
  `SECTIONANY_MAX_USD_PER_DOC`) and what is left of the total. As the total runs out, paid runs are
  downgraded (standard -> quick -> free), or refused with `CostCapExceeded` when
  `over_budget="fail"`; once nothing is left, those refusals happen without reading the PDF. What is
  spent counts every model call, including those of a PDF that then failed. Free and local modes
  never spend.
- **Errors.** `on_error="record"` (the default) keeps going and records a `SectionAnythingError` in
  the PDF's result; `"raise"` raises the first one. A `ConfigError` (unknown mode, no API key, a
  model with no price) is always raised, before any PDF is read: it would fail every PDF the same way.
- PDFs run one at a time, in the order given. Extraction already runs in a worker process, and one at
  a time keeps a laptop usable and the total budget exact. `progress(fraction, message)` reports on
  the whole run.

On the command line, a folder or several PDFs run in folder mode, with one output per PDF in
`-o DIR`:

```sh
section-anything papers/ -o out/                              # out/<name>.md for each papers/*.pdf
section-anything papers/ -o out/ --recursive --format json    # subfolders too: out/sub/<name>.json
section-anything papers/ -o out/ --mode quick --max-usd-total 2  # at most $2 for the whole run
section-anything papers/ -o out/ --skip-existing              # resume: skip PDFs already written
section-anything a.pdf b.pdf -o out/                          # several files
```

- A folder's PDFs (`*.pdf` in any case; hidden files and folders left out) keep their place below it,
  so `papers/a/x.pdf` and `papers/b/x.pdf` give `out/a/x.md` and `out/b/x.md`. PDFs named on their
  own go straight into `out/`; names that would still clash (ignoring case) get `-2`, `-3`, ...
- Each output is written as soon as its PDF is done, through a temporary file, so a stopped run can
  be resumed with `--skip-existing`. A PDF that failed leaves no output and is retried.
- One line per PDF and a total (PDFs done, failed and skipped, model calls, cost) go to stderr,
  unless `-q`.
- `--recursive`, `--skip-existing` and `--max-usd-total` are for folder mode only; with a single
  file they exit with code 2. A single file works exactly as before.

## PDFs as bytes

`section`, `asection` and `extract_pdf` also take the PDF itself: `bytes`, `bytearray`,
`memoryview` or a binary file-like object (an open file, `io.BytesIO`, an upload stream). This is
for data platforms and serverless functions that hand over a file's bytes, not a path.

```python
tree = section_anything.section(pdf_bytes)  # from object storage, a request body or a table column
with open("paper.pdf", "rb") as f:
    tree = section_anything.section(f)      # read to the end once and left open
```

- The size cap is checked on the bytes before anything is written to disk. A stream over the cap
  is read to the end to measure it, but no more than the cap is kept in memory.
- Data without a `%PDF-` header in its first 1,024 bytes is refused with `PdfError`.
- The bytes then go to a private temporary file (its own folder, readable only by the current
  user), so the page, text, time and memory limits and the extraction worker apply as for a path.
  The file and its folder are removed afterwards, after an error or a timeout too.
- Errors call the document "PDF", never by the temporary file's name.
- `section_anything.PdfInput` is the type of everything these functions accept.

## Use with Docling

Opt-in, for when you already run [Docling](https://github.com/docling-project/docling). Pass its
output in one of two ways. Neither needs docling-core: the `DoclingDocument` object, its JSON as a
dict (`doc.export_to_dict()`) and a JSON file saved with `doc.save_as_json(...)` all work.

```python
from docling.document_converter import DocumentConverter

doc = DocumentConverter().convert("report.pdf").document

tree = section_anything.section("report.pdf", docling=doc)  # a PDF with a text layer: Docling's labels as hints
tree = section_anything.section(doc)                        # a scanned PDF: Docling's text as the lines
```

```sh
section-anything report.pdf --docling report.json    # hints
section-anything scanned.json                        # the Docling document itself
```

- **Hints** (`docling=`): the PDF is read as usual, so its fonts, bookmarks and printed table of
  contents still count. Lines Docling labels `section_header` or `title` become heading candidates
  whatever their style, and its page headers and footers are treated as running headers and
  footers. In `free` mode, styled lines Docling labels as body text, list items, captions or code
  are not taken as headings; lines outside every Docling box keep their own style. `quick` reviews
  the candidates as usual. `standard` reads every line anyway, so only the page headers and footers
  change what it sees. `auto` runs `free` with the hints and decides on that result.
- The hints must be Docling's output of the same PDF. When too few of the PDF's lines match the
  text in Docling's boxes, `section` raises `ConfigError`. A Docling run on some of the pages gives
  hints for those pages only.
- **A Docling document as the input** (`section(doc)`): for scanned PDFs, or any format Docling
  reads. Docling gives no font sizes, so heading levels come from Docling's own levels when they
  differ (its heading-hierarchy stage), and otherwise from the height of each heading's box.
  `tree.text` puts Docling's page headers first and its page footers last on each page. The page
  and character caps apply; the file-size cap and the extraction worker do not, as no PDF is read.
  With `auto`, Docling's levels are not counted as outline evidence for its own headings, so Free's
  confidence rests on numbering, style and heading names.
- `docling=` belongs to one PDF: `section_many` and folder mode refuse it. The MCP server does not
  take Docling output yet.

## Output

`tree.sections` is a list of dicts in reading order:

| Key | Meaning |
|---|---|
| `number`, `title` | numbering as printed (`"2.3"`, `"Chapter 4"`, or `""`) and the heading text |
| `level` | 1 = top level, 2 = its subsections, ... The document title (flag `doc_title`) is level 1, beside the top divisions (an Act's Parts), in every mode |
| `page_start`, `page_end` | 1-based physical pages |
| `start`, `end` | character range of the section's own text in `tree.text` (up to the next heading) |
| `flags` | `doc_title` (the document's own title), `front_matter` (text before the first heading), `generated_title` (`standard` wrote a title for text that has no printed heading), `kept_strong` (`quick` or `standard` left out a heading Free had strong evidence for, and it was put back: see `keep_strong` under Settings), `from_contents` (added by the opt-in contents check), and checks such as `start_marker_fuzzy`, `title_not_in_text`, `end_mismatch` |
| `confidence` | `free` only: 0 to 1, how much of Free's own evidence backs the heading (the PDF's outline lists it; its style is used on several pages and for little else; its number follows the previous one; a standard name such as References; not over ten words). A ranking within a document, fitted mostly on papers and READMEs, not a probability. `None` for front matter and in the model modes |
| `parent` | index in `tree.sections` of the nearest enclosing section, or `None` |
| `heading_path` | headings from the outermost enclosing section down to this one: `["1 Introduction", "1.1 Scope"]`. The document title's path is the title alone and front matter's is empty; neither is a parent |

- `tree.to_markdown()`: the document title as `#`, every other heading as `#` x (level + 1),
  capped at six. `to_markdown(body=True)` adds each section's text, reflowed into paragraphs,
  with running headers and footers removed.
- `tree.to_json()` / `tree.to_dict()`: the sections plus mode, model, pages, calls, tokens,
  cost, any downgrades and, for `auto`, `auto`: the mode it took (`path`), why (`reason`), Free's
  document `confidence` and the `threshold`. With `text=True` (`--format json --body` on the
  command line), each section also has `text`: exactly `tree.text[start:end]`, from its heading to
  the next heading.
- `tree.possible_misses` (also in `to_dict()`): lines with heading evidence that the result does not
  have as headings, best first, with page, text, the evidence in words and a score from 0 to 1, at
  most one per 5 pages. It is a short list to check by eye: on held-out documents it held 1% to 4% of
  the headings `free` missed, at 0.2 to 0.5 wrong entries per 10 pages (research finding F057).
- `section_anything.Section` and `TreeDict` type the sections and `to_dict()`;
  `SectionTree.json_schema()` returns the JSON Schema of the JSON output.
- `tree.extraction` holds the lines with their boxes (PDF points), for highlighting.

### Use Docling's or Unstructured's chunkers

Section Anything finds the headings but has no chunker that caps chunk size. Export the tree to
Unstructured's or Docling's format and run their section-aware chunkers on these headings.

Unstructured (`pip install unstructured`; the export itself needs no extra):

```python
from unstructured.chunking.title import chunk_by_title
from unstructured.staging.base import elements_from_dicts

tree = section_anything.section("paper.pdf")
elements = elements_from_dicts(tree.to_unstructured_elements("paper.pdf"))
chunks = chunk_by_title(elements, max_characters=1500)
```

Docling (`pip install "section-anything[docling]" "docling-core[chunking]"`):

```python
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker

tree = section_anything.section("paper.pdf")
doc = tree.to_docling_document("paper.pdf")
for chunk in HybridChunker().chunk(doc):
    print(chunk.meta.headings, chunk.text[:60])
```

- `to_unstructured_elements()` returns Unstructured's element dicts (its JSON format): a `Title`
  per heading, then a `NarrativeText` per body paragraph. A `Title`'s `category_depth` is 0 for
  the document title and level - 1 for other headings; `parent_id` points to the enclosing
  heading. Front matter has no `Title`. Each element has `page_number` and `coordinates`.
- `chunk_by_title` starts a chunk at every `Title`. By default it also merges short sections into
  one chunk; `combine_text_under_n_chars=0` keeps every section apart.
- `to_docling_document()` returns a `DoclingDocument`: the document title as a `TitleItem`, other
  headings as `SectionHeaderItem`s at their level, and body paragraphs as text items under their
  heading, with page, box and character span.
- `HybridChunker` gives each chunk `meta.headings`: the document title, then the section's
  `heading_path`. Its default tokenizer downloads a Hugging Face model; pass `tokenizer=` to use
  another.
- The body text is what `to_markdown(body=True)` prints. Tables, figures and lists come through as
  plain paragraphs.

## MCP server

`pip install "section-anything[mcp]"` adds `section-anything-mcp`, an MCP server on stdio for
Claude Code, Claude Desktop, Cursor and other MCP hosts:

```sh
claude mcp add --transport stdio section-anything -- section-anything-mcp --max-usd 0.10
```

| Tool | Returns |
|---|---|
| `section_pdf(path, mode="free", model=None, max_usd=None)` | the `to_dict()` output: every section with level, pages, `parent`, `heading_path` and span, no text |
| `read_sections(path, indexes, mode="free", ..., max_chars=20000)` | the chosen sections' text, reflowed as `--body` prints it (at most 50 per call) |
| `estimate_cost(path, max_usd=None)` | calls, tokens and dollars for each mode, without calling a model |

- All three are read-only. Results are cached (the last 8 PDFs and modes), so `read_sections` after
  `section_pdf` does not extract or pay again.
- Paid modes use the API keys in the server's environment and are capped per document by
  `--max-usd` (default 0.50); a call can lower that cap, not raise it, and `--max-usd 0` keeps every
  run in free mode.
- `--root DIR` (repeatable) limits the folders the tools may open; paths must be absolute `.pdf`
  files.
- Errors (no text layer, no API key, unknown mode, a path outside `--root`) come back as tool errors
  the agent can read.
- Section text is the PDF's content: the server's instructions tell the agent to treat it as data.

## Configuration

Every setting can be passed in code or set as an environment variable `SECTIONANY_<NAME>`.
Arguments win over the environment. **No `.env` file is read, and nothing is ever written to
`os.environ`.**

| Setting | Default | |
|---|---|---|
| `SECTIONANY_PROVIDER` / `provider=` | (from the model) | `openai` or `anthropic`; unset, `claude-*` models use Anthropic and all others OpenAI-compatible endpoints (see [Providers](#providers)) |
| `SECTIONANY_API_KEY` / `api_key=` | (none) | Falls back to `OPENAI_API_KEY` only while `base_url` is OpenAI's own endpoint, and for Claude models to `ANTHROPIC_API_KEY` only while requests go to Anthropic's own endpoint |
| `SECTIONANY_BASE_URL` / `base_url=` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint with JSON-schema outputs; always passed explicitly to the client. Left at the default, Claude models go to `https://api.anthropic.com`; set it to put a gateway or relay in front of either provider |
| `SECTIONANY_QUICK_MODEL`, `SECTIONANY_STANDARD_MODEL` / `model=` | `gpt-6-luna`, `gpt-6-luna` | the models all published scores used; `gpt-6.1-sol` is also priced (see [Modes](#modes)) |
| `SECTIONANY_LOCAL_MODEL` | (none) | Ollama tag for `local` |
| `SECTIONANY_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | |
| `SECTIONANY_PRICES` / `prices=` | built-in list | JSON `{"model": {"input": 2.0, "output": 10.0, "cached": 0.1}}`, USD per 1M tokens, merged over the built-in list. Optional: `cache_write`, `cache_write_1h`, and `long_prompt_tokens` with a `long_prompt` price for longer prompts |
| `SECTIONANY_MAX_USD_PER_DOC` / `max_usd=` | `0.50` | hard per-document cap |
| `SECTIONANY_OVER_BUDGET` / `over_budget=` | `downgrade` | or `fail` |
| `SECTIONANY_MAX_PAGES`, `SECTIONANY_MAX_CHARS`, `SECTIONANY_MAX_MB` | 500, 5,000,000, 100 | refused above these; the error says how to raise them |
| `SECTIONANY_DEMOTE_UNLISTED_HEADINGS` / `demote_unlisted_headings=` | `["free"]` | modes in which sections that a complete-looking PDF outline does not list are dropped (JSON list; `[]` turns it off) |
| `SECTIONANY_COVERAGE_RETRY` / `coverage_retry=` | `true` | `standard`: a window whose answer leaves many heading-like lines unlisted is read once more, and the answer that lists more of them is kept. At most one extra call per window, only while the per-document cap covers it and the windows after it; not counted in the up-front estimate. Each re-read is listed in `tree.usage["coverage_retries"]` |
| `SECTIONANY_KEEP_STRONG` / `keep_strong=` | `ask` | `quick` and `standard` (and `local`): Free's headings with evidence that needs no model (the outline lists them, their number follows the previous one, a standard name such as References) that the model's answer leaves out are put back when the outline lists them, and otherwise shown to the model once more in one call per document to keep or reject (`ask`); `restore` puts them all back without a call, `off` leaves the answer as it is. Decisions are in `tree.usage["kept_strong"]`. On a random 980 of the held-out READoc documents, Claude Haiku 5.5, `ask` raised `quick`'s heading-tree TEDS by 1.76 (95% CI 1.36 to 2.18) |
| `SECTIONANY_CONTENTS_CHECK` / `contents_check=` | `[]` | modes (JSON list of `free`, `quick`, `standard`) in which bookmark and contents entries that no section covers are looked for in the body and added (flag `from_contents`); entries not found go to `tree.possible_misses`. Off by default: it removed under 1% of `free`'s missed headings on held-out documents |
| `SECTIONANY_HEADING_GUIDANCE` / `Settings(heading_guidance=...)` | (empty) | `standard` only: text appended to the model's instructions on every call, for documents of one type (see [Optional collection tuning](#optional-collection-tuning-heading_guidance)). Off by default; a sheet written from unrepresentative samples can lower accuracy. `quick`, `auto` and `local` ignore it and log a warning |
| `SECTIONANY_EXTRACT_TIMEOUT_SECONDS` / `extract_timeout=` | 120 | extraction worker is killed after this |
| `SECTIONANY_EXTRACT_MEMORY_MB` | 4096 | worker memory limit (Linux only; 0 = none) |
| `SECTIONANY_ISOLATE_EXTRACTION` | `true` | run extraction in a separate process |
| `SECTIONANY_LLM_TIMEOUT_SECONDS`, `SECTIONANY_LOCAL_TIMEOUT_SECONDS` | 300, 600 | total time per call, including streaming (cloud models, local models); a call past it is stopped and retried once like any timeout, so one call can take up to twice this |
| `SECTIONANY_STORE_PROMPTS` | `false` | keep prompt text in call records passed to a `Usage(sink=...)` |
| `SECTIONANY_LANGFUSE` | `false` | trace calls with Langfuse (needs the `langfuse` extra and Langfuse's own keys); OpenAI-client calls only, Claude calls are not traced |

Or build a `Settings` object once: `section(pdf, "quick", settings=Settings(max_usd_per_doc=1.0))`.
Async code can `await section_anything.asection(...)`.

## Providers

`quick` and `standard` call a chat model through the OpenAI Python client
(`chat.completions.parse` with a JSON schema), or, for Claude models, through Anthropic's own
Python SDK (`messages.stream` with a JSON schema in `output_config.format`). `local` calls Ollama.

| Provider | Status | Setup |
|---|---|---|
| OpenAI | tested (all benchmarks) | `OPENAI_API_KEY`, or `SECTIONANY_API_KEY` |
| Ollama (local) | tested | `--mode local:<tag>`; no key, nothing leaves the machine |
| Anthropic (native API) | supported; `standard` tested on development documents only (below) | `pip install "section-anything[anthropic]"`, `ANTHROPIC_API_KEY`, a Claude model (below) |
| Other OpenAI-compatible endpoints: Azure OpenAI, OpenRouter, Groq, Together, vLLM, LM Studio, a LiteLLM proxy | not tested | base URL, key, model and price (below) |
| Google Gemini | not tested | no native client; use an OpenAI-compatible endpoint or gateway that meets the requirements below |

### Anthropic (Claude)

Claude models are opt-in: the defaults stay `gpt-6-luna`. A model id starting with `claude-` is
sent to Anthropic's own API; set `SECTIONANY_PROVIDER=openai` to send it to an OpenAI-compatible
gateway instead. Priced built in: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`,
`claude-fable-5-1`.

```bash
pip install "section-anything[anthropic]"
export ANTHROPIC_API_KEY="..."                       # or SECTIONANY_API_KEY
export SECTIONANY_STANDARD_MODEL="claude-haiku-5-5"  # or SECTIONANY_QUICK_MODEL
section-anything paper.pdf --mode standard
section-anything paper.pdf --mode quick --model claude-haiku-5-5
```

```python
tree = section_anything.section("paper.pdf", mode="standard", model="claude-haiku-5-5")
```

- Each request sends the schema as `output_config.format` and `output_config.effort="medium"`,
  streams the answer, and checks `stop_reason`:
  a refusal or an answer cut off at `max_tokens` is retried once and counted against the cost cap.
  No `temperature`, `top_p`, `top_k` or `thinking` setting is sent.
- Effort is `"medium"` where OpenAI models get `"low"`: OpenAI's `"low"` still reasons, but in one
  test Claude Haiku 5.5 at `"low"` did not think at all and returned only the paper's title as a
  section; at `"medium"` it found the headings.
- The models need the effort setting: older Claude models without it, such as Claude Haiku 4.5,
  are not supported.
- Keys never cross providers: `OPENAI_API_KEY` is never sent to Anthropic, nor `ANTHROPIC_API_KEY`
  to OpenAI, and a key that is plainly the other provider's is refused rather than sent.
  `SECTIONANY_BASE_URL` puts a gateway or local relay in front of either provider.
- Anthropic's OpenAI-compatible endpoint is not used: it ignores `response_format` and
  `reasoning_effort`, which these modes need.

`standard` on development documents only (98 READoc arXiv papers and 100 GitHub READMEs, same
code, October 2026; differences against `gpt-6-luna` are paired, with 95% CIs):

| Model | Papers | READMEs | Cost per 1,000 pages | Time per document |
|---|---|---|---|---|
| `gpt-6-luna` (default) | 69.4 | 72.0 | $0.16 | 11.9 s |
| `claude-haiku-5-5` | 69.2 (-0.2, -3.2 to +2.4) | 72.0 (+0.0, -3.8 to +4.0) | $0.49 | 26.6 s |
| `claude-sonnet-5-5` | 65.0 (-4.5, -7.8 to -1.7) | 63.6 (-8.4, -14.0 to -3.4) | $4.04 | 8.5 s |

Claude Haiku 5.5 ties the default at about 3 times the cost. Claude Sonnet 5.5 at `"medium"` did
not think on any document and sometimes returned only one or two sections. Not confirmed on
held-out documents; `quick`, Opus and Fable were not tested.

### Other OpenAI-compatible endpoints

An endpoint works if it:

- supports structured outputs (`response_format` with a strict JSON schema);
- accepts `max_completion_tokens` and `reasoning_effort` (`"low"`), which every request sends;
- has a price set for the model. A model with no price is refused, so the cost cap can always be
  enforced.

```bash
export SECTIONANY_BASE_URL="https://openrouter.ai/api/v1"   # the provider's OpenAI-compatible URL
export SECTIONANY_API_KEY="..."                              # the provider's key
export SECTIONANY_QUICK_MODEL="vendor/model-name"            # or SECTIONANY_STANDARD_MODEL
export SECTIONANY_PRICES='{"vendor/model-name": {"input": 0.15, "output": 0.60}}'  # USD per 1M tokens
section-anything paper.pdf --mode quick
```

```python
tree = section_anything.section(
    "paper.pdf", mode="quick",
    base_url="https://openrouter.ai/api/v1", api_key="...", model="vendor/model-name",
    prices={"vendor/model-name": {"input": 0.15, "output": 0.60}},
)
```

Benchmark numbers are for the OpenAI models above; other models, Claude included, can score
differently. If you run one, results are welcome in an issue.

## Costs and caps

- **Unknown prices are refused.** A cloud model with no price (built-in, `SECTIONANY_PRICES` or
  `prices=`) is refused before the PDF is read, so the cap can always be enforced. Local models
  are free.
- **Estimate first.** Before a paid mode runs, its cost is estimated from the document. Over
  `max_usd`, the run is downgraded (standard -> quick -> free) and the downgrade is reported in
  `tree.downgraded`, or refused with `CostCapExceeded` when `over_budget="fail"`. A model you pass
  (`model=`, `--model`) stays with the run: Standard on it goes to Quick on it.
- **Hard cap while running.** The cap is re-checked before every model call, and each call's
  output tokens are limited to what the remaining budget can pay for. A downgrade continues the
  same budget. The SDK's own retries are off; one retry on an unusable answer is counted.
- **A total for many PDFs.** `section_many(..., max_usd_total=)` and `--max-usd-total` lower each
  PDF's cap to what is left of the total (see [Many PDFs](#many-pdfs)).
- The built-in prices are list prices from October 2026. Check your provider's prices and
  override them with `SECTIONANY_PRICES`.
- Claude prices include cache reads and writes, and Claude Haiku 5.5's higher price for prompts
  over 100,000 tokens (each request is priced on its own prompt). For Claude models the up-front
  estimate counts more tokens for the same text (1.5 characters per token, the low end of what
  Claude's token counter gave on 200 READoc documents) and adds thinking at the effort sent (half
  the prompt's tokens at `"medium"`, within each call's 32,000-token output limit), so it errs high:
  a long document on a pricier model such as Claude Sonnet 5.5 can be downgraded before it runs.
  The cap during the run is enforced from each response's token counts.

## Handling untrusted PDFs

- File size and page count are checked first, from the PDF's page tree, without parsing any
  page content.
- Text extraction runs in a separate Python process: the text size is counted (PDFium) before
  layout analysis starts, the process is killed at the time limit, has a memory limit on Linux,
  runs in an empty temporary directory, and inherits no API keys. It returns JSON, not pickles.
- Document text is treated as untrusted in every prompt; model output is validated against a
  schema and clipped (strings to 300 characters, lists to 2,000 items). In `quick`, a heading
  title the model rewrote is replaced by the printed line; in `standard`, titles the model wrote
  for headingless text are flagged `generated_title`.
- Log messages and errors name the error type, HTTP status and error code, never prompt or
  response text.

## Benchmarks (summary)

Heading-tree similarity (TEDS, 0-100, higher is better) with
[READoc](https://github.com/icip-cas/READoc)'s own scoring code, October 2026. Docling and MinerU
convert whole documents (layout, tables, figures, formulas, OCR); these numbers compare only the
heading tree. The full tables, methods and per-document results are in the repository:
`site/data/results.js` (rendered by the project site in `site/`) and `corpus/results/`.

| READoc arXiv papers not used during development | Docs | Score |
|---|---|---|
| Section Anything `standard` (gpt-6-luna) | 905 | **70.0** |
| Section Anything `quick` (gpt-6-luna) | 905 | 68.0 |
| Section Anything `free` | 905 | 60.0 |
| Docling 2.140 (heading hierarchy on) | 905 | 49.4 |

`quick` is release 0.1.2 and `free` release 0.1.5. 0.1.1 found the abstract's heading (journals often set it
small, bold or run into the first line): +2.4 to `free` and +3.7 to `quick` in a pre-registered
held-out test (0.1.0: 54.8 and 63.9). 0.1.2 keeps a section number that the PDF extractor split
off its title ("1" | "Introduction"): +0.7 to `free` (95% CI 0.5 to 1.0) and +0.5 to `quick` (95%
CI 0.4 to 0.8; +1.7 on the 291 papers it changes) in a second pre-registered test (0.1.1: 57.2 and
67.4).
0.1.5 gives back matter (References, Acknowledgements, Appendix) and appendix sections the level of the
numbered sections: +2.1 to `free` (95% CI 1.7 to 2.4; 136 papers better, 4 worse) in a fourth
pre-registered test on these papers (0.1.4: 57.9); READMEs unchanged.
`standard` uses none of these. See the
[changelog](https://github.com/Omniwot/section-anything/blob/main/CHANGELOG.md).

On the same 905 papers with MinerU's cloud service (3.4.4, VLM): our `standard` 70.0, our `quick`
68.0, MinerU + its LLM title levels (gpt-6.1-sol) 64.8 (paired difference: `standard` +5.1, 95% CI
4.0 to 6.2, or +2.8 without the 154 papers where that step, run by us on gpt-6.1-sol, returned no
parsable levels and kept MinerU's raw levels; `quick` +3.1, 95% CI 2.1 to 4.1, but level without
those papers: +1.0, 95% CI −0.03 to 2.0),
MinerU cloud alone 53.9, Docling 49.4.

On 1,112 bookmarked READoc GitHub READMEs not used in development, `free` scores 81.9 against
Docling's 75.5; Docling reaches 79.7 with the opt-in outline check we proposed upstream
([docling#5002](https://github.com/docling-project/docling/issues/5002)), the same idea as
`free`'s outline check. On 27 UK government reports never used in development (answer keys from each report's HTML version), the outline check improved `free` by +5.7 (95% CI +0.4 to +12.2; 43.1 → 48.8; measured on 0.1.0).

Where others win: on the 1,124 held-out READoc READMEs our `quick` and `standard` only tie with
Docling (about 75); on the 905 held-out papers Docling scored higher than `standard` on 103 papers
and lower on 773 (by more than 0.5 points); Nougat, an OCR model trained on arXiv, has the highest
published READoc arXiv score (88.5 in the READoc paper, older tool versions; we have not run it).
Docling and MinerU also read scanned pages with OCR; Section Anything needs a text layer.

## Integrations

Separate packages on PyPI, each depending only on this library and the framework's core package
([usage](https://github.com/Omniwot/section-anything#integrations)):

```sh
pip install langchain-section-anything            # LangChain loader: one Document per section
pip install llama-index-readers-section-anything  # LlamaIndex reader: one Document per section
pip install lightrag-section-anything             # LightRAG parser engines
```

## Limitations

- Reads the PDF's text layer. Scanned PDFs need OCR first, or Docling's output of them
  ([Use with Docling](#use-with-docling)).
- Tables, figures and equations are not structured; their text is part of the section text.
- `free` relies on bookmarks or a printed table of contents for its best results; without them it
  is weaker than `quick` on papers. When the bookmarks look complete it drops headings they do not
  list, so bookmarks that stop at the top levels lose real deeper headings (about 6% of READMEs
  lose more than 5 points); set `SECTIONANY_DEMOTE_UNLISTED_HEADINGS='[]'` to turn this off.
- `quick` and `standard` send text to the provider you configure; results vary slightly between
  runs.
- `local` uses Ollama's OpenAI-compatible endpoint, whose default context is small (4k tokens on
  most laptops) and truncates silently. Candidate batches are kept small, but give the model a
  larger context (for example a Modelfile with `num_ctx 8192`) for long documents. Quality with
  local models has not been measured.
- Python 3.11 or newer.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
