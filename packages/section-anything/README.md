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
pip install "section-anything[langfuse]"  # optional Langfuse tracing
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/section-anything"
# from a checkout of the repository:
pip install -e ./packages/section-anything
```

Dependencies: pdfplumber and pdfminer.six (MIT), pypdfium2 (Apache-2.0 / BSD-3-Clause),
RapidFuzz (MIT), openai (Apache-2.0), pydantic and pydantic-settings (MIT). No PyMuPDF (AGPL).
The `anthropic` extra adds Anthropic's Python SDK (Apache-2.0).

## Modes

| Mode | What runs | Sent to a model | Cost per 1,000 pages |
|---|---|---|---|
| `free` (default) | PDF bookmarks or the printed table of contents as the outline, then typography and numbering rules; headings a complete-looking outline does not list are dropped | nothing | $0 |
| `quick` | the rules propose candidate heading lines; a small model keeps the real ones and sets levels | candidate lines and a 70-character peek at the next line | about $0.07 (`gpt-6-luna`) |
| `standard` | a model reads every line, with font hints, and marks where sections start and end | the document text | about $0.16 (`gpt-6-luna`, the default); $2.90 with `gpt-6.1-sol` |
| `local:<model>` | `quick`, answered by a local [Ollama](https://ollama.com) model | nothing leaves the machine | $0 |

Costs are measured averages at the built-in list prices; your documents may differ. The
`quick` and `standard` READoc scores below were measured with the default model, `gpt-6-luna`.

To run `standard` on the larger `gpt-6.1-sol`, set `SECTIONANY_STANDARD_MODEL=gpt-6.1-sol` or
pass `model="gpt-6.1-sol"` (`--model gpt-6.1-sol` on the command line). It costs about 18 times
as much. In one development-set comparison on READoc (98 papers and 100 READMEs, same code) it scored
5.8 points higher on READMEs (95% CI +2.1 to +9.6) and 0.9 higher on papers (CI -0.3 to +2.1,
not significant). This has not been confirmed on held-out documents.

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
| `SECTIONANY_PROVIDER` / `provider=` | (from the model) | `openai` or `anthropic`; unset, `claude-*` models use Anthropic and all others OpenAI-compatible endpoints (see [Providers](#providers)) |
| `SECTIONANY_API_KEY` / `api_key=` | (none) | Falls back to `OPENAI_API_KEY` only while `base_url` is OpenAI's own endpoint, and for Claude models to `ANTHROPIC_API_KEY` only while requests go to Anthropic's own endpoint |
| `SECTIONANY_BASE_URL` / `base_url=` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint with JSON-schema outputs; always passed explicitly to the client. Left at the default, Claude models go to `https://api.anthropic.com`; set it to put a gateway or relay in front of either provider |
| `SECTIONANY_QUICK_MODEL`, `SECTIONANY_STANDARD_MODEL` / `model=` | `gpt-6-luna`, `gpt-6-luna` | the models all published scores used; `gpt-6.1-sol` is also priced (see [Modes](#modes)) |
| `SECTIONANY_LOCAL_MODEL` | (none) | Ollama tag for `local` |
| `SECTIONANY_OLLAMA_BASE_URL` | `http://localhost:11434/v1` | |
| `SECTIONANY_PRICES` / `prices=` | built-in list | JSON `{"model": {"input": 2.0, "output": 10.0, "cached": 0.1}}`, USD per 1M tokens, merged over the built-in list. Optional: `cache_write`, `cache_write_1h`, and `long_prompt_tokens` with a `long_prompt` price for longer prompts |
| `SECTIONANY_MAX_USD_PER_DOC` / `max_usd=` | `0.50` | hard per-document cap |
| `SECTIONANY_OVER_BUDGET` / `over_budget=` | `downgrade` | or `fail` |
| `SECTIONANY_MAX_PAGES`, `SECTIONANY_MAX_CHARS`, `SECTIONANY_MAX_MB` | 500, 5,000,000, 100 | refused above these |
| `SECTIONANY_DEMOTE_UNLISTED_HEADINGS` / `demote_unlisted_headings=` | `["free"]` | modes in which sections that a complete-looking PDF outline does not list are dropped (JSON list; `[]` turns it off) |
| `SECTIONANY_EXTRACT_TIMEOUT_SECONDS` / `extract_timeout=` | 120 | extraction worker is killed after this |
| `SECTIONANY_EXTRACT_MEMORY_MB` | 4096 | worker memory limit (Linux only; 0 = none) |
| `SECTIONANY_ISOLATE_EXTRACTION` | `true` | run extraction in a separate process |
| `SECTIONANY_LLM_TIMEOUT_SECONDS`, `SECTIONANY_LOCAL_TIMEOUT_SECONDS` | 300, 600 | per model call |
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
  `tree.downgraded`, or refused with `CostCapExceeded` when `over_budget="fail"`.
- **Hard cap while running.** The cap is re-checked before every model call, and each call's
  output tokens are limited to what the remaining budget can pay for. A downgrade continues the
  same budget. The SDK's own retries are off; one retry on an unusable answer is counted.
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
