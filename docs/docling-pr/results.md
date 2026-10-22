# Bookmark reconciliation in Docling: real-run results

Run on 21 Oct 2026, on the local branch `feat/bookmark-reconciliation` (commit `97c09a7`, on top of
Docling `main@d01c9c0`, 2.140.0). Nothing was pushed or posted.

## Summary

- **The change works on real conversions.** With the new option on, READoc heading-tree TEDS
  goes up by **+5.2** on 100 arXiv PDFs and **+3.7** on 100 GitHub PDFs, compared with the same
  conversions with the option off. Both results are significant (Wilcoxon p < 1e-4). With the
  option off, the Markdown is byte-identical to stock Docling 2.140 on all 200 documents.
- **Keeping the paper title as a `title` item is better on arXiv (+8.1 instead of +5.2).** In 55
  of the 56 arXiv papers where the title is demoted, READoc's answer key has it as the document
  title. See "Title variant" below (re-scored 21 Oct, no new conversions).
- **The real arXiv gain is larger than the simulation (+5.2 vs +1.6).** Most arXiv demotions are
  the paper title, which the layout model labels `section_header`. When the title goes, the style
  pass re-ranks the headings that remain, so Abstract and References move up one level and match
  the answer key (35 documents). The simulation kept the old levels. On GitHub the real gain is
  smaller than the simulation (+3.7 vs +5.5).
- **Partial bookmarks (risk check).** With a flat outline (top level only), the option changes
  nothing (0 of 200 documents). With the deepest outline level removed, the mean change is small
  (arXiv +0.3, GitHub −0.4), but 3 of 100 GitHub documents lose 10–17 points. In each of them, the
  removed level held only one heading, and a single unmatched heading cannot be told from junk.
- **One change from the spec, based on this run.** The shared-style check now also counts a
  heading as heading-like when its font face differs from the body face, and it groups headings
  by face. Without this, bold TeX fonts (`CMBX10`) do not read as bold, and one arXiv document lost
  21 points in the risk check. The cost is 0.3 points of the arXiv gain (see "ON-spec" below).

## Setup

| Item | Value |
|---|---|
| Code | Docling 2.140.0 + this change, editable install in conda env `docling-dev` (Python 3.11). Same dependency versions as `docling-eval` (docling-core 2.102.0, docling-parse 7.22.3, docling-ibm-models 4.0.3, torch 2.14.1). |
| Pipeline | default `PdfPipelineOptions`, `generate_parsed_pages=True`, `HeadingHierarchyOptions(enabled=True)`; ON adds `demote_unmatched_headings=True`. Same settings as `compare-2026-10-18/run_docling.py`. |
| Documents | READoc arXiv and GitHub PDFs with ≥ 3 outline entries (our saved extraction), answer key with headings, not in `readoc-pilot/selection.json`. 100 per subset, `random.Random(20261021)` from pools of 721 (arXiv) and 1,112 (GitHub). List: `.tmp/bookmark-recon/selection.json`. |
| Metric | READoc heading-tree TEDS (×100) of Docling's Markdown export against the answer key (`readoc-pilot/score.py`: `heads`, `calc_head_teds`), in env `readoc-eval`. |
| Paired stats | mean of per-document differences; 95% bootstrap CI (4,000 resamples, seed 0); better / same / worse at ±0.5 points; Wilcoxon signed-rank p. |
| OFF and ON | One conversion per PDF. The pipeline runs the stage with the option ON. A wrapper takes the document, parsed pages and outline just before the stage and also runs the stage on deep copies: OFF, and ON with the shared-style check as first specified ("ON-spec"). Check: the pipeline's ON output equals the side run in 200/200 documents. |
| Risk check | Done at the stage level: the stage runs again on the same pre-stage document with a reduced outline (deepest level removed; or top level only). The outline is read only by this stage (`standard_pdf_pipeline.py:907`, consumed in `HeadingHierarchyModel.__call__`), so this equals a PDF with a reduced outline. |

The outline depth that Docling reads (docling-parse backend) is not the same as in our saved
extraction:

| Subset | 1 level | 2 levels | 3 levels |
|---|---|---|---|
| arXiv | 31 | 52 | 17 |
| GitHub | 0 | 38 | 62 |

