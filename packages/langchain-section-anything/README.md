# langchain-section-anything

A LangChain document loader for [Section Anything](https://github.com/Omniwot/section-anything):
it finds the sections of a PDF (every heading, its level, its pages and its exact text) and
returns **one `Document` per section**, with the heading path in the metadata. The default mode
runs locally with rules only, calls no model and costs nothing.

## Install

```sh
pip install langchain-section-anything
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/langchain-section-anything"
```

Python 3.11+. Depends on `section-anything` and `langchain-core` only.

## Example

```python
from langchain_section_anything import SectionAnythingLoader

loader = SectionAnythingLoader("paper.pdf")  # mode="free": rules only, no model, $0
docs = loader.load()  # or loader.lazy_load(), await loader.aload()

doc = docs[2]
print(doc.page_content[:59])         # '### 1.1 Scope\n\nSectioning splits a long document into parts'
print(doc.metadata["heading_path"])  # ['1 Introduction', '1.1 Scope']
print(doc.metadata["page_start"], doc.metadata["page_end"])  # 1 1
```

Sections vary in length; to cap chunk size, split the Documents further (for example with
`RecursiveCharacterTextSplitter.split_documents`), which keeps the metadata on every chunk.

## Options

`SectionAnythingLoader(file_path, mode="free", *, include_heading=True, **opts)`

- `file_path`: a path, or a list of paths.
- `mode`: `free` (bookmarks, table of contents and typography rules; nothing leaves the machine),
  `quick` (a small model reviews candidate heading lines, about $0.07 per 1,000 pages),
  `standard` (a model reads every line) or `local:<ollama model>`. Over the per-document cost cap
  (default $0.50) a run is downgraded (standard → quick → free) or refused.
- `include_heading`: start each Document with its heading as a Markdown line (`## 1 Introduction`).
  With `False`, sections with no text of their own (a heading directly followed by a subheading)
  are skipped.
- `**opts` go to `section_anything.section`: `api_key`, `base_url`, `model`, `max_usd`, `prices`,
  `over_budget`, `max_pages`, `extract_timeout`, `progress`, `settings`. Anything not given falls
  back to the `SECTIONANY_*` environment variables; see the
  [library README](https://github.com/Omniwot/section-anything/tree/main/packages/section-anything#configuration).
  Keys are never logged or put in metadata.

## Text and metadata

A Document's text is the section's own text, from its heading to the next heading, reflowed into
paragraphs with running headers and footers removed (the same text as `section-anything --body`).
Text before the first heading is a Document of its own (flag `front_matter`).

| Key | Meaning |
|---|---|
| `source` | the PDF path |
| `section_index` | position in the document's section list (0-based) |
| `title`, `number`, `level` | heading text, numbering as printed (`"3.1"` or `""`), 1 = top level |
| `heading_path` | list of headings from the outermost section down to this one |
| `page_start`, `page_end` | 1-based pages |
| `start`, `end` | character range in the library's extracted text |
| `flags` | for example `doc_title`, `front_matter`, `generated_title` |
| `document_title` | the document's title, if found |
| `mode`, `model`, `document_cost_usd` | how the document was sectioned (after any downgrade) and what the whole document cost |

`heading_path` and `flags` are lists. For a vector store that accepts only scalar metadata, join
them (`" > ".join(...)`) or drop them with `filter_complex_metadata` from
`langchain_community.vectorstores.utils` before indexing.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
