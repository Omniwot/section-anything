<!--
DRAFT, NOT FOR DISTRIBUTION. Venue-neutral technical report, 21 Oct 2026.
Nothing in this folder has been published, submitted, uploaded or posted.

Source convention: every number carries an HTML comment "src: <file> <lines or key>".
Paths are relative to the workspace root (written <workspace>/ elsewhere), e.g.
  HANDOFF-section-anything.md                     = <workspace>/HANDOFF-section-anything.md
  section-anything/site/data/results.js           = latest headline tables (updated 2026-10-21)
  section-anything/docs/PLAN-upstream-and-rag.md  = related-work notes and the 23-doc table
  section-anything/backend/app/sectioning/...     = method (code is the source of truth)
  .tmp/readoc-pilot/score.py, heldout_report.py   = READoc export and statistics (cited by the handoff)
  .tmp/rag-pilot/step4_rag.py                     = RAG pilot protocol (cited by the handoff)
Line numbers refer to the files as of 21 Oct 2026.
Where a number is missing, the text says TODO. Do not fill TODOs from memory.
Model names (gpt-6-luna, gpt-6.1-sol, gpt-5.5) are the OpenAI model ids used in the runs.
-->

# Section Anything: Heading Hierarchies from Born-Digital PDFs with Typography, Bookmarks and Verbatim-Anchored Language Models

**Anonymous Author(s)**
Affiliation withheld · contact withheld

*Draft technical report, 21 October 2026. To be adapted for arXiv, ICDAR 2027 or ACM DocEng 2027.*

---

## Abstract

Retrieval-augmented generation (RAG) pipelines increasingly split documents at their headings, so
the heading hierarchy that a PDF parser recovers decides what each chunk contains and which
section path it carries. We describe Section Anything, a heading-hierarchy extractor for
born-digital PDFs that works from the PDF text layer and its typography rather than from page
images. It has three settings of increasing cost. *Free* uses no model: it anchors the PDF's
bookmarks or its printed table of contents to body lines and fills the gaps with typography and
numbering rules. *Quick check* sends only candidate heading lines to a small language model.
*Standard* lets a model read every line in windows and quote verbatim start and end markers,
which a deterministic resolver maps back to exact character ranges, rejecting table-of-contents
copies and flagging anything it cannot verify. On READoc, scored with the benchmark's own
Heading Tree TEDS code, Standard with a small model scores 70.0 on 905 arXiv papers that were not
used during development, against 49.4 for Docling 2.140 with its heading-hierarchy stage enabled.
On the same papers, MinerU with its own LLM title-levelling step on a larger model scores 64.8. On GitHub READMEs there is no
such gain: Docling is level with or ahead of our settings. The model settings cost about $0.07
(Quick check) and $0.16 (Standard) per 1,000 pages with a small model. Without bookmarks, the
free setting is weaker than Docling on papers, and nothing here works on scanned pages. In a small
FinanceBench pilot (51 questions), chunks split at headings retrieved the evidence page more
often than fixed-size chunks, but our headings did not beat MinerU's. We report the development
history behind each number, including a thread-safety bug that silently dropped bookmarks.
<!-- src: held-out 905 — HANDOFF-section-anything.md L944-961; site/data/results.js readoc.heldout; MinerU 64.8 — results.js readoc.heldoutMinerU, .tmp/readoc-pilot/heldout_report_mineru_full.txt (25 Oct).
     GitHub — results.js readoc.sample (Docling 73.2 vs ours 71.3/70.1/71.5) and HANDOFF L864-877 (full: Standard 75.4, Docling 75.0, Quick 70.3).
     Cost — results.js modes[].costPer1000Pages. Free without bookmarks — HANDOFF L801-802. RAG — HANDOFF L679-704. Bug — HANDOFF L784-794. -->

---

## 1 Introduction

Retrieval pipelines for long documents rarely embed whole documents. They cut them into chunks,
and a growing number cut along the document's own sections instead of at fixed token counts, or add
context such as a section path to each chunk so that a retrieved passage keeps its meaning
[@lu2026hichunk; @anthropic2024contextual]. LightRAG's heading-based chunker, for example,
splits on the `heading`, `level` and `parent_headings` that a parser supplies, and its
documentation warns that this chunker depends on the parser getting headings right
[@guo2025lightrag; @lightrag_parser_docs].
Markdown header splitters in common RAG frameworks behave the same way with `#` levels. In each
case the heading hierarchy recovered from the PDF decides the chunk boundaries and the context
strings attached to them: a missed heading merges two topics into one chunk, a sentence promoted
to a heading splits a paragraph, and a wrong level files a subsection under the wrong parent.
<!-- src (LightRAG chunker and warning): section-anything/docs/PLAN-upstream-and-rag.md L22-24. TODO: confirm wording against current LightRAG docs before submission. Markdown header splitters — site/data/results.js integrations (LlamaIndex / LangChain). -->

A PDF stores positioned glyphs with font names and sizes, not sections. Born-digital PDFs do carry
partial signals: an outline (bookmarks), a printed table of contents, numbering schemes ("2.3",
"Article 9", "Chapter IV") and typography (size and weight). None is reliable on its own. Bookmarks
are often missing or incomplete, and their titles drop section numbers and mangle maths; numbering
is absent from most READMEs; bold type also marks theorem labels, FAQ questions, callout labels and
table cells. Open-source converters such as Docling and MinerU detect section-header blocks with
layout or vision-language models on page images and then assign levels with rules or an optional LLM
step [@docling_software; @mineru_software]. On the READoc benchmark [@li2025readoc], the published
Heading Tree TEDS of Docling, MinerU and Marker ranged from 38.3 to 42.0 on arXiv papers and from
22.8 to 47.2 on GitHub READMEs, while Nougat, an OCR model trained on arXiv, reached 88.5 on arXiv.
<!-- src: published READoc scores — site/data/results.js readoc.published (Docling 38.3/22.8, Marker 39.4/37.5, MinerU 42.0/47.2, Nougat-base 88.5/37.0); all five match the "Heading > Tree" column of READoc Tables 3 and 4 (arXiv 2409.05137v3), checked 2026-10-21. Bookmark titles drop numbers — HANDOFF L801-803. -->

Section Anything treats heading recovery from born-digital PDFs as a text problem with
typographic hints. It reads the text layer with pdfminer's layout analysis, keeps the size and
weight of every line, reads the bookmarks, and offers three settings of increasing cost (Free,
Quick check and Standard). In the model settings the model never writes the output directly:
every proposed heading must be anchored to verbatim text by a deterministic resolver that rejects
table-of-contents copies, gives each start offset to one section only, and flags markers or titles
it cannot find. The method does not look at page images and does not perform OCR.

**Contributions.**

1. A text-layer method with three cost settings and a shared resolution step that anchors every
   proposed heading to a verbatim span of the document (Section 3).
2. An evaluation on READoc with the benchmark's own scorer, including 905 held-out arXiv papers
   that were not used during development, against current Docling (heading-hierarchy stage on),
   MinerU (cloud, with and without its LLM title levelling on two models) and PyMuPDF4LLM; and
   an evaluation on a 118-document, 11-category English corpus whose answer keys come from
   source markup (Section 4).
3. An account of what changed the numbers during development (TeX bold fonts, a thread-safety bug
   that dropped bookmarks, a document-title rule, a prompt fix designed on the development sample
   and confirmed on held-out papers), of the remaining failure modes, of where other tools win, and
   an offline simulation of bookmark reconciliation for Docling (Section 5).
4. A small RAG pilot on FinanceBench that separates "heading-aware versus fixed-size chunks" from
   "our headings versus MinerU's" (Section 6).
<!-- src: corpus size — HANDOFF L456-475; held-out count — HANDOFF L944. -->

Every number in this report comes from a single run per configuration with proprietary models
(OpenAI gpt-6-luna and gpt-6.1-sol, plus gpt-5.5 in early runs), dated October 2026. Several
method changes were designed on a 200-document READoc sample; we report that sample separately and
treat the held-out arXiv papers as the main test.

---

## 2 Related work

### 2.1 Benchmarks for document hierarchy

