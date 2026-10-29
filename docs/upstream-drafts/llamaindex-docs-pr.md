# LlamaIndex: docs listing PR (opened 29 Oct 2026: run-llama/llama_index#23794)

Opened on 29 Oct 2026 as https://github.com/run-llama/llama_index/pull/23794 (branch
`Omniwot:patch-2`), with the change, title and body below unchanged. Waiting for review.

Status, 27 Oct 2026: `llama-index-readers-section-anything` 0.1.0 is on PyPI
(https://pypi.org/project/llama-index-readers-section-anything/). The integrations page, its
`## Data Loaders` section and the PR template were re-checked on 27 Oct 2026 and are unchanged
since 26 Oct, so the diff below still applies.

Route (checked 26 Oct, re-checked 27 Oct 2026):

- The monorepo takes **no new integration packages**: "New integrations should be maintained in
  their own repositories and published to PyPI independently. PRs that add a new
  `pyproject.toml` will be automatically closed"
  ([CONTRIBUTING.md](https://github.com/run-llama/llama_index/blob/main/CONTRIBUTING.md), since
  [#21139](https://github.com/run-llama/llama_index/pull/21139), March 2026).
- LlamaHub is retired: llamahub.ai points to the
  [integrations page](https://developers.llamaindex.ai/python/framework/community/integrations)
  ([#23070](https://github.com/run-llama/llama_index/pull/23070), Sept 2026). There is no
  submission form. The [Finding Data Connectors](https://developers.llamaindex.ai/python/framework/understanding/rag/loading/llamahub/)
  page tells users to search PyPI for `llama-index-readers-<source>`, so the package name is
  itself the main listing.
- A docs-only PR that links an outside project from the integrations page has been merged before:
  [#20083](https://github.com/run-llama/llama_index/pull/20083) (Kiln, Oct 2025). The page has no
  list of outside readers yet, so this PR proposes one; maintainers may decline or move it.
- PR template: [`.github/pull_request_template.md`](https://github.com/run-llama/llama_index/blob/main/.github/pull_request_template.md).
  Their AI-use guidelines ask contributors to say where AI was used and how it was checked.
- Package conventions followed (from in-repo readers such as `llama-index-readers-docling`):
  name `llama-index-readers-<name>`, import path `llama_index.readers.<name>` (namespace package),
  a `BaseReader` with `load_data(file, extra_info=None, fs=None)` so it works as a
  `SimpleDirectoryReader` file extractor, and a `[tool.llamahub]` table in `pyproject.toml`.

Before opening: the link below must show the package README on `main` (it does from 257eecd),
and the PyPI page above must load.

## Change

File: `docs/src/content/docs/framework/community/integrations.md`, section `## Data Loaders`.

```diff
 ## Data Loaders

 Data loaders (readers) live in the [`readers` directory](https://github.com/run-llama/llama_index/tree/main/llama-index-integrations/readers) of the LlamaIndex repo, one package per source. See the [data connectors guide](/python/framework/module_guides/loading/connector) for how to use them.

+Readers maintained in their own repositories:
+
+- [Section Anything](https://github.com/Omniwot/section-anything/tree/main/packages/llama-index-readers-section-anything) (`SectionAnythingReader`, `pip install llama-index-readers-section-anything`): one Document per PDF section, with heading path, pages and parent/child links.
+
 ## Agent Tools
```

## PR title

`docs: list the Section Anything PDF reader on the integrations page`

## PR body (their template)

````markdown
# Description

Docs-only change: adds a short "Readers maintained in their own repositories" list under
**Data Loaders** on the Integrations page, with one entry.

[Section Anything](https://github.com/Omniwot/section-anything) is an Apache-2.0 library that
finds the sections of a PDF (headings, levels, pages, character spans). Its reader,
`llama-index-readers-section-anything` on PyPI, returns one `Document` per section with the
heading path as flat metadata and PARENT/CHILD/PREVIOUS/NEXT relationships, and works as a
`SimpleDirectoryReader` file extractor. Its default mode uses rules only (no model, no network).

```sh
pip install llama-index-readers-section-anything
```

```python
from llama_index.core import SimpleDirectoryReader
from llama_index.readers.section_anything import SectionAnythingReader

reader = SectionAnythingReader()  # mode="free": rules only, no model, no cost
docs = reader.load_data("paper.pdf")
docs[2].metadata["heading_path"]  # '1 Introduction > 1.1 Scope'
# or for a folder: SimpleDirectoryReader("papers/", file_extractor={".pdf": reader}).load_data()
```

What it adds: one `Document` per real section of the PDF, with its heading path, pages and
character span, instead of one per page. In our Qasper test (200 papers, 707 questions),
section-bounded chunks retrieved the gold evidence more often than fixed-size chunks, mostly
because they are smaller, but answer quality did not change
([write-up](https://github.com/Omniwot/section-anything/blob/main/docs/rag-qasper.md)).

Since new integration packages are maintained outside this repo (CONTRIBUTING.md), a place on
this page to link them seemed useful; happy to move or reword it.

AI use: the reader and this text were drafted with an AI assistant and reviewed by me; the
reader's tests run offline on a generated PDF.

## New Package?

- [ ] Yes
- [x] No

## Version Bump?

- [ ] Yes
- [x] No

## Type of Change

- [x] This change requires a documentation update

(docs-only change)

## How Has This Been Tested?

- [ ] I added new unit tests to cover this change
- [x] I believe this change is already covered by existing unit tests

(docs-only; the link and the package were checked by hand)

## Suggested Checklist:

- [x] I have performed a self-review of my own code
- [x] I have made corresponding changes to the documentation
- [x] My changes generate no new warnings
````
