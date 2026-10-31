# Changelog

Releases of the `section-anything` library on [PyPI](https://pypi.org/project/section-anything/).
Scores are READoc heading-tree TEDS (0-100) with READoc's own scoring code.

## 0.1.6 (2026-10-31)

- **The same PDF now gives the same text every time.** pdfminer's layout analysis breaks ties
  between equally distant text boxes (table cells, for example) by `id()`, a memory address, so
  such lines could come out in a different order in each process: one arXiv paper gave 3 different
  texts in 6 extractions. Extraction now breaks those ties by the boxes' order (a copy of pdfminer's
  `group_textboxes` with that one change, used for our pages only; pdfminer itself is not patched).
  On the 200 READoc development documents, 25 (22 papers, 3 READMEs) now extract to a different line
  order than before: the same lines with the same total length, 2 to 45 of them moved. `free` finds
  the same headings on all 25; `quick`'s candidate lines are unchanged on 21. No held-out score was
  re-measured. `EXTRACTOR_VERSION` and `TEXT_COMPATIBLE_SINCE` are now 5: character offsets saved
  from earlier versions may not match the new text for such documents.
- **Every section has `parent` and `heading_path`.** `parent` is the index of the nearest enclosing
  section (or `None`); `heading_path` lists the headings from the outermost enclosing section down to
  this one (`["1 Introduction", "1.1 Scope"]`). The document title and front matter are outside the
  hierarchy, as in the LangChain and LlamaIndex loaders. They are in `tree.sections`, `to_dict()`,
  `to_json()` and the command line's JSON.
- **Section text in the JSON:** `to_dict(text=True)`, `to_json(text=True)` and
  `section-anything paper.pdf --format json --body` add each section's `text`, exactly
  `tree.text[start:end]`.
- **Typed output:** `section_anything.Section` and `TreeDict` (TypedDicts) describe the sections and
  `to_dict()`; `SectionTree.json_schema()` gives the JSON Schema of the JSON output, for tool
  definitions and validation. New dependency: `typing-extensions>=4.6` (already installed with
  pydantic).

- **MCP server:** `pip install "section-anything[mcp]"` adds `section-anything-mcp` (stdio, `mcp>=2.3,<3`)
  with three read-only tools: `section_pdf` (the heading tree), `read_sections` (chosen sections'
  text, reflowed) and `estimate_cost`. Free mode by default; paid modes use the server's API keys and
  are capped per document by `--max-usd` (a call can lower it, not raise it); `--root` limits the
  folders it may read.
- **Safety limits say how to raise them.** Every limit's error (pages, file size, text size,
  extraction time, the worker's memory, the per-document cost cap) now says it is a safety limit and
  gives the command-line flag, Python setting and environment variable that raise it, set to a value
  that would fit this PDF (the page count, the file size, an estimate from the pages read so far), for
  example `PDF has 5000 pages; the limit is 500 (a safety limit; to allow more, use --max-pages 5000,
  max_pages=5000 in Python, or SECTIONANY_MAX_PAGES=5000)`. The MCP server adds that its limits are set
  in its environment.
- A folder given as the PDF is refused with a `PdfError` instead of a pypdfium2 traceback.
- **Agent skill:** `skills/section-anything/SKILL.md` teaches an agent the command-line workflow
  (outline first, then only the sections it needs, and when a paid mode is worth asking for).

## 0.1.5 (2026-10-28)

- **`free`: back matter and appendices sit beside the numbered sections** (the cause left open in
  0.1.2). Without a usable PDF outline, `free` gave numbered headings their numbering depth as
  level and unnumbered ones the rank of their font style, where the paper title takes the top
  rank. References, Acknowledgements, Appendix and appendix sections lettered without a dot ("A
  Broader Impact") therefore came out one level below "1 Introduction", and "A.1" subsections one
  level below "2.1". A style that two or more numbered headings share, on two or more pages, now
  takes their numbering depth, and the other styles fit in around it by size, as they already did
  around an outline. Without such a style holding top-level numbers (1, 2, 3), the levels are the
  style ranks as before, so documents without numbered headings are unchanged. Pre-registered
  held-out test, READoc heading-tree TEDS, `free` 0.1.4 vs this change, paired (95% bootstrap CI):
  905 arXiv papers 57.9 -> 60.0, +2.05 (CI +1.70 to +2.42; 136 better, 765 the same, 4 worse at
  +-0.5 points); 1,124 GitHub READMEs 81.4 -> 81.4, +0.00 (one README changed). `quick` and
  `standard` are unchanged: they do not use `free`'s levels and their prompts are byte-identical. A
  run downgraded to `free` gets the same change.

## 0.1.4 (2026-10-28)

- **Claude models on Anthropic's own API**, as a provider next to OpenAI: `pip install
  "section-anything[anthropic]"` (`anthropic>=2.0,<3`), then `ANTHROPIC_API_KEY` and a Claude
  model, for example `SECTIONANY_STANDARD_MODEL=claude-haiku-5-5` or `model="claude-haiku-5-5"`.
  Requests stream through `messages.stream` with the JSON schema in `output_config.format` and
  `output_config.effort="medium"` (at `"low"`, Claude Haiku 5.5 skipped thinking and returned one
  section where there were 21); refusals and answers cut off at `max_tokens` are retried once and
  counted against the cost cap. The defaults are unchanged (`gpt-6-luna` for `quick` and
  `standard`), and OpenAI requests are sent exactly as before. `standard` on development documents
  only (98 READoc papers and 100 READMEs, same code): `claude-haiku-5-5` tied `gpt-6-luna` (papers
  -0.2, 95% CI -3.2 to +2.4; READMEs +0.0, CI -3.8 to +4.0) at about 3 times the cost;
  `claude-sonnet-5-5` scored lower (papers -4.5, CI -7.8 to -1.7; READMEs -8.4, CI -14.0 to -3.4)
  at about 26 times the cost. Not confirmed on held-out documents; `quick`, Opus and Fable were
  not tested.
- **Provider selection**: `SECTIONANY_PROVIDER` / `provider=` / `--provider` (`openai` or
  `anthropic`); unset, `claude-*` model ids go to Anthropic and all others to OpenAI-compatible
  endpoints. A `claude-*` model served by an OpenAI-compatible gateway now needs
  `SECTIONANY_PROVIDER=openai`.
- **Keys never cross providers**: for Claude models the key is `api_key=`, then
  `SECTIONANY_API_KEY`, then `ANTHROPIC_API_KEY` (only while requests go to Anthropic's own
  endpoint). `OPENAI_API_KEY` is never sent to Anthropic, nor `ANTHROPIC_API_KEY` to OpenAI, and a
  key that is plainly the other provider's is refused before anything is sent.
  `SECTIONANY_BASE_URL` works for both, so a gateway or local relay can sit in front of either.
- **Prices**: `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens; $0.50 / $2.50 for prompts over
  100,000 tokens), `claude-sonnet-5-5` ($2 / $10), `claude-opus-5-5` ($4 / $20) and
  `claude-fable-5-1` ($10 / $50), with cache-read and cache-write prices. `Price` gains optional
  `cache_write`, `cache_write_1h`, `long_prompt_tokens` and `long_prompt`.