READoc [@li2025readoc] evaluates end-to-end conversion of real PDFs to Markdown on 3,576 documents in
three subsets: READoc-arXiv (1,009), READoc-GitHub (1,224) and READoc-Zenodo (1,343). Among other
aspects it scores headings in two ways: edit-distance similarity on all headings concatenated
("Concat") and tree edit distance similarity on a table-of-contents tree ("Tree"). The latter is the
TEDS metric introduced for table recognition [@zhong2020image]. We report the Tree score. HRDoc
[@ma2023hrdoc] provides 2,500 multi-page papers with line-level semantic classes and parent and
relation labels for hierarchical reconstruction. Comp-HRDoc [@wang2024detectorderconstruct], built
on HRDoc-Hard, evaluates page object detection, reading order, table-of-contents extraction and
hierarchical reconstruction with a semantic variant of TEDS. DocHieNet [@xing2024dochienet] has
1,673 English and Chinese documents (15,610 pages, up to 50 pages each) annotated with 19 layout
element types and hierarchical relations that cross pages. These datasets were built for layout
and vision models; Comp-HRDoc and DocHieNet are natural next tests for a text-layer method
(Section 8). Our own corpus reuses the HiPS law-textbook annotations [@hips_dataset].
<!-- src: READoc subset sizes, metric names — arXiv 2409.05137v3 (https://arxiv.org/html/2409.05137v3), verified 2026-10-21; HRDoc — AAAI-23 / arXiv 2303.13839; Comp-HRDoc — arXiv 2401.11874; DocHieNet — https://aclanthology.org/2024.emnlp-main.65/ (paper PDF); HiPS — HANDOFF L423-427 (unverified at source). -->

### 2.2 Parsers that produce heading levels

Docling [@auer2024docling] converts PDFs with layout and table-structure models. Its layout model
tags section headers without depth; an optional heading-hierarchy stage, added in version 2.106.0
and disabled by default because "a wrong level is worse than a missing one", rewrites their levels
from PDF bookmarks, numbering and font style [@docling_software]. We evaluate Docling with this stage
enabled. MinerU [@wang2024mineru; @niu2025mineru25] parses documents with a pipeline or a
vision-language backend, and an optional LLM step assigns title levels (formerly
`llm-aided-config.title_aided`, now `llm_aided.features.title_leveling`, levels 2 to 6, disabled by
default) [@mineru_software]. Marker's README describes its `--use_llm` mode as improving tables,
inline maths and forms; its code also contains an LLM processor that asks for correct section-header
levels, which we did not trace to that flag [@marker_software]. PyMuPDF4LLM maps font sizes larger
than the most common one to Markdown header levels, or takes headers from the PDF's table of
contents [@pymupdf4llm_software]. Nougat [@blecher2024nougat] and GOT-OCR 2.0 [@wei2024got] are
end-to-end OCR models that output markup; Nougat, trained on scientific papers, holds the best
published READoc-arXiv heading score. PageIndex [@pageindex_software] builds a hierarchical tree
index that an LLM searches by reasoning instead of by vector similarity; it consumes a document tree
rather than evaluating one. Unlike Docling and MinerU, Section Anything uses no page images; unlike
PyMuPDF4LLM's size mapping, it combines the outline, numbering and typography and can let a model
judge candidates, and it holds every model proposal to a verbatim span of the text.
<!-- src: Docling heading levels — https://docling-project.github.io/docling/usage/heading_levels/ and CHANGELOG (v2.106.0, 2026-06-23), verified 2026-10-21; MinerU — https://opendatalab.github.io/MinerU/usage/quick_usage/; Marker — https://github.com/datalab-to/marker (README; marker/processors/llm/llm_sectionheader.py); PyMuPDF4LLM — https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html; PageIndex — https://github.com/VectifyAI/PageIndex; Nougat best on arXiv — results.js readoc.published. -->

### 2.3 Structure-aware chunking and retrieval

RAPTOR [@sarthi2024raptor] builds a retrieval tree by recursively embedding, clustering and
summarising chunks: a tree induced from content, not from the document's headings. Contextual
Retrieval [@anthropic2024contextual] prepends model-written context to each chunk and reports that
this cut the top-20 retrieval failure rate by 35%, and by 49% together with contextual BM25. HiChunk
[@lu2026hichunk] argues that existing RAG benchmarks have too little evidence per question,
introduces HiCBench with manually annotated multi-level chunking points, and structures documents
into multi-level chunks with a fine-tuned LLM. On FinanceBench [@islam2023financebench],
element-based chunking reached 53.19% answer accuracy against 48.23% for 512-token chunks
[@jimenoyepes2024financial], while an NVIDIA comparison found page-level chunks most accurate on
average, with FinanceBench the exception, where section-level chunks did slightly better
[@han2025chunking]. LightRAG [@guo2025lightrag] is a graph-based RAG system whose parser plugins
can supply headings to a heading-aware chunker; evaluations of graph-based RAG judged by LLMs have
been shown to overstate gains [@zeng2025graphrageval]. We know of no study that varies heading
accuracy while holding text, chunk size, retriever and models fixed; our pilot (Section 6) is a
small first step.
<!-- src: RAPTOR — arXiv 2401.18059; Contextual Retrieval — https://www.anthropic.com/news/contextual-retrieval (failure rate 5.7% -> 3.7% (-35%), 2.9% (-49%)); HiChunk — ACL 2026 / arXiv 2509.11552; Jimeno Yepes et al. — arXiv 2402.05131 (141 of 150 questions); NVIDIA — https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/; 2506.06331; "no study isolates heading accuracy" — PLAN-upstream-and-rag.md L103 (our literature reading, not exhaustive). -->

---

## 3 Method

Figure 1 shows the pipeline. All three settings share the extraction, the structure detectors and
the resolver; they differ only in how sections are proposed.

```
PDF ─┬─► text layer (pdfminer layout): lines in reading order, boxes, size, bold
     └─► bookmarks (pypdfium2): level, title, target page and y
                     │
          shared structure: table of contents, page furniture (headers, footers, page numbers)
                     │
   ┌─────────────────┼──────────────────────────┬───────────────────────────────┐
   Free              Quick check                Standard
   bookmarks / TOC   loose candidates ──►       every line, tagged, in windows ──►
   backbone + rules  small-model review         model returns start/end markers
   └─────────────────┴──────────────┬───────────┴───────────────────────────────┘
                     resolution: markers ─► character ranges (TOC-aware, one section
                     per offset, flags) ─► document-title flag
                                    │
     sections: level, number, title, character range, page range, line boxes, flags
```
*Figure 1. Pipeline. Text only: no page images and no OCR.*

### 3.1 Text layer and typography

We extract text with pdfplumber over pdfminer.six (both MIT-licensed), using pdfminer's layout
analysis with `boxes_flow` = 0.5 so that two-column pages are read column by column. Each text line
gets its text (whitespace collapsed, control characters removed), a box in PDF user space, the
median glyph size (rounded to 0.1 pt) and a bold flag. A line is bold when more than half of its
glyphs come from a font whose name matches a bold pattern. Besides the usual words ("Bold",
"Semibold", "Black"), the pattern includes the font codes of TeX bold faces (CMBX, CMSSBX, CMBSY,
SFBX, SFSX, ECBX, EUBX) and the `-Medi` suffix of Times-like bold fonts; without these, the bold
headings of almost every LaTeX paper were invisible (Section 5.1). All lines are joined with
newlines into one canonical document string, and each line keeps its character range in it, plus
per-word horizontal extents, so a section can be mapped back to exact rectangles on the page. The
body size is the font size that carries the most characters.
<!-- src: section-anything/backend/app/sectioning/extract.py (LAPARAMS, BOLD_FONT, Line, body_size, EXTRACTOR_VERSION 4); HANDOFF L759-762. -->

Bookmarks (the PDF outline) are read with pypdfium2, keeping each entry's level, title, target page
and target y position. PDFium is not thread-safe, so every use takes a process-wide lock
(Section 5.1). We do not use PyMuPDF because of its AGPL licence. Extraction takes about 0.02 s per
page. Pages without a text layer produce no lines.
<!-- src: extract.py (PDFIUM_LOCK, read_outline); speed — HANDOFF L148-150; licence choice — extract.py docstring, HANDOFF L124-128. -->

### 3.2 Shared structure: tables of contents and page furniture

A table of contents (TOC) repeats the headings it lists, so a TOC line must never become a section
start. Two detectors find TOCs: runs of short lines that end in a page number (usually with dot
leaders), and a title line such as "Contents" or "In this chapter" followed by entries in one
numbering pattern or style. TOC entries keep their number, title, printed page and indent; their
level comes from numbering depth or, failing that, from indent rank. Page furniture (running headers
and footers, page numbers) is text that repeats with digits masked at about the same height on many
pages, lines that are only page numbers, and small text in the top or bottom margin. Thresholds for
these and the other rules are listed in Appendix C.
<!-- src: section-anything/backend/app/sectioning/structure.py (_page_number_runs, _titled_runs, _gap_limit, detect_toc, _furniture). -->

### 3.3 Free: bookmarks or TOC as a backbone, then rules

**Backbone.** Free first looks for the document's own outline: the bookmarks, or else the printed
TOC. A bookmark is anchored to a line on its target page (or the next page) whose canonical text
equals the bookmark title, alone or joined with the following one or two lines on the same page
(for titles that wrap, or for "CHAPTER 17" printed above the title). TOC and furniture lines are
excluded, and the line nearest the bookmark's target y wins. TOC entries are anchored in order to
the first matching body line after the TOC. An outline is used as the backbone when at least three
entries anchor and they make up at least 60% of the outline.
<!-- src: structure.py (anchor_bookmarks, _names, anchor_toc, outline_backbone). -->

**Typography and numbering rules.** A line is a candidate when it is *styled* (larger than body
text, or bold) or *numbered* ("2.3", "IV.", "A.", "Chapter 4", "Article 9", ...). Candidates are
dropped when they are furniture, TOC lines or captions; when they are too long to be headings; when
they are mostly not letters (bold maths); when they are rotated text read letter by letter (such
as the arXiv side stamp); when they are short all-caps labels repeated across the document (callout
boxes such as "NOTE"); when they are theorem-like labels ("Definition II.1.", "Proof."); when they
are numbered list items in body type; or when they are bold terms that run on into a lowercase
paragraph. Wrapped headings and bare labels ("CHAPTER 10" followed by its title line) are merged.
Levels come from numbering depth for dotted numbers ("2.3.1" is level 3) and otherwise from the
rank of the line's style (larger first, bold before regular), compressed to 1..n.
<!-- src: section-anything/backend/app/sectioning/strategies/rules.py (candidates, NUMBERING, CAPTION, THEOREM, _labels, _runs_on, _vertical, _merge_wrapped, _rules); HANDOFF L764-769. -->

**Combining them.** When a backbone exists, its entries keep their outline levels. A style used by
two or more backbone entries takes their majority level; other styles found by the rules slot in by
size relative to those. Rule headings that the backbone does not cover are added. Free sends
nothing to any model and costs nothing.
<!-- src: rules.py (RulesStrategy.run, _levels_from_outline). -->

### 3.4 Quick check: candidates plus a small-model review

Quick check widens the candidate filter for recall (a 0.4 pt size threshold, up to 160 characters
or 20 words, no label or theorem filtering) and merges a bare label such as "Article 9" or
"Title I" with the line that follows it. Each candidate is shown to the model as one row,
`<id>| p<page> <tags> <text>  ⟶ <start of the text that follows>`, where the tags give the size
relative to body text (⟨H+n⟩, ⟨=⟩) and boldness (⟨B⟩), and the arrow is followed by the first 70
characters of the next line. Candidates go in batches of 300, each with the last eight decisions as
context. For every candidate the model returns whether it is a heading, its level (1 to 8), its
printed number and its title, through a schema-constrained (structured-output) call.
<!-- src: section-anything/backend/app/sectioning/strategies/llm_text.py (REVIEW_SYSTEM, LlmReviewStrategy._rows, batch = 300, _prev_block last 8, ReviewItem level 1..8); rules.py candidates(loose=True), LABEL_ONLY. -->

The prompt (Appendix A) says that running headers, captions, table cells, list items, callout
labels and emphasised phrases are not headings; that a short bold body-size line standing alone
before a paragraph (an FAQ question, a named step) is usually a minor heading; that the document's
own title on page 1 and printed headings such as Abstract, Acknowledgements, References and
Appendix are headings; and that theorem-like labels are not. If a returned title does not appear in
the printed text, the printed line is used instead, so model-written words never reach chunk
context. The input is a small fraction of the document, but Quick check cannot recover a heading
that the candidate generator never proposed.
<!-- src: llm_text.py (REVIEW_SYSTEM, title fallback in LlmReviewStrategy.run); HANDOFF L1037 (M2 fix), L567 (recall cap). -->

### 3.5 Standard: the model reads every line

Standard sends every line, numbered and tagged (`<line>| <text>`, with ⟨H+n⟩ when the line is at
least 0.8 pt above body size and ⟨B⟩ when it is bold), in windows of about 120,000 characters that
end at a page break where possible (a window is cut at the first page break after the budget, or at
1.3 times the budget). Windows do not overlap; each carries the last eight sections found so far so
that levels stay consistent. For every section that starts in the window, the model returns the
start line, the printed number, the title, whether the title is printed (`title_from_text`), the
level, a start marker (the first 8 to 15 words of the section, copied exactly) and, if the section
ends inside the window, an end marker (its last 8 to 15 words). Where a stretch of text has no
headings, the model is asked to split it at clear topic shifts and to write a short title, marked
as not printed. The exclusion rules match those of Quick check (Appendix A).
<!-- src: llm_text.py (TEXT_SYSTEM, _tagged, _windows, window_chars = 120_000, _prev_block, TextSection). -->

### 3.6 Resolution: from markers to sections

Models rarely quote text byte for byte: quotes, dashes, ligatures, soft hyphens and line-break
hyphens differ between the PDF and the reply. Both sides are therefore reduced to a canonical form
(case-folded letters and digits separated by single spaces, ligatures expanded, line-break hyphens
removed) with a map from every canonical character back to its original offset.
<!-- src: section-anything/backend/app/sectioning/markers.py (_canon, Locator). -->

For each proposal the resolver looks for exact canonical matches of the start marker near the
model's line hint, then anywhere; drops hits inside a TOC when a body copy exists; and falls back to
a bounded fuzzy match or to the line hint, flagging either. Proposals with the fewest candidate
positions claim offsets first, so a heading repeated in an outline, the body and a summary cannot
take another section's place, and no two sections share a start. Text before the first heading
becomes an explicit front-matter section. Each section gets a *segment* (to the next section of any
level) and a *span* (to the next section at the same or a higher level). End markers are checked
against these boundaries, and titles the model says are printed must appear at the section start;
mismatches are flagged, not silently accepted. Every output section therefore has a level, number,
title, character range, pages, lines and flags, and a viewer can highlight it from the line boxes.
<!-- src: section-anything/backend/app/sectioning/pipeline.py (module docstring, _candidates, _assign, resolve, FRONT_MATTER_MIN_CHARS = 300); markers.py (FUZZY_MIN = 85). -->

### 3.7 Document-title flag

Papers have a title that should contain all other sections, whereas READMEs and manuals often have
several top-level headings of the title's size. After resolution, the first heading is flagged as
the document title when it is on page 1, is unnumbered, is not a generic name (Abstract,
Introduction, Contents, ...) and is set at least 1 pt larger than every other heading. Exports nest
the other headings under it; in Markdown, the title becomes `#` and a heading at level L becomes
L + 1 hash marks (capped at six).
<!-- src: pipeline.py (mark_doc_title, GENERIC_FIRST); export — .tmp/readoc-pilot/score.py ours_md; HANDOFF L770-773. -->

### 3.8 Cost controls and safety

Before a run, tokens are estimated from the extracted text and a run whose estimate exceeds the cap
(US$5 by default) is refused. During a run the cap is re-checked before every model attempt, the
SDK's hidden retries are disabled, cloud models without a known price are refused, and in the
LightRAG plugin one budget covers a document across downgrades (Standard to Quick check to Free).
Outputs are schema-validated and clipped (Appendix C). The prompts state that document text is
untrusted and that instructions inside it must not be followed. Uploads are limited to 100 MB (and
500 pages in the web app). Cloud models run at low reasoning effort.
<!-- src: pipeline.py (estimates); section-anything/backend/app/sectioning/llm.py (structured, CostCapExceeded, max_retries=0, attempts=2); backend/app/core/config.py (RUN_COST_CAP_USD = 5.0, MAX_PAGES = 500); llm_text.py (_clip(300), [:2000], UNTRUSTED); HANDOFF L1029-1040 (security review table), L851-852 (plugin budget). -->

### 3.9 Local models

Quick check and Standard can also run on a local model, either through Ollama's
OpenAI-compatible endpoint (temperature 0, reasoning disabled) or, in the demo application,
through the visitor's browser, which relays each prompt to the visitor's own Ollama or
OpenAI-compatible server and returns the reply for the same schema validation. Local runs cost
nothing and send no text to a provider; Standard uses 30,000-character windows for them. We suggest
Quick check for small local models. **We have not yet measured accuracy with local models (TODO).**
<!-- src: llm.py (_client LOCAL_PREFIX, temperature 0, reasoning_effort none; _structured_browser); bridge.py; llm_text.py (30_000 for BROWSER_PREFIX); site/data/results.js modes[local], tryIt; HANDOFF L997-1004. -->

---

## 4 Experiments

### 4.1 READoc setup and metric

READoc [@li2025readoc] converts real PDFs to Markdown and scores them against reference Markdown.
We use two of its three subsets, READoc-arXiv (papers) and READoc-GitHub (READMEs rendered to PDF);
the Zenodo subset has PDFs but no published answer keys, so we cannot score it. Our copy contains all
1,009 arXiv and 1,224 GitHub documents named in the paper, with their answer keys; 1,003 of the
arXiv keys contain headings.
<!-- src: HANDOFF L832 (1,009 / 1,224), L800 and L864 (1,003 with headings), L1079 (Zenodo has no keys); paper subset sizes 1,009 / 1,224 / 1,343 — arXiv 2409.05137v3, checked 2026-10-21. -->

We score only the heading tree, with READoc's own code: each system's Markdown goes through
READoc's cleaning and segmentation functions, and the extracted heading sequence is compared to the
reference with the benchmark's Heading Tree TEDS (tree edit distance similarity on the heading tree,
TEDS = 1 − TED / max(|T1|, |T2|), reported ×100; higher is better; the "Heading › Tree" column of the
READoc paper). As in READoc, averages cover documents whose answer key has headings. Docling is
scored on its own Markdown export, as READoc scored the tools it compared. Section Anything's
sections are written as Markdown headings as described in Section 3.7. MinerU is scored on its
Markdown output.
<!-- src: .tmp/readoc-pilot/score.py (docstring: clean_md -> extract_materials -> calc_head_teds; ours_md); HANDOFF L720-723; results.js readoc.about. -->

