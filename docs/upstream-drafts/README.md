# Upstream listing drafts (not filed)

Drafts for listing the two integration packages where RAG builders look. Nothing here has been
published, filed or opened.

| Framework | Package | Listing route | Draft |
|---|---|---|---|
| LangChain | `langchain-section-anything` | issue form in `langchain-ai/docs`; automation adds a YAML row | [langchain-listing-issue.md](langchain-listing-issue.md) |
| LlamaIndex | `llama-index-readers-section-anything` | PyPI name (their docs say to search PyPI); optional docs PR to the integrations page | [llamaindex-docs-pr.md](llamaindex-docs-pr.md) |

Order:

1. Merge the integrations to `main` (the docs URLs point there).
2. On PyPI, add a pending trusted publisher for each new project: owner `Omniwot`, repository
   `section-anything`, workflow `release-integrations.yml`, environment `pypi` (the environment
   the library already uses). Details in [RELEASING.md](../../RELEASING.md#integration-packages).
3. Push the tags `langchain-section-anything-v0.1.0` and
   `llama-index-readers-section-anything-v0.1.0`; check both PyPI pages and a clean
   `pip install` of each.
4. File the LangChain listing issue, then open the LlamaIndex docs PR.
