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
pip install "section-anything[langfuse]"  # optional Langfuse tracing
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/section-anything"
# from a checkout of the repository:
pip install -e ./packages/section-anything
```

Dependencies: pdfplumber and pdfminer.six (MIT), pypdfium2 (Apache-2.0 / BSD-3-Clause),
RapidFuzz (MIT), openai (Apache-2.0), pydantic and pydantic-settings (MIT). No PyMuPDF (AGPL).

## Modes

| Mode | What runs | Sent to a model | Cost per 1,000 pages |
|---|---|---|---|
| `free` (default) | PDF bookmarks or the printed table of contents as the outline, then typography and numbering rules; headings a complete-looking outline does not list are dropped | nothing | $0 |
| `quick` | the rules propose candidate heading lines; a small model keeps the real ones and sets levels | candidate lines and a 70-character peek at the next line | about $0.07 (`gpt-6-luna`) |
| `standard` | a model reads every line, with font hints, and marks where sections start and end | the document text | about $0.16 (`gpt-6-luna`), $2.90 (`gpt-6.1-sol`, the default) |
| `local:<model>` | `quick`, answered by a local [Ollama](https://ollama.com) model | nothing leaves the machine | $0 |

Costs are measured averages at the built-in list prices; your documents may differ.

## Command line

```sh
section-anything paper.pdf                                   # free, Markdown headings
section-anything paper.pdf --mode quick --format json        # JSON with spans and cost
section-anything paper.pdf --mode standard --max-usd 0.5     # cap this document at $0.50
section-anything paper.pdf --mode local:qwen3:4b --body      # headings plus section text
```

The result goes to stdout (or `-o FILE`), a one-line summary with the cost to stderr. Exit codes:
0 done, 2 configuration (for example no API key), 3 refused by the cost cap, 4 the PDF could not
be read. API keys are read from the environment only, never from the command line.

## Output

`tree.sections` is a list of dicts in reading order:

| Key | Meaning |
|---|---|
| `number`, `title` | numbering as printed (`"2.3"`, `"Chapter 4"`, or `""`) and the heading text |
| `level` | 1 = top level, 2 = its subsections, ... |
| `page_start`, `page_end` | 1-based physical pages |
| `start`, `end` | character range of the section's own text in `tree.text` (up to the next heading) |
| `flags` | `doc_title` (the document's own title), `front_matter` (text before the first heading), `generated_title` (`standard` wrote a title for text that has no printed heading), and checks such as `start_marker_fuzzy`, `title_not_in_text`, `end_mismatch` |

- `tree.to_markdown()`: the document title as `#`, every other heading as `#` x (level + 1),
  capped at six. `to_markdown(body=True)` adds each section's text, reflowed into paragraphs,
  with running headers and footers removed.
- `tree.to_json()` / `tree.to_dict()`: the sections plus mode, model, pages, calls, tokens,
  cost and any downgrades.
- `tree.extraction` holds the lines with their boxes (PDF points), for highlighting.

## Configuration

Every setting can be passed in code or set as an environment variable `SECTIONANY_<NAME>`.
Arguments win over the environment. **No `.env` file is read, and nothing is ever written to
`os.environ`.**