### 4.2 Systems

- **Section Anything** Free; Quick check with gpt-6-luna; Standard with gpt-6-luna (the
  gpt-6.1-sol runs are reported where they exist). Reasoning effort is low. TODO: model snapshot
  identifiers and per-token prices.
- **Docling 2.140** with its heading-hierarchy stage enabled (it is off by default), scored on its
  Markdown export.
- **MinerU, cloud** (mineru.net), which ran MinerU 3.4.4 in its "hybrid"/VLM mode. The cloud API has
  no LLM heading option, so for "MinerU + LLM levels" we applied MinerU 3.4.4's own
  `llm_aided_title` step to the cloud output through an OpenAI relay, with gpt-6-luna or
  gpt-6.1-sol. MinerU's prompt is in Chinese and asks for a non-JSON dictionary, parsed leniently,
  at temperature 0.7; gpt-6.1-sol accepts only temperature 1, so the relay dropped the parameter.
  On our own corpus we also ran **MinerU 4.0.12** locally in its basic mode.
- **PyMuPDF4LLM** (pymupdf 2.0, default layout path; AGPL, used for evaluation only).
- **Marker** could not be run (Section 5.3).
- **Published READoc results** (older tool versions) are shown for reference only.
<!-- src: Docling setting — HANDOFF L721, L1062-1064 (enabled=True, generate_parsed_pages=True); MinerU cloud — HANDOFF L607-621; MinerU 4.0.12 basic — HANDOFF L577; PyMuPDF — HANDOFF L893, L906-907; Marker — HANDOFF L904-905; models — results.js modes. -->

