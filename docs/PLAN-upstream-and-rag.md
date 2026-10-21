# Plan: upstream contributions, RAG proof, launch and corpus growth

Researched 19 Oct 2026 (web and GitHub API, read-only). Not started. Links were checked on
that date; review speeds are rough (last 90 days).

## Where we stand

| 23 public docs, no OpenStax (1,282 pp) | F1 | Levels | Cost / 1,000 pages |
|---|---|---|---|
| Standard (gpt-6.1-sol) | 0.920 | 0.990 | $2.33 |
| Quick check (gpt-6-luna) | 0.911 | 0.966 | $0.04 |
| Docling default (heading-hierarchy stage on) | 0.896 | 0.957 | $0 (local) |
| MinerU cloud + its LLM leveling | 0.870 | 0.950 | free quota + LLM |
| Free (rules) | 0.800 | 0.977 | $0 |

With the 3 OpenStax docs included (26 docs) our lead looked larger (0.915 vs 0.865). Public
claims should use the 23-doc set. PageIndex (39k stars, a competitor) claims about $0.001 per
page for its heading tree. Compare against it before launching.

## 1. Where to contribute (ranked)

1. **LightRAG** (HKUDS, MIT, no CLA; 134 outside PRs merged, median under 1 day).
   - Its heading-based chunker ("P") splits on `heading`/`level`/`parent_headings`. Its docs
     warn that P depends on the parser getting headings right.
   - Open issue [#4226](https://github.com/HKUDS/LightRAG/issues/4226): MinerU/Docling headings
     arrive flat or skip levels, which breaks P.
   - **Route:** our own pip package registering a `lightrag.parsers` entry point
     ([ThirdPartyParser.md](https://github.com/HKUDS/LightRAG/blob/main/docs/ThirdPartyParser.md)),
     so no upstream PR is needed. Then post the benchmark on #4226 and send a small docs PR
     listing the package. A maintainer invites such parsers
     ([#3131](https://github.com/HKUDS/LightRAG/issues/3131)).
2. **RAG-Anything** (MIT, no CLA; outside PRs merged in about 10 days).
   - It uses `text_level` to build section paths for images and tables, but text blocks lose
     their levels.
   - **Route:** a PR that keeps levels and section paths for text chunks (they merged a similar
     one for images, [#283](https://github.com/HKUDS/RAG-Anything/pull/283)), plus a
     `register_parser()` example.
3. **Docling** (DCO sign-off, conventional-commit titles, open an issue first; one outside PR
   was merged in 6 days).
   - **Route:** propose an optional LLM refinement step for its rule-based heading-hierarchy
     stage, with our numbers. Related issues:
     [#4409](https://github.com/docling-project/docling/issues/4409),
     [#4902](https://github.com/docling-project/docling/issues/4902),
     [#3568](https://github.com/docling-project/docling/issues/3568).
4. **Unstructured** (Apache-2.0, needs a CHANGELOG entry and version bump; about 3 days to
   merge).
   - `partition_pdf` gives all PDF titles the same depth, so `chunk_by_title` is flat.
   - **Route:** a PR that sets `metadata.category_depth`.
5. **Haystack**: our own custom component plus a one-file listing PR to
   [haystack-integrations](https://github.com/deepset-ai/haystack-integrations).

**MinerU: file an issue, not a PR.** Only 1 outside PR was merged in 90 days; maintainers
re-implement changes themselves. In 4.0.12 the title leveling asks for real JSON, but
`temperature=0.7` is still hardcoded, the prompt is Chinese only, and it doesn't use JSON mode.
Models that only accept temperature 1 likely fail every call, and the levels are silently left
unchanged. Ask for a configurable temperature, an English prompt option and JSON mode, with our
logs as evidence.

**Skip:**
- LlamaIndex: new integration PRs are closed automatically.
- LangChain: PRs need an approved issue you're assigned to, and text splitters are a low
  priority for them.
- Microsoft GraphRAG: maintenance mode (but its `register_chunker` works from our own package).
- RAGFlow: ingestion moved to Go.
- Marker: inactive.

## 2. How to make the PRs

1. Open an issue or discussion first with a minimal reproduction and the numbers, then the PR.
2. Keep each PR small: one behaviour, tests, the project's lint/pre-commit, and its PR template.
3. Sign-off and agreements:
   - Docling needs `git commit -s` (DCO), which records your name and email.
   - Haystack core, MinerU and GraphRAG need a CLA.
   - Using your name and email there is the owner's call.
4. Link the public benchmark (dataset plus scorer) so reviewers can re-run it.

## 3. Proof before PRs

**Checked 20 Oct:**
- READoc publishes Docling's Heading Tree TEDS: 38.3 on arXiv and 22.8 on GitHub (MinerU 42.0 /
  47.2; best are Nougat-base 88.5 on arXiv and GOT-OCR 2.0 50.1 on GitHub). That Docling run
  predates its heading-hierarchy stage (v2.129), so re-run current Docling beside ours.
- docling-eval has no heading or hierarchy benchmark (only text, layout, reading order and
  tables), so adding one is a contribution with little friction.
- Docling issue [#4409](https://github.com/docling-project/docling/issues/4409): headings the
  layout model labels `list_item`/`text` never enter the hierarchy. The reproducer is the IPCC
  AR6 SYR SPM, whose 18 headline statements A.1–C.7 are lost.
- Issues #4902 and #3568 are about export and Markdown input, not PDF headings.
- The FinanceBench RAG pilot (19 Oct) measured answers, not headings, on 10-Ks with easy
  structure, so it is not a heading comparison.

**Heading accuracy on public benchmarks**, with frozen settings:
- READoc (dataset MIT on Hugging Face; the GitHub code has no licence). It already reports MinerU and Docling numbers, so we can be
  placed beside them.
- DocHieNet (Apache-2.0, 1,673 docs in English and Chinese, many scanned). Best published:
  M3DocDep, F1 76.0.
- Optional: Comp-HRDoc (annotations MIT; images come from HRDoc).

**Does better sectioning give better RAG answers?** Published evidence is mixed:
- Structure-aware chunking usually gains 3–10 points (Unstructured on FinanceBench 53.2% vs
  48.2%; HiChunk; header-path prefixes +24% MRR).
- NVIDIA found page-level chunks beat section chunks on 4 of 5 datasets.
- No study isolates *heading accuracy*. That gap is our angle.

**Experiment**, using LightRAG as the harness. Every arm uses the same MinerU text, the same
LLM and the same token budget; only the headings change.
- Arms:
  - (A) fixed-size chunks
  - (B) P chunker with MinerU headings
  - (C) P chunker with Section Anything headings
  - (D) gold headings, Qasper only
- Modes: vector mode first, then graph mode.
- Metrics:
  - Accuracy against reference answers (binary judge, as RAG-Anything uses) and evidence-page
    recall.
  - Paired bootstrap confidence intervals.
  - Whether the per-document gain tracks the heading-F1 gain.
- Stages:
  1. **Pilot:** FinanceBench, about 30 filings and 50 questions, vector mode. Under $3.
  2. **FinanceBench, 150 questions** (about 10k pages):
     - Section Anything: about $0.40 (Quick check) or $23 (Standard).
     - LightRAG graph indexing: about $15–45 for 3 arms.
     - This size only detects large effects (±6–8 points).
  3. **More power:** add MMLongBench-Doc (135 docs, 1,082 questions, $10–30) and the Qasper
     test split (answer F1, no judge). Together these can detect gains of 3–4 points.
- MinerU on about 10k pages: use its cloud API (2,000 free pages a day). It would load the
  laptop for hours.
- If an LLM judge is used, swap answer order and allow ties: LightRAG's own win rates were
  shown to shrink from 66.7% to 39% once biases were corrected (arXiv 2506.06331).

The cost figures above are estimates; state the cost and confirm with the owner before each run
(workspace rule).

## 4. Section Anything features for RAG (cheapest first)

1. Output adapters:
   - LightRAG `.blocks.jsonl` (`heading`, `level`, `parent_headings`)
   - RAG-Anything content list with `text_level`
   - Markdown with `#` levels
   - Docling heading levels
2. A section path prefix on every chunk (a cheap version of Anthropic's Contextual Retrieval).
3. Chunks that never cross a section boundary.
4. A summary per section (a RAPTOR-style tree built on real sections).
5. Section nodes and entity-to-section edges in the graph (LightRAG `ainsert_custom_kg`), as
   BookRAG does (VLDB 2026), for retrieval scoped to a section.

## 5. Launch and posting

**Order:**
1. Public repo (Apache-2.0) plus a Hugging Face dataset with scorer and results.
2. A write-up covering how the answer keys are built, what we fixed in them, and where Docling
   and MinerU win.
3. Then the posts:
   - **Show HN:** something people can try, no signup gate. Post a first comment with the
     method and limits, and answer every reply for the first 2 hours.
   - **r/MachineLearning:** use the [P] tag and frame it as a benchmark.
   - **r/LocalLLaMA:** self-promotion is limited to about 1 in 10 posts, with a karma minimum.
   - **LinkedIn and X:** one chart and one hard example.
   - **Community channels:** Docling, MinerU and LightRAG Discords and GitHub Discussions.
4. Hugging Face Spaces: free accounts get only Static Spaces or 2 ZeroGPU Gradio Spaces.
5. Papers with Code shut down in July 2025.

**Venues:**
- VisionDocs at WACV 2027: 4-page short papers due **12 Nov 2026**; topics include datasets and
  benchmarks; in-person presentation required.
- ICDAR 2027 (Kuala Lumpur, Aug 2027): abstracts due 31 Jan 2027, papers 20 Feb 2027. A
  heading-hierarchy competition proposal may be due about now (unverified).
- arXiv: first-time authors need an endorsement since Jan 2026.

## 6. Growing the corpus

**Publishing:**
- Host only the files we may redistribute. For the rest, list the URL and SHA-256 and provide a
  fetch script.
- Give each document a licence column. Publish the answer keys as Parquet or JSONL so Hugging
  Face generates the Croissant metadata.
- Licence by source:
  - arXiv: CC BY, BY-SA or CC0 only.
  - Wikipedia: CC BY-SA.
  - GFDL manuals: include the licence text.
  - UK legislation: OGL v3.
  - HiPS law books: CC BY-NC; a separate dataset config, or kept local.
- **OpenStax** is now CC BY-NC-SA, and its book pages forbid ingestion into LLMs or
  generative-AI offerings without written permission. The manifest licence was corrected on
  19 Oct 2026, and the MinerU cloud guard now refuses it. Replace the textbook category with
  CC BY textbooks, or ask OpenStax for permission.

**New sources with reliable answer keys:**
- Canada Justice Laws XML (English and French).
- EUR-Lex Formex XML plus PDF in 24 languages (one structure gives keys for every language).
- US CFR / Federal Register XML.
- PMC open-access articles via `s3://pmc-oa-opendata` (filter by licence; the FTP was retired in
  Aug 2026).
- arXiv LaTeX under CC BY.
- IETF RFCs.
- GovReport.
- EDGAR 10-K filings (Part/Item levels).
- Scanned documents by printing and scanning existing born-digital documents.

**External sets to score on:** READoc, DocHieNet, Comp-HRDoc, FinTOC (registration needed),
ICDAR Book Structure (scanned books).