- A downgrade (standard -> quick -> free) skips a mode whose model has no key configured, for
  example a Claude `standard` with no OpenAI key for `quick`.
- `lightrag-section-anything` 0.1.1: `ANTHROPIC_API_KEY` also makes the `quick` and `standard`
  engines ready; it now needs `section-anything>=0.1.4`.
- **Up-front estimate for Claude models**: the cost estimate checked against `max_usd` before a
  run now counts Claude prompts at 1.5 characters per token (OpenAI models: 3.6, unchanged) and adds
  an allowance for thinking at the effort sent (half the prompt's tokens at `"medium"`, capped at each
  call's 32,000-token output limit). Before, a Claude estimate could be about half the real cost, so
  the per-document cap and the downgrade could let an over-budget Claude run start.

## 0.1.3 (2026-10-27)

- **`standard` now defaults to `gpt-6-luna`** (was `gpt-6.1-sol`). Every published `standard`
  score (held-out READoc: 70.0 on 905 arXiv papers, 75.5 on 1,124 GitHub READMEs) and its cost
  (about $0.16 per 1,000 pages) was measured on `gpt-6-luna`, so the default now matches them.
  `gpt-6.1-sol` (about $2.90 per 1,000 pages, roughly 18 times the cost) is still priced and can be
  chosen with `SECTIONANY_STANDARD_MODEL=gpt-6.1-sol`, `model="gpt-6.1-sol"` or `--model
  gpt-6.1-sol`. On development documents only (98 READoc papers and 100 READMEs, same code) it scored
  5.8 points higher on READMEs (95% CI +2.1 to +9.6) and 0.9 higher on papers (CI -0.3 to +2.1,
  not significant); this is not confirmed on held-out documents. `quick` (`gpt-6-luna`) and `free` are unchanged.
- The command line's `--model` help names the default models.

## 0.1.2 (2026-10-26)

- **Section numbers split off their titles are kept.** The PDF extractor (pdfminer) splits a line
  where a space is wider than twice the letters beside it, which happens after a section number
  when the title starts with a narrow letter: "1" | "Introduction". The bare "1" looked like a page
  number and was dropped, so the heading lost its number and, in `free`, its level ("###
  Introduction" next to "## 2 Related Work"). Such a number (same baseline, size and weight as the
  title right after it) is now joined to its title in `free` and `quick`, also when a bookmark
  names only the title. Pre-registered held-out test on 905 READoc arXiv papers: `free` +0.7 (95%
  CI +0.5 to +1.0); `quick` +1.7 (95% CI +1.2 to +2.3) on the 291 papers it changes, +0.5 (95% CI
  +0.4 to +0.8) on all; GitHub READMEs unchanged. Held-out scores are now `free` 57.9 (was 57.2) and
  `quick` 68.0 (was 67.4). `standard` is unchanged.
- Not fixed: in `free`, unnumbered headings that share the section style (References, appendices
  lettered without a dot) can still come out one level below the numbered sections when the paper
  title takes the largest style. This is a separate cause.

## 0.1.1 (2026-10-26)

- **Abstract headings are found.** Journals often set "Abstract" bold but smaller than body text,
  or run it into the abstract's first line ("Abstract—We study…", "Abstract. Let…"), so the rules
  never offered it as a heading. On pages 1-2 it is now a candidate whatever its size, in `free`
  and `quick`; `free` gives it the level of the section that follows. Pre-registered held-out test
  on 905 READoc arXiv papers: `free` +2.4 (95% CI +2.0 to +2.7), `quick` +3.7 (95% CI +3.3 to
  +4.1); GitHub READMEs unchanged (-0.02). Held-out scores are now `free` 57.2 (was 54.8) and
  `quick` 67.4 (was 63.9). `standard` does not use the candidates and is unchanged.
- Docs: a Providers section in the package README (tested and untested endpoints, requirements,
  setup).
- Release workflow: `pypa/gh-action-pypi-publish` v1.13.0.

## 0.1.0 (2026-10-25)

- First release on PyPI: `pip install section-anything`. Modes `free`, `quick`, `standard` and
  `local:<model>`, a command line, Markdown and JSON output, and a hard cost cap on every paid run.
- `free` drops headings that a complete-looking PDF outline does not list (the outline check, on by
  default for `free`).