| Setting | Default | |
|---|---|---|
| `SECTIONANY_API_KEY` / `api_key=` | (none) | Falls back to `OPENAI_API_KEY` only while `base_url` is OpenAI's own endpoint |
| `SECTIONANY_BASE_URL` / `base_url=` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint with JSON-schema outputs; always passed explicitly to the client |
| `SECTIONANY_QUICK_MODEL`, `SECTIONANY_STANDARD_MODEL` / `model=` | `gpt-6-luna`, `gpt-6.1-sol` | |
| `SECTIONANY_LOCAL_MODEL` | (none) | Ollama tag for `local` |
| `SECTIONANY_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | |
| `SECTIONANY_PRICES` / `prices=` | built-in list | JSON `{"model": {"input": 2.0, "output": 10.0, "cached": 0.1}}`, USD per 1M tokens, merged over the built-in list |
| `SECTIONANY_MAX_USD_PER_DOC` / `max_usd=` | `0.50` | hard per-document cap |
| `SECTIONANY_OVER_BUDGET` / `over_budget=` | `downgrade` | or `fail` |
| `SECTIONANY_MAX_PAGES`, `SECTIONANY_MAX_CHARS`, `SECTIONANY_MAX_MB` | 500, 5,000,000, 100 | refused above these |
| `SECTIONANY_DEMOTE_UNLISTED_HEADINGS` / `demote_unlisted_headings=` | `["free"]` | modes in which sections that a complete-looking PDF outline does not list are dropped (JSON list; `[]` turns it off) |
| `SECTIONANY_EXTRACT_TIMEOUT_SECONDS` / `extract_timeout=` | 120 | extraction worker is killed after this |
| `SECTIONANY_EXTRACT_MEMORY_MB` | 4096 | worker memory limit (Linux only; 0 = none) |
| `SECTIONANY_ISOLATE_EXTRACTION` | `true` | run extraction in a separate process |
| `SECTIONANY_DEMOTE_UNLISTED_HEADINGS` | `[]` (off) | JSON list of modes (`free`, `quick`, `standard`): when the PDF's bookmarks look complete, drop sections they do not list (`section_anything.outline_check`) |
| `SECTIONANY_LLM_TIMEOUT_SECONDS`, `SECTIONANY_LOCAL_TIMEOUT_SECONDS` | 300, 600 | per model call |
| `SECTIONANY_STORE_PROMPTS` | `false` | keep prompt text in call records passed to a `Usage(sink=...)` |
| `SECTIONANY_LANGFUSE` | `false` | trace calls with Langfuse (needs the `langfuse` extra and Langfuse's own keys) |

Or build a `Settings` object once: `section(pdf, "quick", settings=Settings(max_usd_per_doc=1.0))`.
Async code can `await section_anything.asection(...)`.

## Costs and caps

- **Unknown prices are refused.** A cloud model with no price (built-in, `SECTIONANY_PRICES` or
  `prices=`) is refused before the PDF is read, so the cap can always be enforced. Local models
  are free.
- **Estimate first.** Before a paid mode runs, its cost is estimated from the document. Over
  `max_usd`, the run is downgraded (standard -> quick -> free) and the downgrade is reported in
  `tree.downgraded`, or refused with `CostCapExceeded` when `over_budget="fail"`.
- **Hard cap while running.** The cap is re-checked before every model call, and each call's
  output tokens are limited to what the remaining budget can pay for. A downgrade continues the
  same budget. The SDK's own retries are off; one retry on an unusable answer is counted.
- The built-in prices are list prices from October 2026. Check your provider's prices and
  override them with `SECTIONANY_PRICES`.

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
[READoc](https://github.com/icip-cas/READoc)'s own scoring code, October 2026. The full tables,
methods and per-document results are in the repository: `site/data/results.js` (rendered by the
project site in `site/`) and `corpus/results/`.

| READoc arXiv papers not used during development | Docs | Score |
|---|---|---|
| Section Anything `standard` (gpt-6-luna) | 905 | **70.0** |
| Section Anything `quick` (gpt-6-luna) | 905 | 63.9 |
| Section Anything `free` | 905 | 54.8 |
| Docling 2.140 (heading hierarchy on) | 905 | 49.4 |

On the 313 of those papers that MinerU's cloud service had processed: our `standard` 71.6,
MinerU + its LLM title levels (gpt-6.1-sol) 67.2 (+4.4 for us, 95% CI 2.5 to 6.4), our `quick`
66.1, MinerU cloud alone 57.3, Docling 49.2.

On 1,112 bookmarked READoc GitHub READMEs not used in development, `free` scores 81.9 against
Docling's 75.5. On 27 UK government reports never used in development (answer keys from each report's HTML version), the outline check improved `free` by +5.7 (95% CI +0.4 to +12.2; 43.1 → 48.8).

Where others win: our `quick` and `standard` only tie with Docling on READMEs (about 75); Nougat, an OCR model trained on arXiv, scores far higher
on arXiv papers (88.5, published).

## Limitations

- Reads the PDF's text layer. Scanned PDFs need OCR first.
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