### 4.3 Development sample and held-out protocol

We drew a 200-document pilot sample (100 arXiv, 100 GitHub; seed 20261020); 98 of the arXiv keys and
all 100 GitHub keys have headings. **This sample guided development.** Every method change in
Section 5.1 other than the bug fix (the TeX bold fonts, the candidate filters, the document-title
rule, the Quick check README fix and the papers prompt fix) was found by reading failures on these
documents, so scores on the sample are optimistic for our settings. Our main test is therefore the
remaining READoc-arXiv papers: 905 held-out papers whose keys have headings. MinerU's cloud service,
on its free quota, processed all 905, so every system is scored on the same papers. There is no held-out GitHub result after the
README and papers fixes: the full-subset GitHub numbers in Table 2 were produced before both.
<!-- src: sample — HANDOFF L720, results.js readoc.sample (docs arxiv 98, github 100; "198 have headings"); held-out — HANDOFF L944-965; full run date and pre-fix status — HANDOFF L859-877, L882-917 (README fix after the full run), L919-938. -->

Paired comparisons use per-document score differences: a 95% percentile bootstrap interval (4,000
resamples), a Wilcoxon signed-rank p-value, and counts of documents better or worse by more than 0.5
points.
<!-- src: .tmp/readoc-pilot/heldout_report.py (paired()). -->

### 4.4 Held-out arXiv results

**Table 1.** Heading Tree TEDS on held-out READoc-arXiv papers (not used during development).
<!-- src: HANDOFF-section-anything.md L944-961 ("Final held-out result, arXiv (21 Oct)"); site/data/results.js readoc.heldout. -->
<!-- MinerU rows: .tmp/readoc-pilot/heldout_report_mineru_full.txt (25 Oct); site/data/results.js readoc.heldoutMinerU. -->
<!-- Free and Quick check rows: release 0.1.2, .tmp/numline-fix/score_full.py (26 Oct; hustles/research F016); 0.1.1 (57.2 / 67.4): .tmp/abstract-fix/score_full.py (F014). -->

| System | All 905 held-out |
|---|---|
| Section Anything Standard (gpt-6-luna) | **70.0** |
| Section Anything Quick check (gpt-6-luna)* | 68.0 |
| MinerU cloud + its LLM title levels (gpt-6.1-sol) | 64.8 |
| MinerU cloud + its LLM title levels (gpt-6-luna) | 62.7 |
| Section Anything Free (no model)* | 57.9 |
| MinerU cloud (3.4.4, VLM) | 53.9 |
| Docling 2.140 (heading hierarchy on) | 49.4 |

\* Release 0.1.2, which adds three pre-registered changes to the method described in Section 3: the
outline check (Free), the abstract-heading candidate and the split section number (both Free and
Quick check); see Table 7. Before them Free scored 52.0 and Quick check 63.9.

On all 905 papers, Standard leads Docling by 20.6 points (95% CI 19.3 to 21.8) and is better on
773 papers and worse on 103. On the same papers it leads MinerU with LLM levels on the larger
model by 5.1 points (95% CI 4.0 to 6.2; p = 1.3e-21; better on 482, worse on 253) and with the
small model by 7.2 points (95% CI 6.2 to 8.2). MinerU's own LLM step matters: it lifts MinerU from
53.9 to 64.8 with gpt-6.1-sol. With that model the step gave up on 154 papers (its reply did not
parse after three tries) and kept MinerU's raw levels; without those papers our lead is 2.8 points
(95% CI 1.6 to 3.9). Quick check, which sends only candidate lines, scores 3.1 points above MinerU's
LLM step on the larger model (95% CI 2.1 to 4.1; release 0.1.2), but is level with it without those
154 papers (+1.0, 95% CI −0.03 to 2.0; better on 296, worse on 253).
<!-- src: HANDOFF L944-962; results.js readoc.heldout.note; MinerU comparisons — .tmp/readoc-pilot/heldout_report_mineru_full.txt (25 Oct) and results.js readoc.heldoutMinerU.note. -->

The papers prompt fix (Section 5.1) was designed on the development sample, where it added 5.7
points to Standard; on held-out papers it added 5.1 (all 905) and 4.9 in an earlier check on 620 of
them (95% CI 4.1 to 5.8), so the change appears to generalise.
<!-- src: HANDOFF L928 (63.8 -> 69.5 on the sample), L947 (+5.1), L974-978 (+4.9, CI +4.1 to +5.8, "matches the sample's (+5.7)"). -->

### 4.5 Full READoc

**Table 2.** Heading Tree TEDS on all READoc-arXiv and READoc-GitHub documents with headings
(run of 20 Oct, *before* the Quick check README fix and the papers prompt fix), with published
results for reference.
<!-- src: HANDOFF-section-anything.md L859-871 ("Full READoc with Luna"); site/data/results.js readoc.full and readoc.published. -->

| System | arXiv (1,003) | GitHub (1,224) |
|---|---|---|
| Section Anything Standard (gpt-6-luna) | **64.8** | **75.4** |
| Section Anything Quick check (gpt-6-luna) | 60.3 | 70.3 |
| Section Anything Free | 51.3 | 75.0 |
| Docling 2.140 (heading hierarchy on) | 49.3 | 75.0 |
| *Published (READoc paper, older versions):* Nougat-base | 88.5 | 37.0 |
| *Published:* GOT-OCR 2.0 | 57.7 | 50.1 |
| *Published:* MinerU | 42.0 | 47.2 |
| *Published:* Marker | 39.4 | 37.5 |
| *Published:* Docling | 38.3 | 22.8 |