The option cannot act on the 31 arXiv documents with a flat outline (check 1).

## Main result: option off vs on (full bookmarks)

"ON" is the committed code. "ON-spec" is the shared-style check exactly as first specified
(larger than body or bold; no font-face check).

| Subset | Comparison | n | OFF | ON | mean diff | 95% CI | better / same / worse | Wilcoxon p |
|---|---|---|---|---|---|---|---|---|
| arXiv | OFF → ON | 100 | 50.4 | 55.6 | **+5.22** | +3.77 to +6.78 | 41 / 57 / 2 | 3.2e-08 |
| arXiv | OFF → ON-spec | 100 | 50.4 | 55.9 | +5.54 | +3.99 to +7.18 | 43 / 54 / 3 | 2.0e-08 |
| GitHub | OFF → ON | 100 | 75.7 | 79.4 | **+3.69** | +2.07 to +5.37 | 27 / 67 / 6 | 2.3e-05 |
| GitHub | OFF → ON-spec | 100 | 75.7 | 79.4 | +3.69 | +2.07 to +5.37 | 27 / 67 / 6 | 2.3e-05 |

- OFF equals stock Docling 2.140 (the 18 Oct run in `.tmp/readoc-full-out`) in 100/100 arXiv and
  100/100 GitHub documents (same heading list).
- An earlier run of the ON-spec code on the same 100 arXiv PDFs (`.tmp/bookmark-recon/out-v1`)
  gave the same numbers (+5.54, 43 / 54 / 3).
- Time: conversion 3.9 s per arXiv PDF and 1.4 s per GitHub PDF. The stage itself adds about
  0.01–0.02 s per run.

### What gets demoted (ON)

| Subset | Docs with a demotion | Headings demoted | Paper title (first heading) | Docs where the title was the only demotion |
|---|---|---|---|---|
| arXiv | 56 | 67 | 56 | 46 |
| GitHub | 34 | 75 | 1 | 1 |

Examples:

