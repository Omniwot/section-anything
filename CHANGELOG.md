# Changelog

Releases of the `section-anything` library on [PyPI](https://pypi.org/project/section-anything/).
Scores are READoc heading-tree TEDS (0-100) with READoc's own scoring code.

## 0.1.8 (unreleased)

- **Possible missed headings.** `tree.possible_misses` (also in `to_dict()` and the command line's
  JSON) lists, best first, the lines with heading evidence that the result does not have as
  headings: page, text, the evidence in words ("its number fills a gap in the headings' numbering",
  "set like other headings", "Docling labels it a heading", ...) and a score from 0 to 1, at most one
  entry per 5 pages (at least 3). The weights were fitted on development documents only; after a
  model mode only stronger evidence is listed. The result itself is unchanged. On held-out documents
  (the F042 test split, 100 documents, and 165 more documents frozen on 3 Nov, with and without
  bookmarks) the list held 1% to 4% of the headings Free missed, at 0.2 to 0.5 wrong entries per 10
  pages, and 8% to 10% with Docling's hints (0.5 to 0.7 wrong entries per 10 pages). Most missed
  headings are set like body text and carry no evidence the list can use (research finding F057).
- **Contents check (opt-in).** With `SECTIONANY_CONTENTS_CHECK='["free","quick","standard"]'` (or
  some of those modes), every entry of the PDF's bookmarks (else its printed table of contents) and
  of contents lists without page numbers that no section covers is looked for in the body near its
  page, by its text or its label and number, and added as a heading flagged `from_contents`; an
  entry that is not found is listed in `possible_misses`, never guessed. Off by default: on the
  held-out documents Free's missed headings per 1,000 went from 152.0 to 151.2 (F042 test, with
  bookmarks) and from 233.9 to 232.1 (the 165 documents, without), with F1 down 0.001, and one PDF
  whose 736 bookmarks list far more than its headings got 283 extra headings. Free already follows a
  usable outline; applied offline to saved Quick check runs it removed 0.6% to 5% of their missed
  headings at level F1.

## 0.1.7 (unreleased)