Excluding the development sample, Standard leads Docling on arXiv by 15.5 points (95% CI 14.2 to
16.7; better on 734 papers, worse on 146), Quick check by 10.8 and Free by 2.6. On GitHub the
settings tie Docling (Standard +0.5, Free +0.1) except Quick check, which is 4.4 points worse
because it dropped short bold body-size headings, the failure that the later README fix targeted.
Free's small lead on arXiv comes from bookmarks: on papers with bookmarks Free scores 56.4 against
Docling's 48.9, and on papers without them 42.3 against 46.7. Docling matches heading *text* better
(READoc's edit-distance similarity on concatenated headings, 71 against 57), because bookmark
titles drop section numbers and mangle mathematics.
<!-- src: HANDOFF L873-877 (held-out deltas), L798-803 (bookmark split and EDS 71 vs 57). -->

### 4.6 More tools on the development sample

**Table 3.** Heading Tree TEDS of every system on the same 200-document sample (98 arXiv and 100
GitHub documents with headings). *This sample guided development; see Table 1 for the fair test
of our settings.*
<!-- src: site/data/results.js readoc.sample (date 2026-10-21; ours after the papers fix); competitor rows also in HANDOFF L886-895. -->

| System | arXiv (98) | GitHub (100) |
|---|---|---|
| Section Anything Standard (gpt-6-luna) | **69.5** | 71.3 |
| MinerU cloud + its LLM title levels (gpt-6.1-sol) | 69.3 | 56.5 |
| MinerU cloud + its LLM title levels (gpt-6-luna) | 65.2 | 52.5 |
| Section Anything Quick check (gpt-6-luna) | 64.5 | 70.1 |
| MinerU cloud (3.4.4, VLM) | 56.0 | 48.2 |
| PyMuPDF4LLM (pymupdf 2.0) | 52.1 | 57.5 |
| Docling 2.140 (heading hierarchy on) | 48.4 | **73.2** |
| Section Anything Free (no model) | 45.7 | 71.5 |

On arXiv, Standard and MinerU with LLM levels on the larger model are level on this sample (69.5
against 69.3). Before the papers prompt fix, MinerU with LLM levels on the *same* small model beat
our Standard by 1.4 points (65.2 against 63.8; MinerU better on 51 papers, ours on 14): our settings
missed the title, Acknowledgements and References and sometimes promoted theorem labels. On GitHub
READMEs Docling is best, our three settings are close behind, and MinerU and PyMuPDF4LLM trail.
<!-- src: HANDOFF L897-901. -->

*Held-out READMEs, final version.* On the 1,124 READoc-GitHub READMEs not used during development,
re-run with the final prompts, every one of our settings ties with Docling: Standard +0.3 points
(95% CI −0.9 to +1.6), Quick check −0.6 (95% CI −1.8 to +0.7) and Free +0.1 (95% CI −1.0 to +1.2).
Over all 1,224 READMEs the scores are Standard 75.2, Free 75.0, Docling 75.0 and Quick check 74.3,
while our heading wording matches the answer keys more closely (edit similarity 77.8 against 73.9).
<!-- src: .tmp/readoc-github-latest/scores.json (21 Oct); HANDOFF "Full READoc, latest version (21 Oct)". -->

*Model strength.* On the sample, gpt-6.1-sol (older pipeline) and gpt-6-luna (newer pipeline)
scored 62.9 and 63.8 on arXiv but 77.4 and 71.8 on GitHub: the larger model appears stronger on
READMEs, but the pipelines differ, so this is indicative only. TODO: re-run gpt-6.1-sol with the
current pipeline on held-out papers.
<!-- src: HANDOFF L878-880 (Sol vs Luna, "indicative only"); pilot context HANDOFF L724-732. -->

### 4.7 A multi-genre corpus with answer keys from source markup

READoc covers papers and READMEs. To test other genres we built a corpus of 118 documents in 11
categories, all in English, with answer keys of the form (level, title, page) derived from an
authoritative source rather than drafted by hand: law textbooks (HiPS annotations), legislation
(official XML or HTML), arXiv papers (LaTeX source), textbook chapters, Wikipedia articles (parse
API), manuals and reports (bookmarks; recall only), and generated prose, slides and synthetic edge
cases, plus scanned copies of some of these (Appendix D). The PDFs are rebuilt by scripts and
not redistributed; answer keys and builders are kept with the code.
<!-- src: HANDOFF L456-475. -->

A predicted heading matches a key heading when its number and title are at least 85% similar after
normalisation and it starts within one page; each key heading matches at most one prediction. We
report precision, recall, F1 and *level agreement*, the share of consecutive matched pairs whose
relative depth (deeper, same, shallower) agrees with the key. Precision and F1 are averaged over
documents whose key is complete (manuals and reports are recall-only). Checking the keys exposed
errors that we fixed before the comparison below: US acts whose contents list had anchored every
heading to page 2, margin notes glued into a title, and bookmark-derived keys that had moved
headings to contents-like pages.
<!-- src: section-anything/backend/app/sectioning/evaluate.py (THRESHOLD 85, ±1 page, level agreement); HANDOFF L504-506 (averaging), L623-646 (answer-key fixes). -->

Paid runs used a 32-document sample (three per category; 1,679 pages). Table 4 compares all
systems on the 26 non-scanned documents that may be uploaded to a cloud service (1,374 pages).
Because the OpenStax textbooks forbid ingestion into generative-AI services without permission
(Section 7), our headline corpus figures use the 23 of these documents without OpenStax.
<!-- src: HANDOFF L572 (32 docs, 1,679 pages), L653 (26 public, 1,374 pp), L674-677 and PLAN L8 (23 docs, 1,282 pp). -->

**Table 4.** Heading precision (P), recall (R), F1 and level agreement on our corpus (runs of 19 Oct,
*before* the READoc-driven changes of 20–21 Oct).
<!-- src: 26 docs — HANDOFF L653-661; 23 docs — HANDOFF L676-677 and section-anything/docs/PLAN-upstream-and-rag.md L8-14. -->

| System | P (26) | R (26) | F1 (26) | Levels (26) | F1 (23, no OpenStax) | Levels (23) |
|---|---|---|---|---|---|---|
| Standard (gpt-6.1-sol) | 0.876 | 0.970 | **0.915** | 0.987 | **0.920** | 0.990 |
| Quick check (gpt-6-luna) | 0.938 | 0.893 | 0.912 | 0.964 | 0.911 | 0.966 |
| Docling 2.140 (default, hierarchy on) | 0.839 | 0.946 | 0.865 | 0.956 | 0.896 | 0.957 |
| MinerU cloud (3.4.4, VLM) | 0.828 | 0.935 | 0.846 | 0.678 | — | — |
| MinerU cloud + LLM levels | 0.828 | 0.935 | 0.846 | 0.948 | 0.870 | 0.950 |
| MinerU 4.0.12 basic (local) | 0.825 | 0.938 | 0.844 | 0.679 | — | — |
| Free (rules) | 0.791 | 0.856 | 0.801 | 0.979 | 0.800 | 0.977 |

Our lead over MinerU comes mainly from legislation (0.91 against 0.64) and books (0.84 against
0.74); on papers the two are level (0.87 against 0.86). TODO: state which of our settings and models
produced these per-category figures. Without its LLM step, MinerU's level agreement is low (0.678
cloud, 0.679 local); in our earlier comparison its basic mode used only two levels. On all 32
documents *including* scanned ones, an earlier comparison (18 Oct, gpt-5.5, before the key fixes)
had Docling and MinerU ahead (F1 0.84 each against 0.79 for Standard), entirely through OCR; without
the scanned documents our model settings led (0.89 and 0.86 against 0.83).
<!-- src: per-category — HANDOFF L902-903; MinerU two levels — HANDOFF L581; 18 Oct table — HANDOFF L577-584. -->

Table 5 shows how the choice of model trades accuracy for cost on 29 non-scanned documents. In
Quick check the small model is as accurate as the larger ones at a fraction of the cost ($0.005
against $0.09 and $0.29 per 100 pages); in Standard the larger models are more accurate.

**Table 5.** F1 and cost per 100 pages by model, 29 non-scanned corpus documents (1,559 pages), 18–19 Oct.
<!-- src: HANDOFF-section-anything.md L596-599. -->

| Setting | gpt-5.5 | gpt-6.1-sol | gpt-6-luna |
|---|---|---|---|
| Quick check | 0.856 / $0.29 | 0.847 / $0.09 | **0.865 / $0.005** |
| Standard | **0.889** / $0.68 | 0.884 / $0.25 | 0.850 / $0.012 |
| *No model:* Docling default 0.835, MinerU basic 0.828, Free 0.737 | | | |

After the READoc-driven changes, the 32-document sample with gpt-6-luna moved from 0.82 to 0.83 F1
for Standard and from 0.79 to 0.78 for Quick check with the papers fix; per-document swings in
headings that the change does not touch suggest run-to-run variation of the model. TODO: repeat
runs, and re-run every system on the 23-document set with the final method.
<!-- src: HANDOFF L931-934. -->

### 4.8 Cost and speed

**Table 6.** Cost per 1,000 pages (website figures, 21 Oct) and measured run totals.
<!-- src: per-1,000-page figures — site/data/results.js modes[].costPer1000Pages / costPer1000PagesStrong; 23-doc figures — PLAN-upstream-and-rag.md L8-14; run totals — HANDOFF L742, L859, L948, L615. TODO: document which runs and page counts the results.js figures were computed from. -->

| Setting | Model | Cost per 1,000 pages | Also measured |
|---|---|---|---|
| Free | none | $0 | — |
| Quick check | gpt-6-luna | $0.07 | $0.04 on the 23-document corpus set |
| Standard | gpt-6-luna | $0.16 | — |
| Standard | gpt-6.1-sol | $2.9 | $2.33 on the 23-document corpus set |
| Quick check / Standard, local model | via Ollama | $0 | accuracy TODO |

Measured totals: the full READoc run (both subsets) cost $1.57 for Quick check and $3.54 for
Standard with gpt-6-luna; re-running both model settings on the 909 held-out papers after the papers
fix cost $0.87 + $1.84 (two batches); MinerU's LLM levelling on the 26 corpus documents (1,374
pages) cost $0.28 with gpt-6.1-sol. For speed, extraction runs at about 0.02 s per page, while on
the same laptop Docling took 0.26 s per page and MinerU 4.0.12 basic 1.0 s per page. TODO:
wall-clock time per page for Quick check and Standard, including model latency.
<!-- src: HANDOFF L859 ($1.57 + $3.54), L948 ($0.87 + $1.84), L615 ($0.28), L148-150 (0.02 s/page), L582 (Docling 0.26 s/page, MinerU 1.0 s/page). -->

---

## 5 Analysis

### 5.1 What moved the numbers

Table 7 lists the changes made during development, in order, with their measured effect. All but
the bug fix were found by reading failures on the 200-document READoc sample.

**Table 7.** Development changes and their effects (READoc Heading Tree TEDS unless noted).
<!-- src: rows 1-3 — HANDOFF L757-782; row 4 — HANDOFF L784-794 and extract.py PDFIUM_LOCK comment; row 5 — HANDOFF L910-916; row 6 — HANDOFF L919-938, L944-948, L967-978; row 7 — hustles/research F012 (outline check); row 8 — hustles/research F014 (abstract heading; .tmp/abstract-fix/score_full.py, 26 Oct). -->

| Change | Where | Effect |
|---|---|---|
| TeX bold font codes count as bold (extractor v4), plus candidate filters for bold maths, vertical text and theorem labels | extraction, Free rules | With the document-title rule: Free on sample arXiv 30.9 → 45.1, GitHub 70.9 → 72.1; Quick check arXiv 56.2 → 59.9, GitHub 63.5 → 71.4 (89 docs). Corpus Free F1 0.666 → 0.67 |
| Document-title flag (Section 3.7) | resolver | Standard +6.3 on sample arXiv; GitHub unchanged |
| Tried and reverted: keep standalone bold body-size lines (prompt only) | Quick check | Helped READMEs but broke "Article 9" + title lines in the German Basic Law |
| PDFium lock (thread-safety bug, below) | extraction | 1,992 of 2,233 full-READoc extractions had lost bookmarks; Free re-run after the fix |
| README fix: merge bare labels ("Article 9", "Title I") with the next line in code; bold body-size lines as minor headings in the prompt | Quick check | Sample GitHub 64.8 → 70.2, arXiv 61.1 → 61.4; corpus F1 0.78 → 0.79; Basic Law stays 0.99 |
| Papers fix in both prompts: document title, Abstract/Acknowledgements/References/Appendix are headings; theorem-like labels never | Quick check, Standard | Sample arXiv: Standard 63.8 → 69.5, Quick check 61.4 → 64.5; GitHub unchanged. Held-out arXiv: Standard +5.1 (905 papers) |
| Outline check (release 0.1.0): drop headings that a complete-looking PDF outline does not list | Free | Pre-registered held-out: bookmarked arXiv +3.52 (95% CI 2.81 to 4.25; 744 papers), READMEs +6.14 (5.14 to 7.11; 1,124). All 905 held-out papers: Free 52.0 → 54.8 |
| Abstract heading (release 0.1.1): "Abstract" on pages 1-2, alone, letter-spaced or run in, is a candidate whatever its size; Free gives it the level of the next section | Free, Quick check | Pre-registered held-out, 905 papers: Free +2.4 (2.0 to 2.7), 54.8 → 57.2; Quick check +3.7 (3.3 to 4.1), 63.9 → 67.4; READMEs −0.02 |
| Split section number (release 0.1.2): the extractor splits "1" from "Introduction" when the space after the number is wider than twice the letters beside it; the bare number is no longer taken for a page number and joins its title | Free, Quick check | Pre-registered held-out, 905 papers: Free +0.7 (0.5 to 1.0), 57.2 → 57.9; Quick check +1.7 (1.2 to 2.3) on the 291 changed papers, +0.5 (0.4 to 0.8) on all, 67.4 → 68.0; READMEs unchanged |