- arXiv: paper titles; author lines ("Alena Harley", "Matthew J. Evans", "The IceCube
  Collaboration"); algorithm captions ("Algorithm 1: Estimation Procedure"); "Properties:",
  "Netherlands", "Problem 5.1 ([19]). Is it true …".
- GitHub: "Say we set a role like so:", "Example:", "IMPORTANT NOTICE:", "struct as the first
  argument.", "or the arXiv paper", "Table of Contents".

Why the real arXiv gain is larger than the simulation: after the title is demoted, the style pass
ranks fewer headings, so unmatched standard headings move up one level (for example
`### References` → `## References`). This happened in 35 arXiv documents and in no GitHub document.
It matches the answer key, where References is a top-level section.

### Documents that got worse (ON, full bookmarks)

| Subset | Document | Change | Demoted |
|---|---|---|---|
| arXiv | 2008.07557 | −0.6 | paper title |
| arXiv | 2306.16303 | −0.8 | paper title |
| GitHub | 82388118 | −11.1 | "Including It In Your Project" (a real section; one heading, not in the outline) |
| GitHub | 483665243 | −6.3 | "4. Train the detector", … (shell comments in code blocks; the answer key also lists such lines as headings) |
| GitHub | 282072618 | −2.8 | "Paper link: …" |
| GitHub | 113086028 | −2.6 | "Table of Contents", "GO reference", … |
| GitHub | 263452252, 6252013 | −1.1 each | "CocoaPods", "Carthage", "Tests", … |

ON vs ON-spec differs on 5 arXiv documents (no GitHub document):

| Document | ON | ON-spec | Why |
|---|---|---|---|
| 2207.02679 | 0.0 | −5.6 | unbookmarked subsections in an italic face at body size; the face check keeps them |
| 2107.12186 | +21.0 | 0.0 | two author lines in different faces; ON-spec saw one bold family and demoted nothing |
| 1709.05793 | 0.0 | +15.5 | seven "Algorithm N" captions share a bold face; ON keeps them (and the title) |
| 1807.06622 | 0.0 | +18.6 | "· Forward solver:" / "· Backward solver:" share a face; ON keeps them |
| 1905.13399 | 0.0 | +24.3 | "Phase 1/2/3:" and an algorithm caption share a face; ON keeps them |

In the risk check, the face check also removes the one large arXiv loss (2209.05611, below).

## Risk check: partial bookmarks

Paired OFF vs ON with the same reduced outline. arXiv has 69 documents with 2 or more outline
levels; only these have a deepest level to remove.

| Subset | Outline | n | OFF | ON | mean diff | 95% CI | better / same / worse | worst document |
|---|---|---|---|---|---|---|---|---|
| arXiv | deepest level removed | 69 | 51.6 | 51.9 | +0.29 | +0.01 to +0.64 | 4 / 65 / 0 | none worse |
| arXiv (ON-spec) | deepest level removed | 69 | 51.6 | 51.6 | +0.01 | −0.81 to +0.57 | 5 / 63 / 1 | 2209.05611: −21.1 |
| arXiv | top level only | 100 | 49.6 | 49.6 | 0.00 | 0.00 to 0.00 | 0 / 100 / 0 | none |
| GitHub | deepest level removed | 100 | 75.7 | 75.3 | −0.43 | −1.00 to 0.00 | 0 / 97 / 3 | 141265446 and 488807679: −16.7; 21162135: −10.0 |
| GitHub | top level only | 100 | 75.2 | 75.2 | 0.00 | 0.00 to 0.00 | 0 / 100 / 0 | none |

Comparable with the simulation's risk scenario (baseline = OFF with the full outline):

| Subset | OFF full → OFF deepest removed | OFF full → ON deepest removed | Simulation: full → deepest removed |
|---|---|---|---|
| arXiv (69) | −0.98 | −0.69 | −0.25 |
| GitHub (100) | −0.01 | −0.45 | −1.20 |

Reading:

- No material harm on average. On arXiv the option slightly improves results under a partial
  outline.
- The 3 GitHub losses have the same cause. The removed level held one heading ("Kubernetes",
  "Example benchmark output", "Supported Features"), so check 4, which needs two or more headings in
  one style, cannot see the missing level. A single real heading that the outline omits is
  demoted. The same thing happened in GitHub 82388118 with full bookmarks.
- 2209.05611 (REVTeX) is the case that the font-face check fixes. Its subsections are set in
  `CMBX10`, which the font-name parser does not read as bold.

## Fresh documents (22 Oct, review items E1/E2 and the tuning concern)

The option was designed while looking at READoc, so it was also run on documents never used in its
design. Code: `97c09a7` first, then `183f1dd` with two fixes (below). The Canadian run was
pre-registered: keys, metrics and code were frozen before any output existed
(`.tmp/bookmark-recon/fresh/PREREGISTRATION.md`).

| Set | Answer key | n | OFF → ON (`text`) | OFF → TITLE | Worse docs | Risk check (deepest level removed) |
|---|---|---|---|---|---|---|
| arXiv papers from our corpus (not in READoc) | LaTeX sectioning commands + official arXiv title | 8 | TEDS +4.4 (95% CI +0.3 to +10.7), 4 better | +5.5 (+0.7 to +13.2), 4 better | 0 | 0.0 (nothing demoted) |
| Canadian federal acts (English and French side by side) | official XML, both languages | 9 | F1 0.0: nothing demoted | 0.0 | 0 | 0.0 |
| Docling's test PDFs with multi-level outlines | none (listed below) | 3 | 5 headers demoted | | | |

- **Papers:** the gain matches READoc's direction (+5.2 / +8.1 there). Demoted: 4 paper titles, an
  author name, a figure axis label, a "Contents" line, "AUTHOR CONTRIBUTIONS" (not in the key). One
  wrong demotion: arxiv-08 "REPRODUCIBILITY", a real section the outline omits (the known
  single-omitted-heading limit).
- **Canadian acts:** the layout model labels the marginal notes as section headers (312–1,021
  headers per act against 62–116 key headings; with marginal notes counted as headings, OFF F1 is
  92.0). Each bookmark can claim one header, so at most about a quarter of the headers match, check
  3 (half matched) fails, and the option does nothing. No harm, no gain; the safety check works as
  intended on a different genre and layout.
- **Docling test PDFs:** `elsevier-00` demotes the journal name and the letter-spaced "A R T I C L E
  I N F O" label; `llncsdoc` demotes its title and a stray `\spnewtheorem` line; `bookmark_sample`
  is unchanged.

**Two fixes found on these documents (`183f1dd`).** Both are general rules with no thresholds,
each with a unit test that fails without it:

1. Letter-spaced standard headings: `elsevier-00`'s "A B S T R A C T" was demoted because the
   standard-heading check did not read letter spacing. Now kept.
2. Bookmark titles that differ from the printed heading: arxiv-07's section "4. Proofs of Lemma 1.1
   and Lemma 1.2" has the bookmark "4. Proofs of thm:mainEXP and thm:mainPOLY" (unresolved LaTeX
   references), so it matched nothing and was demoted. A heading whose section number belongs to a
   bookmark that matched no heading now counts as matched, so it is kept. Because it counts as
   matched, this rule can also let the completeness checks pass in other documents.

