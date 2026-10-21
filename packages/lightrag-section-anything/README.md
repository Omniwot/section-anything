# lightrag-section-anything

> **Pre-release.** Not yet published on PyPI.

LightRAG parser engines that turn a PDF into heading-aware blocks (`.blocks.jsonl`) using the
[`section-anything`](../section-anything) library, so LightRAG's heading-based chunker ("P") and
its heading context work on PDFs without a MinerU or Docling service.

| Engine | Runs | Cost per 1,000 pages |
|---|---|---|
| `sectionany_free` | rules (bookmarks, contents, typography) | $0 |
| `sectionany_quick` | rules + a small model reviewing candidate lines | about $0.07 |
| `sectionany_standard` | a model reading all lines | about $0.16 (gpt-6-luna) to $2.90 (gpt-6.1-sol) |
| `sectionany_local` | quick-style review on a local Ollama model (`SECTIONANY_LOCAL_MODEL`) | $0 |
| `sectionany` | the mode in `SECTIONANY_MODE` (default `free`) | |

Setup: install both packages next to `lightrag-hku` (1.5.7 or later, below 1.7), in a dedicated
environment:

    pip install ./packages/section-anything ./packages/lightrag-section-anything

    LIGHTRAG_PARSER=pdf:sectionany_quick-P,pdf:sectionany-P,*:native-teP,*:legacy-R

Settings are the library's `SECTIONANY_*` environment variables (see its README): API key
(`SECTIONANY_API_KEY`, else `OPENAI_API_KEY` for OpenAI's endpoint), models, prices,
`SECTIONANY_MAX_USD_PER_DOC` (default 0.50), `SECTIONANY_OVER_BUDGET=downgrade|fail`,
`SECTIONANY_MAX_PAGES` (500), `SECTIONANY_MAX_MB` (100), `SECTIONANY_EXTRACT_TIMEOUT_SECONDS`
(120). The plugin adds `SECTIONANY_MODE`, `SECTIONANY_SYNTHETIC_TITLES` and
`MAX_PARALLEL_PARSE_SECTIONANY` (default 2). Nothing is written to the process environment, so
LightRAG's own model settings are untouched. Cost, model and mode per document are reported in
LightRAG's document status (`parse_warnings`) and in `<name>.sectionany.json`.

Tests: `SECTIONANY_TEST_PDF=<some.pdf> pytest packages/lightrag-section-anything/tests`.

Not yet: tables as tables, images, OCR, re-levelling MinerU/Docling output, a section-path
prefix inside embeddings (needs LightRAG's chunker plugins, 1.5.8+).