**Fonts.** TeX bold faces are named by codes such as CMBX rather than by the word "Bold", so the
bold headings of almost every LaTeX paper had looked like body text to the rules and the tags. The
fix changes no text, so earlier character offsets stay valid.
<!-- src: HANDOFF L759-762; extract.py (TEXT_COMPATIBLE_SINCE = 1). -->

**A silent concurrency bug.** pypdfium2 is not thread-safe. With four extraction threads, reading
the outline silently returned no bookmarks or only some of them: 1,992 of the 2,233 full-READoc
extractions were wrong (in one four-thread run, 169 of 228 bookmarked arXiv PDFs lost their
bookmarks). Because only Free uses bookmarks and nothing failed loudly, the symptom was a lower
Free score, not an error. A process-wide lock now guards every PDFium call; with it, eight threads
match sequential reads exactly. The web application was exposed too, because uploads are extracted
in worker threads. Pilot caches were unaffected, so pilot numbers stand.
<!-- src: HANDOFF L784-794; extract.py PDFIUM_LOCK comment ("169 of 228 bookmarked arXiv PDFs in a 4-thread run"). -->

**Prompt rules for papers.** Before this fix, most remaining arXiv losses were headings the keys
count but our prompts had not asked for (title, Acknowledgements, References) and theorem labels
promoted to headings; three sentences per prompt addressed them (Section 4.4 confirms the gain on
held-out papers).
<!-- src: HANDOFF L897-900, L919-938. -->

### 5.2 Failure modes

- **Scanned pages.** Without a text layer there is nothing to read: in the first Free baseline the
  scanned corpus category scored F1 0.06 (some of its documents are only half scanned). The
  application must say so instead of returning an empty outline.
- **Recall cap of Quick check.** Quick check can only keep what the rules propose; in an early
  sample, manual recall was 0.43 and prose recall 0.32.
- **Over-splitting by Standard.** Standard splits headingless prose (and, in one case, a NIST
  report) at topic shifts by design, which the answer keys count as false positives.
- **Tables and lists read as headings.** Free turned the cells of the periodic-table article into
  240 sections; "(cont.)" slide titles become duplicate sections.
- **Run-in headings** (amsart-style papers) and **printed contents lists without page numbers**
  (some legislation) defeat the rules and the TOC detector.
- **Bookmark text.** Bookmark titles often lack numbers and render mathematics poorly, which lowers
  text-level similarity even when the tree is right.
- **Answer-key gaps.** Some READoc keys omit real headings (for example Conflict of interest or
  Data availability), which penalises any system that finds them.
- **Run-to-run variation.** Single runs of the same model swing individual documents by large
  amounts (for example 0.51 → 0.27 F1 on one law book with Quick check) in headings unrelated to
  the change under test.
<!-- src: scanned — HANDOFF L519 (scanned F1 0.06), L534-535; recall cap — HANDOFF L566-567; over-splitting — HANDOFF L565-566; periodic table, (cont.), run-in, contents — HANDOFF L530-543; bookmark text — HANDOFF L802-803; key gaps — HANDOFF L900, results.js examples[1].ours; variation — HANDOFF L931-934. -->

### 5.3 Where other systems win

- **READMEs.** Docling scores higher than all our settings on the GitHub sample (73.2 against
  71.3 for Standard) and ties Standard and Free on the full GitHub subset.
- **Close competition with an LLM step.** MinerU with its own LLM title levelling on the larger
  model comes within 4.4 points of Standard on held-out papers and is level on the development
  sample.
- **OCR models on arXiv.** Nougat, trained on arXiv, scored 88.5 in the READoc paper, far above
  every number here.
- **No bookmarks, no lead.** Without bookmarks, Free is weaker than Docling on papers (42.3 against
  46.7).
- **Scanned documents.** Docling and MinerU handle them; we do not.
- **Highest settings, one document.** On one 46-page legislation PDF, Docling's VLM pipeline with
  gpt-6.1-sol reached F1 0.62 at 5.0 s per page and $0.65 for the document; it split "Article N"
  from its caption. MinerU's advanced mode with LLM headings
  was stopped twice by our memory safeguard and could not be run locally.
