# llama-index-readers-section-anything

A LlamaIndex reader for [Section Anything](https://github.com/Omniwot/section-anything): it
finds the sections of a PDF (every heading, its level, its pages and its exact text) and returns
**one `Document` per section**, with the heading path in the metadata and parent/child links
between sections. The default mode runs locally with rules only, calls no model and costs
nothing.

## Install

```sh
pip install llama-index-readers-section-anything
# latest from GitHub:
pip install "git+https://github.com/Omniwot/section-anything#subdirectory=packages/llama-index-readers-section-anything"
```

Python 3.11+. Depends on `section-anything` and `llama-index-core` only.

## Example

```python
from llama_index.core import SimpleDirectoryReader
from llama_index.readers.section_anything import SectionAnythingReader

reader = SectionAnythingReader()  # mode="free": rules only, no model, $0
docs = reader.load_data("paper.pdf")
# or for a folder: SimpleDirectoryReader("papers/", file_extractor={".pdf": reader}).load_data()

doc = docs[2]
print(doc.text[:59])                 # '### 1.1 Scope\n\nSectioning splits a long document into parts'
print(doc.metadata["heading_path"])  # '1 Introduction > 1.1 Scope'
print(doc.metadata["page_start"], doc.metadata["page_end"])  # 1 1
```

Sections vary in length; `VectorStoreIndex.from_documents(docs)` splits long ones with its node
parser and keeps the metadata on every node.

## Options

`SectionAnythingReader(mode="free", *, include_heading=True, relationships=True, **opts)`, then
`load_data(file, extra_info=None, fs=None)` (also `lazy_load_data` and `aload_data`).

- `mode`: `free` (bookmarks, table of contents and typography rules; nothing leaves the machine),
  `quick` (a small model reviews candidate heading lines, about $0.07 per 1,000 pages),
  `standard` (a model reads every line) or `local:<ollama model>`. Over the per-document cost cap
  (default $0.50) a run is downgraded (standard → quick → free) or refused.
- `include_heading`: start each Document with its heading as a Markdown line (`## 1 Introduction`).
  With `False`, sections with no text of their own (a heading directly followed by a subheading)
  are skipped.
- `relationships`: set `PARENT` (the enclosing section), `CHILD`, `PREVIOUS` and `NEXT` between
  the Documents. Ids are `<file path>_part_<n>`, the format `SimpleDirectoryReader(filename_as_id=True)`
  uses, so the links survive it. A node parser starts fresh links between its own nodes; these
  are for using the sections as nodes directly.
- `**opts` go to `section_anything.section`: `api_key`, `base_url`, `model`, `max_usd`, `prices`,
  `over_budget`, `max_pages`, `extract_timeout`, `progress`, `settings`. Anything not given falls
  back to the `SECTIONANY_*` environment variables; see the
  [library README](https://github.com/Omniwot/section-anything/tree/main/packages/section-anything#configuration).
  Keys are never logged or put in metadata.
- `fs`: an fsspec filesystem (as `SimpleDirectoryReader` passes for remote files); the file is
  copied to a temporary local file first.

## Text and metadata

A Document's text is the section's own text, from its heading to the next heading, reflowed into
paragraphs with running headers and footers removed (the same text as `section-anything --body`).
Text before the first heading is a Document of its own (flag `front_matter`).

Metadata is flat (str, int, float or None), so it works with every vector store. `extra_info` is
merged over it.

| Key | Meaning |
|---|---|
| `file_path`, `file_name` | the PDF |
| `section_index` | position in the document's section list (0-based) |
| `title`, `number`, `level` | heading text, numbering as printed (`"3.1"` or `""`), 1 = top level |
| `heading_path` | headings from the outermost section down to this one, joined with `" > "` |
| `page_start`, `page_end` | 1-based pages |
| `start`, `end` | character range in the library's extracted text |
| `flags` | comma-separated, for example `doc_title`, `front_matter`, `generated_title` |
| `document_title` | the document's title, if found |
| `mode`, `model`, `document_cost_usd` | how the document was sectioned (after any downgrade) and what the whole document cost |

Embeddings see only `heading_path` and `document_title`; the LLM also sees `file_name`,
`page_start` and `page_end` (for citations). The other keys are excluded from both
(`excluded_embed_metadata_keys`, `excluded_llm_metadata_keys`) but stay available for filters.

## Licence

Apache-2.0. See `LICENSE` and `NOTICE`.