Scores with the fixes: papers unchanged in total (+4.4 / +5.5; arxiv-07 −0.2 because our own key
also misses section 4, for the same bookmark reason). Canada unchanged (0.0). The READoc tables in
this file are from `97c09a7`; the recheck with `183f1dd` is in the next section. Since the fixes were found on the papers and on
`elsevier-00`, those are no longer held out for the fixes; the Canadian acts were the blind test,
and there the option did not engage.

## Recheck of READoc with the fixes (`183f1dd`, 22 Oct)

All 200 READoc documents converted again (output `.tmp/bookmark-recon/out-183f1dd/`), same
settings and scripts.

| Subset | Comparison | n | before | after | mean diff | 95% CI | better / same / worse | Wilcoxon p |
|---|---|---|---|---|---|---|---|---|
| arXiv | OFF → ON (`text`) | 100 | 50.4 | 55.8 | **+5.45** | +3.98 to +7.04 | 42 / 56 / 2 | 2.0e-08 |
| arXiv | OFF → TITLE | 100 | 50.4 | 58.8 | **+8.38** | +6.39 to +10.52 | 57 / 43 / 0 | 5.1e-11 |
| arXiv | deepest removed: OFF → ON | 69 | 51.6 | 51.9 | +0.29 | +0.01 to +0.64 | 4 / 65 / 0 | 0.12 |
| GitHub | OFF → ON (`text`) | 100 | 75.7 | 79.4 | +3.69 | +2.07 to +5.37 | 27 / 67 / 6 | 2.3e-05 |
| GitHub | OFF → TITLE | 100 | 75.7 | 79.2 | +3.44 | +1.89 to +5.06 | 26 / 68 / 6 | 3.7e-05 |
| GitHub | deepest removed: OFF → ON | 100 | 75.7 | 75.3 | −0.43 | −1.00 to 0.00 | 0 / 97 / 3 | 0.1 |

- OFF Markdown is byte-identical to the earlier run on all 200 documents.
- Exactly one document changed: arXiv 1812.06594 (ON 56.7 → 79.8, TITLE 56.7 → 87.4). Its bookmark
  for section 2.2 holds garbled LaTeX math ("2.2 Tsallis Entropy bold0mu mumu Sq=2Sq=22005"), so it
  matched nothing and the unmatched dotted heading failed check 2. With the number rule it counts as
  matched, the checks pass, and only the paper title is demoted (the key has it as the title).
- Demotions: arXiv 68 headers in 57 papers (57 paper titles; the key has 56 of them as the title),
  GitHub 76 headers in 34 READMEs (multiset count; the earlier "75" was a set count).
- Size-checked TITLE estimate (page 1, no smaller than any other header): arXiv +7.9, GitHub +3.7,
  no arXiv document worse than OFF.

## Title variant (review item T1)

Re-scored on 21 Oct from the saved Markdown; no new Docling run. In the TITLE variant, a demoted
header that is the document's first section header becomes a `title` item; other demoted headers
still become `text`. Docling's Markdown export writes a `TitleItem` as `# text` and does not rank
it with the section headers (docling-core `transforms/serializer/markdown.py`), so the variant is
the ON Markdown with that paragraph turned back into a `# ` line. Script:
`.tmp/bookmark-recon/score_title_variant.py`; public version `repro/score.py`.