- **`quick` finds structural headings set small or plain.** A bare division label (Part, Chapter,
  Schedule, Annex, Appendix, Title, Book and their German and French forms) is now a candidate
  with the title line under it, however small or plain it is set; `free` already took it. A short
  reference printed smaller beside a label (a UK Act's "Section 5" next to "SCHEDULE 1") is passed
  over, so a schedule's heading starts at its label in both modes. On held-out legislation, Claude
  Haiku 5.5, 3 runs each (research finding F052): UK Acts heading F1 0.623 -> 0.677 (15 documents,
  +0.054, CI +0.024 to +0.085), with recall of Parts 0.20 -> 0.96, Chapters 0.01 -> 0.96 and
  Schedules 0.03 -> 0.87; EU regulations 0.819 -> 0.875 (11 documents, +0.057, CI +0.027 to
  +0.087), Chapters 0.27 -> 0.85. `free` gains schedule headings on UK Acts (recall 0.83 -> 0.88)
  and is unchanged on five other genres; `quick` is level on the 15 documents of those genres whose
  candidates changed (theses, reports, German laws; no RFC changed).
- **Mode `auto`, and a confidence for each Free heading.** Every `free` section now has `confidence`
  (0 to 1): how much of Free's own evidence backs it (the PDF's outline lists it; its style is used
  on several pages and for little else; its number follows the previous one; a standard name; ten
  words or fewer). It is `None` for front matter and in the model modes; nothing else in any mode's
  output changes. Mode `auto` runs `free`, then `quick` only when Free found fewer than three
  headings or their mean confidence is below `auto_threshold` (0.72, `SECTIONANY_AUTO_THRESHOLD`);
  `tree.auto` (and `auto` in `to_dict()`) gives the mode taken, the reason, the confidence and the
  threshold. It needs `quick`'s API key and keeps the per-document cap (over it, Free's result
  stands). The weights and threshold were chosen on development documents only (200 READoc, 21
  public corpus documents; an earlier version was also scored once on the held-out documents
  before the threshold was fixed). On held-out READoc: 905 arXiv papers 68.4 with 28% sent to
  `quick` (`quick` 68.0, `free` 60.1); 1,124 READMEs 81.6 with 3.5% sent (`free` 81.4, `quick` 70.8).
  Other genres are not yet tested on held-out documents. With `docling=`, Free runs with Docling's
  hints and auto judges that result (the confidence weights do not use Docling's labels). On a
  Docling document, `section(doc, "auto")`, Docling's own heading levels are not counted as outline
  evidence for its own headings.
- **Docling's output as input (opt-in).** `section("report.pdf", docling=doc)` takes Docling's
  layout labels as hints for the PDF's own lines: its section headers and titles become heading
  candidates whatever their style, its page headers and footers are treated as running headers and
  footers, and in `free` mode styled lines it labels as body text are not taken as headings. A bare
  label and the title line under it ("Article 3" / "Subject matter") stay one heading even when
  Docling gives each its own item, as it often does in EU regulations. The PDF's fonts, bookmarks
  and printed table of contents still count. `section(doc)` sections a
  `DoclingDocument` itself, for scanned PDFs or any format Docling reads: its text items become the
  lines, and heading levels come from Docling's levels or the heights of the heading boxes. Both
  take the `DoclingDocument` object, its JSON as a dict or a saved `.json` file, and neither needs
  docling-core. Hints from another PDF are refused with `ConfigError`. On the command line:
  `--docling FILE.json` for hints, or a Docling `.json` file in place of the PDF. Not in
  `section_many`, folder mode or the MCP server yet.
- **Standard reads a window again when its answer leaves many headings out.** gpt-6-luna sometimes
  stops listing early or skips a run of headings: asked the same thing six times, it once listed
  none of the 83 sections in the first part of a 75-page act, and in 3 of 6 runs left 70 to 100
  headings of a 125-page manual out. When a window's answer leaves at least 10 heading-like lines
  unlisted, and at least 30% of them (rule candidates after its last section, or lines set in the
  style of its own larger headings that it skipped), Standard reads that window once more and keeps
  the answer that lists more of them. Replayed on 60 saved Standard runs of 26 corpus documents, the
  check fired on all 4 runs that had this problem, on none of the 52 runs with heading recall of
  0.80 or more, and on the 2 runs of a manual whose index letters Standard always leaves out.
  In a paid check (gpt-6-luna, 5 new runs per document), the check fired in 3 of 5 runs of the
  manual and each re-read listed the skipped headings: recall 0.955 to 0.965 in all 5 runs, against
  0.32 to 0.955 in the 6 earlier runs; a re-read cost $0.005 to $0.009. It does not catch every miss:
  on the act, runs that skipped some section titles set in bold at body size were not flagged
  (F1 0.74 to 0.90 over 5 runs). At most one extra call per window, only while the per-document
  cap still covers it and the windows after it (it is not in the up-front estimate). Each re-read
  is listed in `tree.usage["coverage_retries"]`; `SECTIONANY_COVERAGE_RETRY=false` turns the check
  off. Standard only: Quick check, and mode `auto` when it escalates, make one review call as before.
- **Standard swings less from run to run.** Three more causes of runs that differ on the same input:
  - **Contents lists without page numbers** ("CONTENTS OF ACT") were listed as sections. They are now
    recognised because their entries come back later, in the same order, as headings spread over the
    document, and Standard treats them like a table of contents.
  - **Section titles in bold at body size** were skipped without the coverage check noticing. With
    contents lists left out, it now counts them too; labels repeated through a document
    ("Parameters", "Returns") are not counted.
  - **A cut-off answer** at the model's output limit, whether a window's first read or its coverage
    re-read, used to fail the document. That window is now read as two halves, split at the page
    break nearest its middle. Each split is listed in `tree.usage["window_splits"]`.

  With Claude Haiku 5.5:
  - South Africa's POPIA act: F1 0.68 to 0.89 over 4 runs plus 1 failed, now 0.87 to 0.90 over 5
    runs.
  - The 125-page Requests manual: 4 of 5 runs failed and the fifth found 15% of the known headings;
    now recall 0.955 to 1.00 in all 5 runs.
  - 7 other public documents, 3 runs each: the worst run's F1 averaged 0.635, now 0.710. Two
    documents are better, three the same and two worse by 0.025.

  Development data and one model (research finding F051). A cut-off answer is paid for before the
  split, and splits are not in the up-front estimate.
- **Many PDFs with a total budget.** `section_many(pdfs, mode, max_usd_total=...)` (and
  `asection_many`) sections PDFs one at a time and yields a `DocumentResult` for each: path, tree or
  error, cost, and the cap it ran with. Each PDF's cap is the smaller of the per-document cap and
  what is left of the total, so paid runs are downgraded (or refused with `over_budget="fail"`) as
  the total runs out; spending on PDFs that then failed counts too. Errors are recorded and the run
  goes on (`on_error="raise"` stops at the first); configuration errors are always raised, before any
  PDF is read. On the command line, a folder or several PDFs write one output per PDF into
  `-o DIR`, with `--recursive`, `--skip-existing` (resume a stopped run) and `--max-usd-total`, one
  line per PDF and a total on stderr. Folder mode exits 4 when one or more PDFs failed, 0 when all
  were done or skipped. A single file works as before.
- **Use Docling's or Unstructured's chunkers on our headings.** `tree.to_unstructured_elements()`
  returns Unstructured's element dicts (a `Title` per heading with `category_depth` and
  `parent_id`, a `NarrativeText` per body paragraph, page numbers and boxes) for its
  `chunk_by_title`; it needs no new dependency. `tree.to_docling_document()` returns a Docling
  `DoclingDocument` (`TitleItem`, `SectionHeaderItem` at each level, text items under their
  heading, page provenance) for its `HybridChunker`; it needs the new `docling` extra
  (`pip install "section-anything[docling]"`, docling-core 2.x). Tests run both chunkers on the
  exports: every chunk starts at one of our headings (Unstructured) or carries our heading path
  (Docling).
