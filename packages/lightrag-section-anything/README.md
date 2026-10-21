# lightrag-section-anything (private, not published)

LightRAG parser engines that turn a PDF into heading-aware blocks (`.blocks.jsonl`) using
Section Anything, so LightRAG's heading-based chunker ("P") and its heading context work on PDFs
without a MinerU or Docling service.

| Engine | Runs | Cost per 1,000 pages |
|---|---|---|
| `sectionany_free` | rules (bookmarks, contents, typography) | $0 |
| `sectionany_quick` | rules + a cheap model reviewing candidate lines | about $0.04 |
| `sectionany_standard` | a model reading all lines | about $2.33 |
| `sectionany_local` | quick-style review on a local Ollama model | $0 |
| `sectionany` | the mode in `SECTIONANY_MODE` (default `free`) | |

Setup (development): install into a dedicated environment next to `lightrag-hku`, and point
`SECTIONANY_BACKEND` at `section-anything/backend` (the sectioning core is not packaged yet).

    LIGHTRAG_PARSER=pdf:sectionany_quick-P,pdf:sectionany-P,*:native-teP,*:legacy-R

Settings: `SECTIONANY_MODE`, `SECTIONANY_API_KEY` (else `OPENAI_API_KEY`),
`SECTIONANY_QUICK_MODEL`, `SECTIONANY_STANDARD_MODEL`, `SECTIONANY_LOCAL_MODEL`,
`SECTIONANY_MAX_USD_PER_DOC` (default 0.50), `SECTIONANY_OVER_BUDGET=downgrade|fail`,
`SECTIONANY_MAX_PAGES` (default 500). Cost, model and mode per document are reported in
LightRAG's document status (`parse_warnings`) and in `<name>.sectionany.json`.

Not yet: tables as tables, images, OCR, re-levelling MinerU/Docling output, a section-path
prefix inside embeddings (needs LightRAG's chunker plugins, 1.5.8+).