| Subset | Comparison | n | before | after | mean diff | 95% CI | better / same / worse | Wilcoxon p |
|---|---|---|---|---|---|---|---|---|
| arXiv | OFF → ON (`text`) | 100 | 50.4 | 55.6 | +5.22 | +3.77 to +6.78 | 41 / 57 / 2 | 3.2e-08 |
| arXiv | OFF → TITLE | 100 | 50.4 | 58.4 | **+8.08** | +6.06 to +10.17 | 56 / 44 / 0 | 7.5e-11 |
| arXiv | ON → TITLE | 100 | 55.6 | 58.4 | +2.86 | +2.16 to +3.55 | 55 / 44 / 1 | 7.6e-10 |
| arXiv | deepest removed: OFF → TITLE | 69 | 51.6 | 52.3 | +0.68 | +0.17 to +1.35 | 6 / 63 / 0 | 0.028 |
| GitHub | OFF → ON (`text`) | 100 | 75.7 | 79.4 | +3.69 | +2.07 to +5.37 | 27 / 67 / 6 | 2.3e-05 |
| GitHub | OFF → TITLE | 100 | 75.7 | 79.2 | +3.44 | +1.89 to +5.06 | 26 / 68 / 6 | 3.7e-05 |
| GitHub | deepest removed: OFF → TITLE | 100 | 75.7 | 75.3 | −0.43 | −1.00 to 0.00 | 0 / 97 / 3 | 0.1 |

- arXiv: the first header is demoted in 56 papers. The answer key has that text as the `#` title in
  55; 5 of these differ only in formatting (subscripts, capitals, bold). The exception, 1503.06448,
  has no title in its key and loses 7.7 points with TITLE. No arXiv paper is worse than OFF with
  TITLE; the 2 that were worse with ON (2008.07557, 2306.16303) gain 7–8 points.
- GitHub: only one README has its first header demoted, "IMPORTANT NOTICE:" (122838124). TITLE
  makes it worse by 25 points.
