# Section Anything

Find the real sections of a PDF: every heading, its level, the pages it spans and the exact text
under it. Built for RAG pipelines and document tools that need structure, with a dial from free
rules to an LLM that reads the whole document, and a hard cost cap on every paid run.

> **Pre-release (0.1).** Not on PyPI yet; install from this repository. The API may change before 1.0.

```python
import section_anything

tree = section_anything.section("paper.pdf", mode="quick")
print(tree.to_markdown())
# # A Study of Sectioning
# ## 1 Introduction
# ### 1.1 Scope
# ## 2 Methods
print(tree.summary())  # mode, model, pages, sections, calls, tokens, cost_usd, seconds
```

## Why

PDF converters guess headings from how a line looks, so paper titles, author names, captions and
theorem statements often come out as sections, and real subsections get the wrong level. Anything
that chunks or navigates by headings inherits those mistakes. Section Anything combines the PDF's
own outline (bookmarks) and printed table of contents, typography and numbering rules, and
optionally a model that reviews or reads the text.

## Results

Heading-tree similarity (TEDS, 0–100, higher is better) on [READoc](https://github.com/icip-cas/READoc)
with READoc's own scoring code, October 2026. Papers not used while developing the method:

| READoc arXiv papers (held out) | Docs | TEDS |
|---|---|---|
| Section Anything `standard` (gpt-6-luna) | 905 | **70.0** |
| Section Anything `quick` (gpt-6-luna) | 905 | 63.9 |
| Section Anything `free` (no model) | 905 | 54.8 |
| Docling 2.140 (heading hierarchy on) | 905 | 49.4 |

On the 313 of those papers that MinerU's cloud had processed: our `standard` 71.6, MinerU + its own
LLM title levels (gpt-6.1-sol) 67.2 (+4.4 for us, 95% CI +2.5 to +6.4), our `quick` 66.1, MinerU
alone 57.3, Docling 49.2.

On GitHub READMEs, `free` leads: on 1,112 bookmarked READMEs not used in development it scores
81.9 against Docling's 75.5 (79.7 with the change we proposed upstream,
[docling#5002](https://github.com/docling-project/docling/issues/5002)).
On 27 UK government reports never used in development (answer keys from each report's HTML
version), the outline check improved `free` by +5.7 (95% CI +0.4 to +12.2; 43.1 → 48.8).

**Where others win:** on READMEs our `quick` and `standard` only tie with Docling (about 75). Nougat,
an OCR model trained on arXiv, scores far higher on arXiv papers (88.5, published). Better headings improved RAG retrieval in our
[Qasper test](docs/rag-qasper.md) but not answer quality.

## Settings and cost

| Mode | What runs | Sent to a model | Cost per 1,000 pages |
|---|---|---|---|
| `free` (default) | bookmarks or the printed contents as the outline, then typography and numbering rules; headings a complete-looking outline does not list are dropped | nothing | $0 |
| `quick` | rules propose candidate heading lines; a small model keeps the real ones and sets levels | candidate lines only | about $0.07 (gpt-6-luna) |
| `standard` | a model reads every line, with font hints, and marks where sections start and end | the document text | about $0.16 (gpt-6-luna) to $2.90 (gpt-6.1-sol) |
| `local:<model>` | `quick`, answered by a local Ollama model | nothing leaves the machine | $0 |

Every paid run is estimated first and capped (default $0.50 per document); over the cap it
downgrades (standard → quick → free) or fails, as you choose.

## Install

Python 3.11 or newer:

```sh
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/section-anything"
```

Command line:

```sh
section-anything paper.pdf                                # free, Markdown headings
section-anything paper.pdf --mode quick --format json     # JSON with spans and cost
section-anything paper.pdf --mode standard --max-usd 0.5  # cap this document at $0.50
```

API keys come from the environment only (`SECTIONANY_API_KEY`, or `OPENAI_API_KEY` for OpenAI's
endpoint); any OpenAI-compatible endpoint works. Full options, output format and the security
model for untrusted PDFs: [packages/section-anything/README.md](packages/section-anything/README.md).

## With LightRAG

[`packages/lightrag-section-anything`](packages/lightrag-section-anything) registers parser
engines (`sectionany_free`, `sectionany_quick`, `sectionany_standard`, `sectionany_local`) so
LightRAG's heading-based chunker works on PDFs without a MinerU or Docling service.

## Limitations

- Reads the PDF's text layer; scanned PDFs need OCR first.
- Tables, figures and equations are not structured; their text stays in the section text.
- `free` is best when the PDF has bookmarks or a printed table of contents. When the bookmarks look
  complete, it drops headings they do not list; if the bookmarks stop at the top levels, real deeper
  headings are lost (about 6% of READMEs lose more than 5 points). Turn this off with
  `SECTIONANY_DEMOTE_UNLISTED_HEADINGS='[]'`.
- `quick` and `standard` send text to the provider you configure.

## Repository

| Path | What it is |
|---|---|
| `packages/section-anything/` | the library and CLI (Apache-2.0) |
| `packages/lightrag-section-anything/` | LightRAG parser plugin |
| `backend/`, `frontend/` | a demo web app: upload a PDF, see the sections highlighted ([docs/app.md](docs/app.md)) |
| `site/` | project website and benchmark tables (`site/data/results.js`) |
| `corpus/` | our test corpus: answer keys, results and the tools that rebuild it (no PDFs stored) |
| `docs/` | write-ups: [RAG on Qasper](docs/rag-qasper.md), [the Docling contribution](docs/docling-pr/), plans and a paper draft |

## Licence

Code: Apache-2.0 (`LICENSE`, `NOTICE`). The data under `corpus/` keeps its sources' licences: see
[`corpus/DATA-LICENSES.md`](corpus/DATA-LICENSES.md).
