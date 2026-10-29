# Upstream listing drafts

Drafts for listing the two integration packages where RAG builders look. The packages are on
PyPI. LangChain lists the loader (merged 29 Oct 2026); the LlamaIndex docs PR is open.

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
4. Done, 29 Oct 2026: LangChain listing issue
   [langchain-ai/docs#7112](https://github.com/langchain-ai/docs/issues/7112), merged by their
   automation as [langchain-ai/docs#7171](https://github.com/langchain-ai/docs/pull/7171).
5. Open since 29 Oct 2026: LlamaIndex docs PR
   [run-llama/llama_index#23794](https://github.com/run-llama/llama_index/pull/23794).