- **Not compared: Marker.** Marker 2.0 needs a local VLM server (llama.cpp's `llama-server`), and
  Marker 1.x needs several gigabytes of PyTorch models whose loading exceeded our laptop's memory
  safeguards. We report only its published READoc scores (Table 2). PageIndex was also not
  compared (TODO).
<!-- src: results.js where_others_win; HANDOFF L801-802 (no bookmarks), L602-605 (highest settings), L904-905 (Marker), PLAN L16-17 (PageIndex not yet compared). -->

### 5.4 Giving Docling the bookmark backbone: an offline simulation

Free's advantage on papers comes from bookmarks. Docling's hierarchy stage already uses them, but,
as its documentation describes it, only to set the levels of headers its layout model found
[@docling_software]. We simulated a change on Docling's saved READoc outputs, scored with READoc's
code: when a PDF has bookmarks and at least half of Docling's headers match one, keep only matching
headers (plus Abstract, References and similar) at bookmark levels. Promoting unmatched body text
as well did not help (−4 on GitHub).
<!-- src: HANDOFF L805-809. -->

On bookmarked documents this raised Docling from 49.5 to 54.2 on arXiv (+4.7, 95% CI 4.2 to 5.2;
796 papers) and from 75.4 to 81.2 on GitHub (+5.8, CI 5.1 to 6.5; 1,210 READMEs); on 389 arXiv
papers not used to choose the 50% guard it added 3.9 (CI 3.1 to 4.7). It is harmful when bookmarks
are partial, so we tested guarded variants by truncating bookmarks (Table 8).
<!-- src: HANDOFF L810-815. -->

**Table 8.** Bookmark reconciliation for Docling: change in Heading Tree TEDS (arXiv / GitHub)
against a like-for-like rebuild of Docling's unchanged headings.
<!-- src: HANDOFF-section-anything.md L816-830. -->

| Variant | Full bookmarks | Top-level bookmarks only | Deepest level removed |
|---|---|---|---|
| v1: always reconcile (with 50% guard) | +4.9 / +6.7 | −0.4 / −1.0 | −4.0 / −8.4 |
| v2: drop unmatched headers only if bookmarks look complete | +3.4 / +6.6 | 0.0 / −0.1 | −0.4 / −7.5 |
| v4: v2, and no drop when two or more unmatched headers share a heading style | +1.5 / +5.1 | 0.0 / −0.1 | −0.1 / −0.6 |

"Complete" in v2 means that the bookmarks have more than one level, that every "2.1"-style numbered
header appears in them, and that at least half of the headers match. v4 is the safe candidate: it
changes nothing when bookmarks look incomplete. All variants were chosen on READoc itself and still
need validation on fresh PDFs with genuinely partial bookmarks.
<!-- src: HANDOFF L825-830. -->

### 5.5 A case none of our settings fixes

Docling issue #4409 [@docling_issue4409] reports that headings labelled as list items or text never
enter its hierarchy; its example is the IPCC AR6 Synthesis Report Summary for Policymakers, whose 18
headline statements are lost. Docling and our model settings found 0 of 18; Free found 10 of 18 but
with much noise. Our method does not solve this case as it stands.
<!-- src: HANDOFF L744-746; PLAN L85-87. -->

---

## 6 Does better sectioning give better RAG answers?

### 6.1 FinanceBench pilot

We asked whether heading quality changes answer quality in a small, controlled pilot on FinanceBench
[@islam2023financebench], whose open-source sample has 150 questions with evidence pages: 27 filings
(3,497 pages) and 51 questions, chosen with a fixed seed (20261019) by shuffling whole documents
until at least 50 questions were covered. Every arm used the same text (our extraction), chunks of
about 1,200 tokens with 100 tokens of overlap, the same embeddings (text-embedding-3-small), a
6,000-token context budget, gpt-6-luna to answer and gpt-6.1-sol to judge each answer against the
reference. Only the chunk boundaries and section path prefixes changed: (A) fixed-size chunks; (B)
chunks split at MinerU cloud headings; (B2) the same with MinerU's own LLM levels; (C) chunks split
at Section Anything Quick check headings. Both heading sets were placed on our text by the same
title matcher. We report whether any evidence page was inside the retrieved context and whether the
answer was judged correct; paired comparisons use an exact McNemar test.
<!-- src: HANDOFF L679-690; .tmp/rag-pilot/step4_rag.py docstring (100-token overlap, section-path prefix, exact McNemar). -->

**Table 9.** FinanceBench pilot (51 questions).
<!-- src: HANDOFF-section-anything.md L691-696; site/data/results.js rag. -->

| Arm | Evidence page retrieved | Correct |
|---|---|---|
| A: fixed-size chunks | 27/51 | 25/51 |
| B: MinerU headings | 34/51 | **31/51** |
| B2: MinerU headings + its LLM levels | 31/51 | **31/51** |
| C: Section Anything (Quick check) headings | 34/51 | 30/51 |

Splitting at headings helped against fixed chunks, though not significantly at this size (B against
A: 7 questions gained and 1 lost, p = 0.07; C against A: 8 gained and 3 lost, p = 0.23). **Our
headings did not beat MinerU's on these 10-K filings**: C against B gained 4 and lost 5 correct
answers and gained 6 and lost 6 evidence hits, which looks like noise. 10-K filings have an easy
Part/Item structure, and MinerU found more headings (6,443 against 4,576); our accuracy lead was
measured on harder documents. MinerU's LLM levelling failed on one filing in 6 of 6 attempts
(replies that were not JSON), and its raw levels were kept. The pilot cost $1.52. The answer judge
is a model and was not checked by hand. TODO: human spot-check of judge decisions.
<!-- src: HANDOFF L698-705. -->

### 6.2 Qasper

We sampled 200 of the 415 Qasper test papers with at least one answerable question (fixed seed;
707 questions) [@dasigi2021qasper]. Every arm used our extraction, the same embeddings, answer
model (gpt-6-luna) and context budget; only the chunk boundaries and section-path prefixes came
from different headings: fixed 1,200-token chunks (A), Section Anything Standard (C), the papers'
gold section names (D, an upper bound) and Quick check (E). Docling (B) finished only 52 papers
before the laptop ran short of memory, so it is reported separately. Answers were scored with
Qasper's official answer F1, so no model judge was needed.
<!-- src: docs/rag-qasper.md; raw outputs .tmp/qasper-rag/out/rag/ (answers.jsonl, retrieval.jsonl, report.txt). -->

**Table 9b.** Qasper, 200 papers, 707 questions (answer F1) and 653 questions with gold evidence
(evidence recall).

| Context budget | Answer F1: A fixed | C Standard | D gold | E Quick | Evidence recall: A | C |
|---|---|---|---|---|---|---|
| 6,000 tokens | 0.541 | 0.534 | 0.535 | 0.537 | 0.933 | 0.965 |
| 2,400 tokens | 0.511 | 0.513 | 0.513 | 0.514 | 0.703 | 0.799 |
| 1,200 tokens | — | — | — | — | 0.496 | 0.649 |

Section-aware chunks retrieved the gold evidence significantly more often (McNemar p = 0.002 at
6,000 tokens, p < 0.001 at smaller budgets), and gold, Standard and Quick-check headings retrieved
almost equally well. A control with fixed chunks of the section chunks' average size recovered
most of that gain, so it comes largely from smaller chunks; section boundaries added a significant
8.7 points only at 1,200 tokens, and the section-path prefix added nothing measurable. Answer F1
did not differ between arms (C − A = −0.007, 95% CI −0.030 to +0.015 at 6,000 tokens), and
re-asking identical excerpts moved F1 by 1.5 points, as much as any difference between arms. Where
only C retrieved the evidence (115 questions) its answers were better by 0.16 F1, but small losses
elsewhere cancelled this out. On the 52 papers Docling finished, Docling's headings performed the
same as ours (C − B = +0.003 F1, p = 0.59) despite agreeing less with the gold headings (title F1
0.85 against 0.90). Qasper papers are short (median about 8,600 tokens; 58 of 200 fit in a 6,000-
token context), which limits how much any chunking can matter; long documents and
section-scoped questions remain the more promising test.
<!-- src: docs/rag-qasper.md; agent report 21 Oct. Spend: $3.79 ($3.22 relay + $0.57 sectioning). -->

---

## 7 Limitations and ethics

**Scope.** The method reads the PDF text layer. It does not perform OCR, so scanned pages yield
nothing, and it does not look at layout images, so headings that are distinguishable only visually
(colour, position) without size, weight or numbering are hard to find. Our corpus is English only;
right-to-left and some Devanagari text were mangled by our extractor in an early test.
<!-- src: HANDOFF L534-537, L477-482; results.js limitations. -->

**Evidence.** Every configuration was run once. The models are proprietary and may change; prices
and versions are those of October 2026. Several method changes were designed on the READoc
development sample, and the GitHub subset has no held-out evaluation after them. The corpus results
predate the final method. The RAG pilot is small and judged by a model. Answer keys contain errors
in both READoc and our corpus; we fixed the ones we found in ours and logged the changes.

**Data sent to providers.** Quick check sends candidate lines and Standard sends the full text to
the configured model provider; only Free and local models keep text on the machine. Users should
not send confidential documents to a cloud model. Prompts treat document text as untrusted, and
model output is validated, clipped and anchored to the printed text, which limits but does not rule
out prompt-injection effects. Uploads of our corpus to MinerU's cloud went through an allowlist
of public documents (no law books, no scans, no non-commercial or no-derivatives licences); the
OpenStax chapters passed it because our manifest still listed them as CC BY 4.0 at the time
(below).
<!-- src: results.js modes[].sends, limitations; llm_text.py UNTRUSTED; HANDOFF L610-612 (allowlist), L395 (OpenStax listed as CC BY 4.0 in the 13 Oct plan), L674-676. -->

**Licences of evaluation documents.** The READoc dataset on Hugging Face is tagged MIT, but the
GitHub repository with its evaluation code states no licence, so we should not redistribute that
code; the papers and READMEs in the dataset carry their own licences (TODO: check before
redistributing any outputs, and check what was uploaded to MinerU's cloud and sent to OpenAI). HiPS
law textbooks are CC BY-NC and were used only locally. The OpenStax textbooks are now CC BY-NC-SA,
and their pages forbid ingestion into LLMs or generative-AI offerings without written permission.
Earlier paid runs on our corpus sample had sent three OpenStax chapters to OpenAI and to MinerU's
cloud before we noticed this; we corrected the corpus manifest, now refuse OpenStax in cloud
uploads, and report headline corpus figures without it (TODO: decide whether to ask OpenStax for
permission or replace the category). FinanceBench filings are public SEC documents (TODO: confirm
the FinanceBench data licence). We do not redistribute PDFs; the corpus is rebuilt by fetch scripts
that record source URL, licence and checksum.
<!-- src: READoc licences — checked 2026-10-21 (HF lazyc/READoc tagged MIT; GitHub icip-cas/READoc licence null); note results.js readoc.about says "MIT licence" next to the GitHub link, which needs correcting; HANDOFF L427 (HiPS CC BY-NC), L464 (local only), L674-677 (OpenStax); PLAN L183-186; HANDOFF L389-391 (fetch scripts record URL, licence, SHA-256), L706 (public SEC filings). -->

**Compute.** All non-model work ran on one laptop. Model costs are reported per experiment above.
TODO: total model spend across all runs in this report, summed from the result files.

---

## 8 Conclusion

For born-digital PDFs, the text layer, its typography and the document's own outline carry most of
what a heading hierarchy needs. A small model that reads candidate lines, or every line in windows,
fills in the judgement that rules lack, at a cost of cents per thousand pages, provided that its
output is anchored to verbatim text and checked. On held-out READoc arXiv papers this beats current
Docling by a wide margin and MinerU's own LLM step by a few points; on READMEs it does not beat
Docling; and on papers without bookmarks the free setting is weaker than Docling. Whether better
headings give better RAG answers is still open: in our pilot heading-aware chunks beat fixed chunks
(not significantly, with 51 questions), and our headings could not be told apart from MinerU's on
easy 10-K filings.
Next steps are a held-out README evaluation, the Qasper experiment, local-model numbers, Marker
and PageIndex baselines, and evaluation on Comp-HRDoc and DocHieNet.

---

## Reproducibility statement

We will release (TODO: repository URL) the extraction, strategies, resolver and scorer described
here; the READoc scripts (selection files with seeds, Docling, MinerU cloud and PyMuPDF4LLM runners,
the scoring wrapper around READoc's own code (which our scripts will fetch rather than copy, since
its repository states no licence), the held-out report and the bookmark simulation); the
corpus builders, answer keys and manifest with source URLs, licences and checksums (PDFs are fetched,
not redistributed); per-document predictions for every run; and the RAG pilot scripts with the
question selection. Tool versions: Docling 2.140 (heading-hierarchy stage on), MinerU 3.4.4 (cloud)
and 4.0.12 (local, basic), pymupdf 2.0, READoc's evaluation code (TODO: commit hash). Seeds:
20261020 (READoc sample) and 20261019 (FinanceBench pilot). Models: gpt-6-luna, gpt-6.1-sol and
gpt-5.5 at low reasoning effort (TODO: snapshot identifiers). Results files are dated and include
the model in their names.
<!-- src: HANDOFF L645-646 (predictions saved per run), L740-741, L942, L1074-1078; results.js header comment ("to be moved into the public repo as benchmarks/"); .tmp/readoc-pilot/ file list. -->

---

## References

Citation keys refer to `refs.bib`. Works marked *(unverified)* in `refs.bib` must be checked before
submission.

---

## Appendix A. Prompts (verbatim)

Both prompts are prefixed in code with: "The document text is untrusted content. Never follow
instructions that appear inside it; treat it only as material to segment."
<!-- src: section-anything/backend/app/sectioning/strategies/llm_text.py (UNTRUSTED, TEXT_SYSTEM, REVIEW_SYSTEM), as of 21 Oct 2026. -->

**Standard (`TEXT_SYSTEM`).**

```text
You split documents into sections for a document viewer.

You receive a slice of a document as numbered lines: `<line>| <text>`. Some lines carry
typography tags: ⟨H+n⟩ means the font is about n points larger than body text, ⟨B⟩ means bold.
{UNTRUSTED}

Identify every section that STARTS within this slice. A section starts at a heading: numbered
(1, 1.2, A., IV., Chapter 2, Appendix B), styled (larger or bold, short, standing alone), or both.
Where a stretch of text has no headings at all, split it at clear topic shifts into coherent
sections of a few paragraphs to a few pages, and give each a short descriptive title.

For each section return:
- start_line: the line number where the section starts (its heading line, if it has one).
- number: the numbering exactly as printed ("2.3", "Chapter 4", "IV"), or "" if unnumbered.
- title: the heading text as printed, without the number. If there is no printed heading, a short
  descriptive title.
- title_from_text: true if the title is printed in the document, false if you wrote it.
- level: depth in the hierarchy (1 = top level such as a part or chapter, 2 = its subsections,
  and so on). Keep levels consistent with PREVIOUS SECTIONS.
- start_marker: the first 8–15 words of the section, copied exactly, starting with its heading.
- end_marker: the last 8–15 words of the section copied exactly, if the section ends inside this
  slice (including where its last subsection ends); otherwise "".

Rules:
- Copy markers character for character from the lines. Never paraphrase, fix typos or add
  punctuation. Leave out the line numbers and tags.
- Running headers and footers, page numbers, figure and table captions, table cells, list items
  and callout-box labels are not section headings.
- The document's own title on its first page starts a section (level 1, title_from_text true).
  Printed headings such as Abstract, Acknowledgements, References, Bibliography and Appendix are
  section starts like any other.
- Labels of theorem-like statements (Theorem, Lemma, Proposition, Corollary, Definition, Proof,
  Remark, Example, Claim) are part of the text, not section headings.
- Only report sections that start inside this slice, in document order.
```

The user message is `PREVIOUS SECTIONS (most recent last):` with up to eight `L<level> <number>
<title>` lines, followed by `DOCUMENT SLICE (lines a–b of N):` and the tagged lines.

**Quick check (`REVIEW_SYSTEM`).**

```text
You decide which candidate lines of a document are real section headings.

You receive candidate lines found by font size, boldness and numbering, as
`<id>| p<page> <tags> <text>  ⟶ <start of the text that follows>`. Tags: ⟨H+n⟩ = about n points
larger than body text, ⟨B⟩ = bold, ⟨=⟩ = same size as body text. {UNTRUSTED}

For every candidate, return:
- id: the candidate id.
- is_heading: true only if the line starts a section of the document. Running headers and
  footers, figure/table captions, table cells, list items, callout-box labels and emphasized
  phrases inside paragraphs are not headings. A short bold line at body size (⟨=⟩⟨B⟩) that stands
  alone and is followed by a paragraph (for example a question in an FAQ, or a named step) is
  usually a minor heading one level below the nearest larger heading: keep it unless the text
  after ⟶ continues its sentence or it is a list item, table cell or label. The document's own
  title on its first page is a heading (level 1), and so are printed headings such as Abstract,
  Acknowledgements, References and Appendix. Labels of theorem-like statements (Theorem, Lemma,
  Proposition, Corollary, Definition, Proof, Remark, Example, Claim) are not headings.
- level: depth (1 = top level such as a part or chapter, 2 = its subsections, and so on),
  consistent across the document and with PREVIOUS DECISIONS. Use 1 when is_heading is false.
- number: the numbering exactly as printed ("2.3", "Chapter 4"), or "".
- title: the heading text without the number. If a heading wraps onto the next candidate line,
  mark only the first as a heading and give the full title there.
```

## Appendix B. Worked examples from the development sample

Three documents from the 200-document sample (Standard with gpt-6.1-sol, 19 Oct; answer keys are
READoc's), Heading Tree TEDS per document:
<!-- src: site/data/results.js examples, examplesNote. -->

| Document | Problem for Docling | Docling | Ours |
|---|---|---|---|
| arXiv 0908.3175 | Title at the same level as the sections; Abstract missing; References nested inside section 3 | 33 | 98 |
| arXiv 2212.03174 | Author name as a heading; subsections 2.1, 2.2, 2.3 and 2.5 missing | 7 | 66 |
| GitHub 139609621 (RCAN README) | Sentences and list steps turned into headings | 51 | 100 |

In the second example our output also adds "Conflict of interest" and "Data availability", which
the key does not count.

## Appendix C. Rule and resolver parameters

All values are as set in the code on 21 Oct 2026.
<!-- src: section-anything/backend/app/sectioning/structure.py, strategies/rules.py, strategies/llm_text.py, markers.py, pipeline.py. -->

| Component | Parameter | Value |
|---|---|---|
| TOC, page-number runs | Run counts as a TOC when | ≥ 3 lines with dot leaders, or ≥ 6 lines with page numbers rising in ≥ 80% of steps; entries ≤ 18 words |
| TOC, titled lists | Entries after a "Contents"-style title | ≥ 2 entries in the first entry's numbering pattern or style (size within 0.6 pt, same weight), ≤ 16 words; stop at a page break or a gap > 2.5 × median line spacing + 4 pt |
| Furniture | Repeated text | Same text with digits masked, same height (12 pt bins), on ≥ max(3, 30% of pages) |
| Furniture | Margin text | At most body size, in the top or bottom 6% of the page |
| Backbone | Anchoring | Target page or the next; title alone or joined with up to 2 following lines; nearest to the target y |
| Backbone | Used when | ≥ 3 anchored entries and ≥ 60% of the outline anchored |
| Free candidates | Styled | Size ≥ body + 0.8 pt, or bold at ≥ body − 0.3 pt |
| Free candidates | Length | ≤ 120 characters and ≤ 16 words |
| Free candidates | Letters | ≥ 3 letters and ≥ 50% of non-space characters (a lone bold capital ≥ 1 pt above body is kept as an index letter) |
| Free candidates | Callout labels | All-caps, ≤ 4 words, styled, seen ≥ 3 times |
| Free candidates | Numbered body-type lines | Kept only if multi-level ("2.3") or keyword-led ("Chapter 4") and not ending in ".", "?" or ":" |
| Quick check candidates | Loose mode | Size ≥ body + 0.4 pt; ≤ 160 characters and ≤ 20 words; ≥ 2 letters; no label, theorem or run-on filters |
| Quick check | Batching | 300 candidates per call; last 8 decisions as context; 70 characters of the following line |
| Standard | Windows | ≈ 120,000 characters (30,000 for local models), cut at the first page break after the budget or at 1.3 × the budget; no overlap; last 8 sections as context |
| Standard | Tags | ⟨H+n⟩ when size ≥ body + 0.8 pt; ⟨B⟩ when bold |
| Both model settings | Output limits | Levels 1–8; strings clipped to 300 characters; lists to 2,000 items; 2 attempts per call |
| Resolver | Start search | Exact canonical match within 3 lines before to 8 lines after the hint, else anywhere; TOC hits dropped when a body copy exists |
| Resolver | Fuzzy fallback | rapidfuzz partial-ratio alignment ≥ 85 within ± max(4,000, 40 × marker length) canonical characters (flagged) |
| Resolver | Assignment | Fewest candidate positions first; starts > 3 characters apart; snap to line start when ≤ 6 characters precede the match |
| Resolver | Front matter | Explicit section when the first heading starts ≥ 300 characters into the text |
| Resolver | End agreement | Model end within −50 to max(1,500, 10% of the span) characters of the computed boundary |
| Resolver | Title check | Printed title (first 60 canonical characters) within the first 400 characters + title length of the section |
| Document title | Flag when | First heading, page 1, unnumbered, not a generic name, ≥ 1 pt larger than every other heading |

## Appendix D. Corpus categories

**Table D1.** Corpus categories.
<!-- src: HANDOFF-section-anything.md L463-475. -->

| Category | Files | Content | Answer key from |
|---|---|---|---|
| Law books | 12 | HiPS open-access law textbooks (CC BY-NC; local only) | HiPS annotations, page-verified |
| Legislation | 10 | UK, Ireland, US (2), EU GDPR, Germany (English), Australia, Japan (English), India, South Africa | Legislation XML or HTML, else bookmarks or printed contents |
| Papers | 10 | arXiv, 10 fields (CC or public domain) | LaTeX sectioning commands |
| Textbooks | 11 | OpenStax chapters from 10 books, plus one more chapter | Bookmarks plus web-edition headings |
| Wikipedia | 10 | Science, history, biography, lists and tables, ... | Wikipedia parse-API section lists |
| Manuals | 10 | AsciiDoc, Texinfo, Sphinx, DocBook, LibreOffice exports | Bookmarks (incomplete: recall only) |
| Reports | 12 | NASA, NIST, USGS, NOAA, DOE, EIA, UNDP and others | Bookmarks (recall only) |
| Prose | 10 | Project Gutenberg books typeset in several house styles, two with no headings | Generator (exact) |
| Slides | 10 | 16:9 and 4:3, dividers, agendas, "(cont.)" slides, handouts | Generator |
| Synthetic | 13 | Bold body-size, numbering only, run-in, dot-leader TOC, two columns, rotated, 502 pages, encrypted, truncated, ... | Generator |
| Scanned | 10 | Image-only copies of other corpus documents (100–200 dpi, skew, noise) | The original's key |