- **Free on laws, standards and reports: more text read, fewer false headings, levels from labels.**
  Tested on a new multi-genre set of public documents (RFCs, German, EU and UK legislation, NIST and
  GOV.UK reports, GOV.UK annual reports, arXiv PhD theses; split frozen before any change). On its
  100 held-out documents Free's mean F1 went from 0.710 to 0.739 with the PDFs' bookmarks and from
  0.660 to 0.699 without, up in every genre; heading levels from 0.895 to 0.925 and 0.905 to 0.919.
  READoc held-out: 905 arXiv papers 60.10 to 60.57 (95% CI +0.25 to +0.70; 25 papers worse, 7 of
  them by more than 5 points), 1,124 READMEs 81.44 to 81.46.
  - The extractor (version 6, so saved extractions are redone) reads text drawn inside a form that
    covers the page, which printed UK Acts of 2011-2016 use for every page (they came out with no
    text: "needs OCR"), and CID fonts whose encoding is a CMap embedded in the PDF (Official Journal
    of the EU body text came out as symbols). Both change the text of the PDFs concerned, in every
    mode.
  - A table of contents whose title is on its first page only is followed onto the next pages, and
    the same line at the same height on three pages in a row (a running header that changes with
    each part, a table's repeated header row) is furniture. Both apply in every mode.
  - Free: cells of table rows ("Total", "£ million") are no longer headings; a bare label on its own
    line ("CHAPITRE I", "Article premier", "T e i l 1", now also German and French label words) is
    joined with the bold, larger or capitalised title under it; a bookmark glued to its number
    ("Teil 1Gemeinsame Bestimmungen") is matched; and when an outline is flat, or typography ranks
    the labels upside down, the labels set the levels (parts above chapters above sections above
    articles, corrected by where the numbering starts again).
    On a two-column page a numbered heading that shares its row with an equation, its number or a
    table in the other column is not a cell, and neither is the abstract's heading.
  - Known cost: with fewer stray numbered lines the outline check now demotes headings that a
    partial outline leaves out on some annual reports.
- **Free no longer trusts an outline that skips most of the document.** The outline check (Free
  only, by default) drops headings a complete-looking PDF outline does not list. A long EU
  regulation bookmarked only at its title and annexes passed as complete, so Free returned 13
  sections and none of its articles. The check now also needs no long run of pages without a
  bookmark (more than half the document and at least 10 pages) holding three or more of the
  headings it would drop. On READoc this changes 6 of 2,262 documents, all with outlines that cover
  a small part of the document: held-out papers 59.97 -> 60.10 (3 changed, each +35 or more),
  held-out READMEs 81.42 -> 81.44 (2 changed: +32.6 and -5.8), development READMEs 79.59 -> 79.70
  (1 changed), development papers and the 29-document public corpus unchanged. Quick check and
  Standard do not run the outline check by default and are unaffected.
- **PDFs as bytes.** `section`, `asection` and `extract_pdf` also take the PDF itself as `bytes`,
  `bytearray`, `memoryview` or a binary file-like object (an open file, `io.BytesIO`), for data
  platforms and serverless functions that hand over bytes, not paths. The size cap is checked before
  anything is written to disk, and data without a `%PDF-` header is refused with `PdfError`. The bytes
  then go to a private temporary file, removed afterwards, so the other limits and the extraction
  worker apply unchanged. A file object is read once and left open. `section_anything.PdfInput` types
  the accepted inputs.

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