- **Size check** (`.tmp/bookmark-recon/title_size_check.py`): relabel only when the first header is
  on page 1 and its font is no smaller than every other header. With font sizes from our pdfium
  extraction matched by text, this keeps "IMPORTANT NOTICE:" (10.9 pt vs 14.3 pt) as `text` and
  relabels 48 of the 56 arXiv titles: **arXiv +7.6, GitHub +3.7**, no document worse than OFF on
  arXiv. For 7 of the 8 arXiv titles it misses, our text matching found no size, so Docling, which
  has the sizes in its parsed pages, would likely relabel more. A stricter rule (at least 1 pt
  larger, as Section Anything's `doc_title` flag) relabels only 38 and gives +7.4.
- Why it matters downstream: Docling collapses `TITLE` into `SECTION_HEADER` on purpose (#3957),
  and chunkers use a `TitleItem` as the top of every heading path, while a `text` title vanishes
  from heading paths (compare #4701).

## Real run vs simulation (same documents)

The simulation (`readoc-pilot/eval_bookmark_change_v4.py` logic) used our own PDF extraction for
the outline and styles, its own title matching, and a baseline rebuilt from the saved Docling JSON.

| Subset | n | Simulation v4 (as validated) | Simulation v4, standard headings outside the style check | Real ON | Real ON-spec |
|---|---|---|---|---|---|
| arXiv | 100 | +1.56 (+0.90 to +2.25), 25 / 62 / 13 | +2.13 (+1.20 to +3.00), 35 / 51 / 14 | **+5.22** (+3.77 to +6.78), 41 / 57 / 2 | +5.54 (+3.99 to +7.18), 43 / 54 / 3 |
| GitHub | 100 | +5.48 (+3.33 to +7.90), 35 / 60 / 5 | +5.48 (same) | **+3.69** (+2.07 to +5.37), 27 / 67 / 6 | +3.69 (same) |

Baselines: simulation 50.3 (arXiv) and 73.8 (GitHub); real OFF 50.4 and 75.7.

Two implementation choices differ from the v4 simulation:

1. Standard headings (Abstract, References, …) are not counted in the shared-style check, because
   they are never demoted. In the simulation on all bookmarked READoc documents, this raised the
   arXiv gain from +1.54 to +2.44 (796 documents) with the same partial-outline risk (−0.13 vs
   −0.12 on 603 documents), and changed nothing on GitHub (1,210 documents). Script:
   `.tmp/bookmark-recon/sim_v4_variants.py`.
2. The font-face check described above (found in this run).

## Unit tests

`pytest tests/test_heading_hierarchy.py tests/test_heading_hierarchy_bookmarks.py
tests/test_heading_hierarchy_pdf.py`: **70 passed, 2 skipped** (the 2 skips need reportlab, which
is not installed; they also skip on `main`). New tests (7 functions, 10 cases): complete bookmarks → extra
header demoted; top-level-only bookmarks → nothing dropped; deepest level missing (numbered, bold,
`CMBX10` face) → nothing dropped; under 50% matched → nothing dropped; standard headings kept;
option off and no parsed pages → unchanged; `__call__` keeps parsed pages for the option.

Mutation check (`.tmp/bookmark-recon/mutation_check.py`): disabling each completeness check in the
code makes its own test fail. ruff format and ruff check (0.15.12) and ty (0.0.33) pass on the
changed files.

## Limitations and open questions

- **Title.** On arXiv, the main effect is on the paper title, which the layout model labels
  `section_header` (Docling collapses `TITLE` on purpose, #3957). The paper title is a real title
  with the wrong label, not a non-heading. Relabelling it `title` scores better than `text` (see
  "Title variant"); which one to implement is a question for the maintainers.
- **Post-hoc tuning.** The thresholds and the font-face check were chosen while looking at READoc
  documents (all bookmarked READoc documents went through the design simulations); the face check
  was added after seeing these 100 arXiv papers. Fresh documents (above): 8 new papers agree
  (+4.4 / +5.5); on 9 Canadian acts the option does not engage. Reports and books are still to do
  (review item E4).
- **Legislation with marginal notes.** When the layout model labels marginal notes as headers, far
  fewer than half of the headers can match a bookmark, so the option does nothing there.
- **Single omitted heading.** When the outline omits a level that holds only one heading, that
  heading is demoted (3/100 GitHub documents in the risk check; 1/100 with full bookmarks).
- **Same-face headings.** A missing level set in the body face and size is not detected, unless the
  headings have dotted numbers.
- **Corpus.** READoc only (arXiv papers and GitHub READMEs rendered to PDF). Not tested on
  reports, legal documents or books.

## Laptop and run notes

- Each Docling job held `.tmp/locks/docling.lock`, ran in fresh processes of at most 50 files,
  and used the watchdog (pressure limit 4, 4 GB own RSS, 2 GB swap growth). The batch runner
  checked swap (≤ 14,848 MB) and memory pressure before each batch.
- Swap was near its limit all session (13.7–17.0 GB used). The batch runner stopped before a
  batch 6 times because of swap, and the watchdog stopped one batch at 17:31 (swap +2.2 GB while
  another app started). Each resumed run skipped finished files.
- Total Docling time: about 16 minutes of conversion for about 300 PDF conversions (101 in the
  first run with the ON-spec code, 200 in the final run), plus about 1 minute of model loading per
  batch. Wall time was about 2 hours because of the swap pauses.
- Incident: at 16:52 my first lock command failed because another job held the lock, and the
  script then removed that job's lock. I re-created it within seconds and the other job finished
  normally. All later Docling jobs used `.tmp/bookmark-recon/with_lock.sh`.

## Files

- Branch: `.tmp/repos/docling`, `feat/bookmark-reconciliation`, commit `97c09a7` (author
  placeholder `TBD <tbd@example.invalid>`, no sign-off).
- Patch: `docs/docling-pr/0001-feat-heading-hierarchy-demote-section-headers-that-a.patch`.
- Public reproduction (no local paths): `docs/docling-pr/repro/` (document IDs, per-document
  scores, `run_docling.py`, `score.py`, README).
- Scripts and outputs: `.tmp/bookmark-recon/` (`run_recon.py`, `batches.sh`, `run_all.sh`,
  `score_recon.py`, `score_title_variant.py`, `title_size_check.py`, `select_docs.py`,
  `sim_v4_variants.py`, `mutation_check.py`), per-document
  Markdown in `out/{arxiv,github}/`, scores in `out/scores.json`, the ON-spec run in `out-v1/`.
