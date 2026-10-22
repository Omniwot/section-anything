# Review: Docling bookmark-reconciliation contribution (21 Oct 2026, read-only)

Nothing was posted or changed. Sources: CONTRIBUTING (Docling and community), PR template,
AGENTS.md, AI-review prompt, PRs #3633 #3688 #3984 #4179 #4204 #4473 #3874 #4169, related issues,
docling-eval.

**Status (21 Oct, evening):** "Before posting the issue" steps 1–4 are done: title variant
re-scored (`results.md`, "Title variant"), drafts reworded with links and honesty notes, issue
shortened, public reproduction in `repro/`. Left for the owner: step 5 (review and post), and
replace REPRO_LINK once the repo is public.

**Status (22 Oct):** E1/E2 done on fresh documents (8 new arXiv papers, 9 Canadian acts with a
pre-registered run, Docling's 3 test PDFs with outlines); two fixes committed (`183f1dd`, patch
0002). See `results.md`, "Fresh documents". READoc re-run with `183f1dd` done (arXiv +5.4 / +8.4 with
`title`, GitHub unchanged). Open: E4 (reports, books).

## What maintainers ask for

- **Issue first** for features. #3676 came before #3688. #4472 and #4473 were opened on the same
  day, and #4473 merged.
- **A real PDF in tests.** Asked for in #3688. A maintainer added one in #3633.
- **Failure modes of label changes:** forms (#3688), false-positive tables (#4204), trade-offs
  written in docstrings (#4179).
- **Before/after on Docling's own test PDFs** (#3984). Off by default. Private names.
- No reviewer asked for docling-eval. Merges take about 8–11 days.
- **Overlap:** no one else has proposed demotion. Related: #3957 (`layout_postprocessor.py:151`
  remaps `TITLE`→`SECTION_HEADER`), #4114 (false "Example" headers), #4701 (the title in chunk
  headings), #4169, #4148. #4409 has had no maintainer reply for 3 weeks.

## Items

| # | Item | Label | Reason | Effort |
|---|---|---|---|---|
| T1 | Title: `text` vs `title` | **REQUIRED** (before the issue) | In 55 of 56 arXiv title demotions, the READoc key has that title as `#`. Chunkers use a `TitleItem` as level 0 of every heading path, and `text` drops it | Re-score the saved `on.md`. No Docling run, 30 min |
| T2 | Single-heading missing level | RECOMMENDED | A depth check adds little to check 2, and the 3 losses have no numbers. Try: keep an unmatched heading that is larger than body text but smaller than the smallest matched heading | About 200 conversions (pre-stage docs were not saved), about 20 min of Docling, heavy laptop load |
| T3 | Printed-TOC duplicates | RECOMMENDED | docling-parse outlines have no page (#4162), and on a tie the earlier item wins. A TOC line can take the bookmark, and then the real heading is demoted | Test plus 1 book, 2 h |
| T4 | Non-English | RECOMMENDED | `_STANDARD_HEADING` is English only | 30 min |
| T5 | Scanned PDF with an outline | OPTIONAL | With no text cells, nothing is demoted. Lock this in with a test | 20 min |
| T6 | Order with #4409/#4148 | RECOMMENDED | Can promoted or tagged headings be demoted? | One sentence |
| E1 | Real-PDF test | **REQUIRED** (PR) | Precedent. Only `elsevier-00.pdf` and `bookmark_sample.pdf` have multi-level outlines. Reusing them avoids the 2-approval rule for test data | 2 h, 2 small conversions |
| E2 | Before/after heading table on `elsevier-00` | RECOMMENDED | Same format as #3984 | With E1 |
| E3 | Held-out sample | RECOMMENDED | The face check was added after we saw these docs | With T2 |
| E4 | 5–10 reports, books and legal PDFs | RECOMMENDED (PR) | The stage was built for contracts. READoc has neither books nor printed TOCs | Half a day |
| E5 | Runtime scaling | RECOMMENDED | Reviewers check how work grows with input. #4162: bookmark matching took 1,140 s on 600 pages | Synthetic doc, seconds |
| E6 | Option off | DONE | I diffed them: OFF Markdown is byte-identical to stock on 200/200. Say so | — |
| E7 | docling-eval / DocLayNet / [HRDoc](https://arxiv.org/abs/2303.13839) / [DocHieNet](https://aclanthology.org/2024.emnlp-main.65/) | OPTIONAL | docling-eval and DocLayNet are single pages with no outlines (no-op). HRDoc is the same genre as READoc. DocHieNet PDF access is unverified | — |
| P1 | Issue first, wait about 7 days | **REQUIRED** / wait RECOMMENDED | CONTRIBUTING. Do not wait indefinitely | — |
| P2 | Credit #4409 and link #3957/#4114/#4701 | RECOMMENDED | The face check is close to the #4409 idea. No code was copied | 10 min |
| P3 | DCO sign-off with a real author | **REQUIRED** (PR) | The owner decides. A GitHub noreply email keeps the address private | 5 min |
| P4 | Rebase | **REQUIRED** (PR) | `main` is 9 commits ahead, including `pipeline_options.py` | 15 min |
| P5 | `make validate`, tach | **REQUIRED** (PR) | AGENTS.md. Install uv in an isolated env | 30 min |
| P6 | Docs: known limits | **REQUIRED** (PR) | #4179 precedent. The docs do not list the misses | 15 min |
| P7 | docling-jobkit | RECOMMENDED | Through the service, parsed pages are kept only when `use_style` is on (jobkit #212) | Mention; one-line PR later |
| P8 | Title format, changelog, reportlab skips | DONE / not needed / not an issue | The title matches mergify. The changelog is generated. reportlab is not in `uv.lock`, so CI skips the 2 tests too | — |
| R1 | Reword the title claim | **REQUIRED** | The paper title is a real title with the wrong label (#3957), not a "non-heading" | 10 min |
| R2 | Show both variants | **REQUIRED** | Maintainers can answer Q2 from data | With T1 |
| R3 | State post-hoc tuning and READoc-only evidence | RECOMMENDED | Honesty | 2 lines |
| R4 | Shorter issue | RECOMMENDED | Summary and one table. Details in `<details>` | 30 min |
| R5 | Publish IDs and scripts | RECOMMENDED | Remove `/Users/…` paths. A link is better than "on request" | 1 h |

## Before posting the issue

1. T1/R2: re-score the `title` variant and add it to the tables.
2. R1, P2: reword the title claim, add the links, and note that #4169 also reduces T3.
3. R3, E6: add the honesty notes and "byte-identical".
4. R4/R5: shorten the issue and publish the cleaned scripts or the doc IDs.
5. The owner reviews and posts it.

## Before opening the PR

1. Get a maintainer reply, or wait about 7 days.
2. Implement the chosen label.
3. P4: rebase and check the state of #4169.
4. E1/E2: real-PDF test and the before/after table.
5. T2/E3: one run, with the owner's OK. Save the pre-stage docs.
6. T3–T6 tests and sentences, P6 docs.
7. E5. E4 if time allows.
8. P5: run the checks and record the results.
9. P3: DCO sign-off.
10. Update the PR text (checks run and not run, P7).
