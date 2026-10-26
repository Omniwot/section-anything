# LangChain: integration listing issue (draft, not filed)

Route checked 26 Oct 2026:

- New integrations are not accepted as PRs to any `langchain-ai` repository; they are published
  as independent PyPI packages named like `langchain-<name>`
  ([Contributing integrations](https://docs.langchain.com/oss/python/contributing/integrations-langchain),
  [Publish an integration](https://docs.langchain.com/oss/python/contributing/publish-langchain)).
- Listing is by an **issue form**, not a PR: the "Integration listing" form
  ([`06-integration-submission.yml`](https://github.com/langchain-ai/docs/blob/main/.github/ISSUE_TEMPLATE/06-integration-submission.yml))
  in `langchain-ai/docs`. A maintainer applies the `integration-run` label and automation opens
  the PR that adds a row to `scripts/data/integration_external_docs.yaml`. Manual listing PRs and
  new MDX pages are closed. Do not tag maintainers repeatedly.
- A hosted guide on docs.langchain.com needs 50,000 monthly PyPI downloads or a "featured" call
  by the maintainers; below that the listing is a row in the download table and a provider card
  linking to our own docs.
- Document loaders are in the "not encouraged" column (maintenance burden), but the form offers
  `document_loaders` and the YAML already lists 57 Python loaders, including PDF ones
  (`langchain-mineru`, `langchain-pymupdf4llm`, `langchain-opendataloader-pdf`, docling.rs).
- There is no standard test suite for loaders in `langchain-tests` (it covers chat models,
  embeddings, tools, retrievers, vector stores, caches, stores, indexers and sandboxes).
- Their LLM-use policy applies to AI-assisted contributions: read the text before filing.

Prerequisites before filing: `langchain-section-anything` published on PyPI, and the docs URL
below live on `main`.

## Form fields

**Title:** `[integration]: langchain-section-anything`

| Field | Value |
|---|---|
| Display or class name | `SectionAnythingLoader` |
| Language | Python |
| Component type | `document_loaders` |
| PyPI package name | `langchain-section-anything` |
| npm package name | (blank) |
| Docs URL | `https://github.com/Omniwot/section-anything/tree/main/packages/langchain-section-anything` |
| Source repository | `Omniwot/section-anything` |
| Short provider description (≤160) | PDF loader that returns one Document per section, with heading path, level, pages and character span; rules-only mode runs locally at no cost. |
| Capability flags | (blank: none apply to loaders) |
| Confirmations | [x] The package is already published on PyPI and/or npm. |

The description is 142 characters.

## The row the automation should add

```yaml
python:
  document_loaders:
  - name: SectionAnythingLoader
    pypi: langchain-section-anything
    docs_url: https://github.com/Omniwot/section-anything/tree/main/packages/langchain-section-anything
```
