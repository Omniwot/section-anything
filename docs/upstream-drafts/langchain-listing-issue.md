# LangChain: integration listing issue (ready to paste, not filed)

Status, 27 Oct 2026: `langchain-section-anything` 0.1.0 is on PyPI
(https://pypi.org/project/langchain-section-anything/). The issue form was re-checked on
27 Oct 2026 and has the same fields as on 26 Oct.

Route (checked 26 Oct, re-checked 27 Oct 2026):

- New integrations are not accepted as PRs to any `langchain-ai` repository; they are published
  as independent PyPI packages named like `langchain-<name>`
  ([Contributing integrations](https://docs.langchain.com/oss/python/contributing/integrations-langchain),
  [Publish an integration](https://docs.langchain.com/oss/python/contributing/publish-langchain)).
  That guide also says the package "should live in its own repository"; ours is a subdirectory of
  the library's repository. The form accepts it (repository and docs URL are free fields), but a
  maintainer may ask about it.
- Listing is by an **issue form**, not a PR: the "Integration listing" form
  ([`06-integration-submission.yml`](https://github.com/langchain-ai/docs/blob/main/.github/ISSUE_TEMPLATE/06-integration-submission.yml))
  in `langchain-ai/docs`. A maintainer applies the `integration-run` label and automation opens
  the PR that adds a row to `scripts/data/integration_external_docs.yaml`. Manual listing PRs and
  new MDX pages are closed. Do not tag maintainers repeatedly.
- A hosted guide on docs.langchain.com needs 50,000 monthly PyPI downloads or a "featured" call
  by the maintainers; below that the listing is a row in the download table and a provider card
  linking to our own docs (the README below).
- Document loaders are in the "not encouraged" column (maintenance burden), but the form offers
  `document_loaders` and the YAML already lists 57 Python loaders, including PDF ones
  (`langchain-mineru`, `langchain-pymupdf4llm`, `langchain-opendataloader-pdf`, docling.rs).
- There is no standard test suite for loaders in `langchain-tests` (it covers chat models,
  embeddings, tools, retrievers, vector stores, caches, stores, indexers and sandboxes).
- Their LLM-use policy applies to AI-assisted contributions: read the text before filing.

Before filing: the docs URL below must show the package README on `main` (it does from 257eecd),
and the PyPI page above must load.

## Form fields

Open the form at https://github.com/langchain-ai/docs/issues/new/choose and pick
"Integration listing". Fields in the form's order:

**Title**

```text
[integration]: langchain-section-anything
```

**Display or class name**

```text
SectionAnythingLoader
```

**Language:** Python

**Component type:** `document_loaders`

**PyPI package name**

```text
langchain-section-anything
```

**npm package name:** leave blank.

**Docs URL**

```text
https://github.com/Omniwot/section-anything/tree/main/packages/langchain-section-anything
```

**Source repository**

```text
Omniwot/section-anything
```

**Short provider description** (one factual sentence, at most 160 characters; this one is 142)

```text
PDF loader that returns one Document per section, with heading path, level, pages and character span; rules-only mode runs locally at no cost.
```

**Capability flags (optional):** leave blank (the form asks for them only for chat models and
vector stores).

**Confirmations:** tick "The package is already published on PyPI and/or npm."

## Usage and what it adds

The form has no field for these; they are what the docs URL (the package README) shows. Use them
if a maintainer asks, or as a short comment on the issue.

```sh
pip install langchain-section-anything
```

```python
from langchain_section_anything import SectionAnythingLoader

docs = SectionAnythingLoader("paper.pdf").load()  # mode="free": rules only, no model, no cost
docs[2].metadata["heading_path"]  # ['1 Introduction', '1.1 Scope']
docs[2].metadata["page_start"], docs[2].metadata["page_end"]  # (1, 1)
```

What it adds: one `Document` per real section of the PDF, with its heading path, level, pages
and character span as metadata, instead of one per page (as page-based loaders such as
`PyPDFLoader` return). In our Qasper test (200 papers, 707 questions), section-bounded chunks
retrieved the gold evidence more often than fixed-size chunks, mostly because they are smaller,
but answer quality did not change
([write-up](https://github.com/Omniwot/section-anything/blob/main/docs/rag-qasper.md)).

## The row the automation should add

```yaml
python:
  document_loaders:
  - name: SectionAnythingLoader
    pypi: langchain-section-anything
    docs_url: https://github.com/Omniwot/section-anything/tree/main/packages/langchain-section-anything
```
