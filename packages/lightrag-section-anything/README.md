# lightrag-section-anything

LightRAG parser engines that turn a PDF into heading-aware blocks (`.blocks.jsonl`) using the
[`section-anything`](https://github.com/Omniwot/section-anything) library, so LightRAG's
heading-based chunker ("P") and its heading context work on PDFs without a MinerU or Docling
service.

## Install

```sh
pip install lightrag-section-anything
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/lightrag-section-anything"
```

Python 3.11+. Depends on `section-anything` and `lightrag-hku` (1.5.7 or later, below 1.7); the
LightRAG server needs `lightrag-hku[api]`. The engines register through LightRAG's
`lightrag.parsers` entry point, which the LightRAG server (`lightrag-server`) and the parser debug
CLI (`python -m lightrag.parser.cli`) load at startup. When you embed LightRAG as a library, call
`load_third_party_parsers()` from `lightrag.parser.plugins` first.

## Engines

| Engine | Runs | Cost per 1,000 pages |
|---|---|---|
| `sectionany_free` | rules (bookmarks, contents, typography) | $0 |
| `sectionany_quick` | rules + a small model reviewing candidate lines | about $0.07 |
| `sectionany_standard` | a model reading all lines | about $0.16 (gpt-6-luna, the default); $2.90 with gpt-6.1-sol |
| `sectionany_local` | quick-style review on a local Ollama model (`SECTIONANY_LOCAL_MODEL`) | $0 |
| `sectionany` | the mode in `SECTIONANY_MODE` (default `free`) | |

## Use

Route PDFs to an engine with LightRAG's `LIGHTRAG_PARSER` rules, for example:

    LIGHTRAG_PARSER=pdf:sectionany_quick-P,pdf:sectionany-P,*:native-teP,*:legacy-R

Settings are the library's `SECTIONANY_*` environment variables (see its README): API key
(`SECTIONANY_API_KEY`, else `OPENAI_API_KEY` for OpenAI's endpoint or `ANTHROPIC_API_KEY` for
Claude models), models, prices,
`SECTIONANY_MAX_USD_PER_DOC` (default 0.50), `SECTIONANY_OVER_BUDGET=downgrade|fail`,
`SECTIONANY_MAX_PAGES` (500), `SECTIONANY_MAX_MB` (100), `SECTIONANY_EXTRACT_TIMEOUT_SECONDS`
(120). The plugin adds `SECTIONANY_MODE`, `SECTIONANY_SYNTHETIC_TITLES` and
`MAX_PARALLEL_PARSE_SECTIONANY` (default 2). Nothing is written to the process environment, so
LightRAG's own model settings are untouched. Cost, model and mode per document are reported in
LightRAG's document status (`parse_warnings`) and in `<name>.sectionany.json`.

Tests: `SECTIONANY_TEST_PDF=<some.pdf> pytest packages/lightrag-section-anything/tests`.

Not yet: tables as tables, images, OCR, re-levelling MinerU/Docling output, a section-path
prefix inside embeddings (needs LightRAG's chunker plugins, 1.5.8+).
