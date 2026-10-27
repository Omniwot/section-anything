# Upstream listing drafts (not filed)

Drafts for listing the two integration packages where RAG builders look. The packages are on
PyPI; neither draft has been filed or opened.

| Framework | Package | Listing route | Draft |
|---|---|---|---|
| LangChain | `langchain-section-anything` | issue form in `langchain-ai/docs`; automation adds a YAML row | [langchain-listing-issue.md](langchain-listing-issue.md) |
| LlamaIndex | `llama-index-readers-section-anything` | PyPI name (their docs say to search PyPI); optional docs PR to the integrations page | [llamaindex-docs-pr.md](llamaindex-docs-pr.md) |

Order:

1. Done: the integrations are on `main` (the docs URLs point there).
2. Done: trusted publishers on PyPI for each project (details in
   [RELEASING.md](../../RELEASING.md#integration-packages)).
3. Done, 27 Oct 2026: `langchain-section-anything` 0.1.0 and
   `llama-index-readers-section-anything` 0.1.0 are on PyPI.
4. Still to do: file the LangChain listing issue, then open the LlamaIndex docs PR.
