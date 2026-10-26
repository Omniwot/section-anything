# LlamaIndex: docs listing PR (draft, not opened)

Route checked 26 Oct 2026:

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

Prerequisites before opening: `llama-index-readers-section-anything` published on PyPI, and the
link below live on `main`.

## Change

File: `docs/src/content/docs/framework/community/integrations.md`, section `## Data Loaders`.

```diff
 ## Data Loaders

 Data loaders (readers) live in the [`readers` directory](https://github.com/run-llama/llama_index/tree/main/llama-index-integrations/readers) of the LlamaIndex repo, one package per source. See the [data connectors guide](/python/framework/module_guides/loading/connector) for how to use them.

+Readers maintained in their own repositories:
+
+- [Section Anything](https://github.com/Omniwot/section-anything/tree/main/packages/llama-index-readers-section-anything) (`SectionAnythingReader`, `llama-index-readers-section-anything`): one Document per PDF section, with heading path, pages and parent/child links.
+
 ## Agent Tools
```

## PR title

`docs: list the Section Anything PDF reader on the integrations page`

## PR body (their template)

```markdown
# Description

Docs-only change: adds a short "Readers maintained in their own repositories" list under
**Data Loaders** on the Integrations page, with one entry.

[Section Anything](https://github.com/Omniwot/section-anything) is an Apache-2.0 library that
finds the sections of a PDF (headings, levels, pages, character spans). Its reader,
`llama-index-readers-section-anything` on PyPI, returns one `Document` per section with the
heading path as flat metadata and PARENT/CHILD/PREVIOUS/NEXT relationships, and works as a
`SimpleDirectoryReader` file extractor. Its default mode uses rules only (no model, no network).

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
```
