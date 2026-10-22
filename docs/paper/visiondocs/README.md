# VisionDocs @ WACV 2027: short-paper draft

**Draft only, 22 Oct 2026.** Nothing has been submitted, registered, uploaded, posted or emailed, and
no account was created. The owner doubts the venue fits; see "Fit" below and `../venue_fit.md`.

| File | What it is |
|---|---|
| `main.tex` | 4-page short paper, double-blind review copy, official WACV 2027 template |
| `refs.bib` | 16 entries copied from `../refs.bib`; internal notes moved to comments so they don't print |
| `wacv.sty`, `ieeenat_fullname.bst` | Unchanged from the official WACV 2027 Author Kit (see "Build") |

## CFP facts (checked on the web, 22 Oct 2026)

| Item | Finding | Source |
|---|---|---|
| Workshop | 4th Workshop on Computer Vision Systems for Document Analysis and Recognition (VisionDocs @ WACV 2027) | [VisionDocs site][vd] |
| When / where | Workshop on "January 04 or 05, 2027". WACV runs Mon 4 to Fri 8 Jan 2027 (workshops 4–5 Jan) at Disney Springs, Buena Vista, FL | [VisionDocs site][vd], [WACV 2027][wacv] |
| **Short-paper deadline** | **12 Nov 2026, 11:59 PM Pacific** (confirmed). Notification 19 Nov, camera-ready 26 Nov 2026 | [VisionDocs site][vd] |
| Regular papers | 8 pages + references; deadline was 18 Oct 2026 (closed); OpenReview | [VisionDocs site][vd] |
| Page limit | Short papers: "max 4 pages + reference" | [VisionDocs site][vd] |
| References | Not counted: "+ reference". The WACV author guide also allows extra pages that contain only references | [VisionDocs site][vd], [WACV author guide][ag] |
| Template | "adopt the standard main conference WACV 2027 template" (WACV formatting guidelines). The official kit is public: [wacv-2027-author-kit-template.zip][kit] | [VisionDocs site][vd], [WACV author guide][ag] |
| Anonymity | "All submissions should be compiled for double-blind review". WACV: no self-identifying links or acknowledgements, and don't cite your own public codebase (say the code will be released) | [VisionDocs site][vd], [WACV author guide][ag] |
| Archival | **Short papers are non-archival**: "published on this website only and will not be included in the conference proceedings". Regular papers go to the WACV 2027 Workshop Proceedings (archival; metadata goes to IEEE) | [VisionDocs site][vd], [WACV call for workshops][cfw] |
| Submission route | Short papers: a Google Form ([forms.gle/PHz3WQ6nKsZayHEC6][form]). It returned HTTP 401 to an anonymous fetch, so it likely needs a Google sign-in | [VisionDocs site][vd] |
| Presentation | "Accepted papers must be presented in person during the workshop, either as oral presentations or posters" | [VisionDocs site][vd] |
| Topics | Listed "but not limited to": layout analysis (physical and logical), document analysis systems, extracting document semantics, structured document generation, agentic systems, multimodal analysis, datasets and benchmarks, and more. The intro also names "retrieval-augmented systems" and "language models". Nothing says text-only methods are out of scope, but the title and most topics are vision-focused | [VisionDocs site][vd] |
| Prior and parallel work | The VisionDocs page asks for "original and unpublished work" and says nothing else. WACV's rules: arXiv is fine, and peer-reviewed workshop papers of **4 pages or fewer** (excluding references) do not count as publications. A 20% or more overlap submitted elsewhere during review counts as dual submission | [VisionDocs site][vd], [WACV author guide][ag] |
| Contact | visiondocs.organizers@gmail.com (public address on the site; not contacted) | [VisionDocs site][vd] |

[vd]: https://sites.google.com/view/avml-lab-visiondocs-wacv2027/home
[wacv]: https://wacv.thecvf.com/Conferences/2027
[ag]: https://wacv.thecvf.com/Conferences/2027/AuthorGuides
[kit]: https://wacv.thecvf.com/static/wacv-2027-author-kit-template.zip
[cfw]: https://wacv.thecvf.com/Conferences/2027/CallForWorkshops
[form]: https://forms.gle/PHz3WQ6nKsZayHEC6

**Could not verify:**

- **The form's fields.** I could not see what the Google Form asks for (sign-in required), such as
  author names, an abstract, or whether a PDF upload is the only input.
- **Supplementary material.** The VisionDocs page does not mention it. The draft has no appendix.
- **Track and paper ID.** In review mode the kit requires a track option and prints a paper ID. A
  workshop has no tracks, and the form may not assign an ID. The draft uses
  `[review,applications]` and `*****`.
- **Registration.** The cost, and whether workshop-only registration is enough to present, were not
  checked.
- **ICDAR 2027.** I did not re-check whether ICDAR 2027 accepts work that appeared earlier as a
  non-archival workshop paper. WACV's rule only covers WACV.

## Fit

The fit is weak to moderate. Points for it:

- The topic list is open-ended ("not limited to").
- It includes logical layout analysis, extracting document semantics, and datasets and benchmarks.
- The intro mentions retrieval-augmented systems.
- Section 4 of the paper is a change to a vision pipeline (Docling's layout model proposes the
  headers, and the PDF outline vetoes some of them).

Points against it:

- The method uses no page images.
- The short track is non-archival.
- Presenting in Florida on 4 or 5 Jan is required.

`../venue_fit.md` (21 Oct) recommends ICDAR 2027 (full paper due 20 Feb 2027) as the primary venue.
Under WACV's rule, a 4-page non-archival paper here would not block that, but check ICDAR's own
policy first.

## Submission checklist

- [ ] Choose the venue (owner). If VisionDocs: submit by **12 Nov 2026, 11:59 PM PT**.
- [ ] Compile: `pdflatex main && bibtex main && pdflatex main && pdflatex main`. Check that the body
      is at most 4 pages, that references start after it, and that nothing overflows.
- [ ] Keep it anonymous:
  - No names, affiliations, emails, acknowledgements or grant IDs.
  - No repository, website, PyPI or demo links.
  - Don't cite or link the (unposted) Docling issue or PR drafts.
  - Keep "Code ... will be made available after review."
- [ ] Decide whether the name "Section Anything" can identify the authors during review. It can if a
      public repo, site or package under that name links to the owner. WACV allows public
      preprints, but the macro `\sysname` lets you rename it in one place.
- [ ] Pick the track option and the paper ID line (see "Could not verify").
- [ ] Check the one reference marked UNVERIFIED in `refs.bib` (the LightRAG parser docs wording).
- [ ] Strip all `%` comments before uploading LaTeX source anywhere. They name internal files.
      The PDF does not show them.
- [ ] Submit through the Google Form (owner only, after sign-in).
- [ ] If accepted, by 26 Nov:
  - Prepare the camera-ready with real authors (`\usepackage{wacv}`, fill in `\author`).
  - Plan in-person attendance on 4 or 5 Jan 2027.

## Owner TODOs

1. **Venue.** Choose between the VisionDocs short paper, ICDAR 2027 or both (see "Fit").
2. **Authors.** Add author names, affiliation and contact, for the camera-ready only. The review copy
   stays "Anonymous".
3. **Compile.** There is no TeX engine on this machine (`which tectonic pdflatex latexmk` found
   none). Either compile on Overleaf, or install TeX into a dedicated environment, not base.
4. **Open items carried over from `../paper.md`:**
   - Model snapshot IDs and prices.
   - How the per-1,000-page costs in `site/data/results.js` were computed.
   - Licence checks for the READoc documents sent to OpenAI and MinerU's cloud, and for FinanceBench
     data.
5. **Optional re-runs.** These are not needed for this draft, and each loads the laptop:
   - The Docling READoc tables with commit `183f1dd`, about 20–30 minutes.
   - MinerU on more of the 905 held-out papers, which would change the 313-paper column.

## Page count

Not compiled. The estimate is about 3.3–3.6 pages of body text plus about half a page of references:

- About 2,460 words of prose, including the abstract.
- Two single-column tables and one full-width table, with no figures.
- A WACV two-column page holds roughly 1,000 words of plain text.

This leaves some slack under the 4-page limit. If it runs over, cut the FinanceBench sentence in
Section 5 and the "Other genres and cost" paragraph, and keep the cost column of Table 2.

## Build

- **Template.** `wacv.sty` and `ieeenat_fullname.bst` are unchanged from the official kit, downloaded
  22 Oct 2026 from <https://wacv.thecvf.com/static/wacv-2027-author-kit-template.zip> (zip SHA-256
  `b137cc8b28f11b2be18da32f3b45c21df39254a2d22b9e3c141d90f72ef18433`). `main.tex` follows the kit's
  `main.tex`, with its `preamble.tex` inlined.
- **Packages.** The kit loads `cleveref` itself, which is why `main.tex` uses `\cref`.
- **Characters.** The source is ASCII only, so it builds with pdflatex.

## Claims and their sources

The source files are:

| Short name | File |
|---|---|
| `results.js` | `section-anything/site/data/results.js` (updated 21 Oct) |
| `docling results` | `section-anything/docs/docling-pr/results.md` (22 Oct) |
| `qasper` | `section-anything/docs/rag-qasper.md` |
| `paper.md` | `section-anything/docs/paper/paper.md` |
| `HANDOFF` | `HANDOFF-section-anything.md` in the workspace root |
| `PLAN` | `section-anything/docs/PLAN-upstream-and-rag.md` |

`main.tex` also carries a `% src:` comment after each block.

| Claim in main.tex | Number(s) | Source |
|---|---|---|
| Held-out arXiv papers (not used in development) | 905 | results.js `readoc.heldout.note`; HANDOFF "Final held-out result, arXiv (21 Oct)" |
| Standard / Quick check / Docling on all 905 | 70.0 / 63.9 / 49.4 | results.js `readoc.heldout.note`; HANDOFF same section |
| Free on all 905 | 52.0 | HANDOFF "Final held-out result"; paper.md Table 1 |
| 313-paper MinerU subset: Standard, MinerU+LLM (Sol), Quick check, MinerU+LLM (Luna), MinerU cloud, Docling | 71.6, 67.2, 66.1, 62.8, 57.3, 49.2 | results.js `readoc.heldout.rows`; HANDOFF "Final held-out result" |
| Free on the 313 subset | 55.8 | paper.md Table 1 (computed from `.tmp/readoc-heldout-out/heldout_scores.json`) |
| Standard vs Docling (905): lead, CI, better/worse | +20.6 (19.3 to 21.8), 773 / 103 | HANDOFF "Final held-out result"; results.js note |
| Standard vs MinerU+LLM (Sol) on 313: lead, CI, p; vs Luna | +4.4 (2.5 to 6.4), p = 6e-6; +8.8 | HANDOFF "Final held-out result"; results.js note |
| Papers prompt fix: development sample, held-out | +5.7, +5.1 | paper.md §4.4; HANDOFF "Papers fix" and "Final held-out result" |
| GitHub, all 1,224: Standard / Quick check / Free / Docling | 75.2 / 74.3 / 75.0 / 75.0 | results.js `readoc.full`; HANDOFF "Full READoc, latest version (21 Oct)" |
| Held-out READMEs (1,124) vs Docling, with CIs | +0.3 (−0.9 to +1.6), −0.6 (−1.8 to +0.7), +0.1 (−1.0 to +1.2) | paper.md §4.6 (`.tmp/readoc-github-latest/scores.json`); HANDOFF "Full READoc, latest version" |
| Development READMEs: Docling, Standard, MinerU range, PyMuPDF4LLM | 73.2, 71.3, 48.2–56.5, 57.5 | results.js `readoc.sample` |
| Free vs Docling on papers without bookmarks | 42.3 vs 46.7 | HANDOFF "Full READoc run" (L801–802); paper.md §4.5 |
| Published READoc arXiv scores: Docling, Marker, MinerU, Nougat | 38.3, 39.4, 42.0, 88.5 | results.js `readoc.published`; paper.md §1 (checked against READoc Tables 3–4) |
| READoc subset sizes | 1,003 arXiv with headings, 1,224 GitHub | paper.md §4.1; HANDOFF |
| Development sample; bootstrap resamples | 200 (100 + 100); 4,000 | paper.md §4.3 |
| Cost per 1,000 pages: Free, Quick check (Luna), Standard (Luna), Standard (Sol) | $0, $0.07, $0.16, $2.9 | results.js `modes[].costPer1000Pages`, `costPer1000PagesStrong` |
| Measured cost per 1,000 pages on the 23 corpus documents: Quick check, Standard (Sol) | $0.04, $2.33 | PLAN "Where we stand" |
| Corpus, 23 documents without OpenStax (1,282 pages): F1 / levels | Standard (Sol) 0.920 / 0.990; Quick check 0.911 / 0.966; Docling 0.896 / 0.957; MinerU+LLM 0.870 / 0.950; Free 0.800 / 0.977 | PLAN "Where we stand"; paper.md Table 4 (23-document columns); HANDOFF L674–677 |
| Corpus matching rule | ≥ 85% similar, within one page | paper.md §4.7 (`evaluate.py`) |
| Method parameters: backbone; Quick check; Standard; title flag; extraction speed | ≥ 3 entries and 60%; 70 characters, batches of 300, last 8 decisions; 120,000-character windows, last 8 sections, 8–15-word markers; 1 pt; 0.02 s/page | paper.md §3.1–3.7 and Appendix C |
| Docling option, READoc, full outline (Off → On, Δ, CI, better/same/worse) | arXiv 50.4 → 55.8, +5.4 (+4.0 to +7.0), 42/56/2 (code 183f1dd); GitHub 75.7 → 79.4, +3.7 (+2.1 to +5.4), 27/67/6 | docling results "Main result" |
| Wilcoxon p for those two rows | 3.2e-08, 2.3e-05 (paper says p < 1e-4) | docling results "Main result" |
| Docling option, deepest outline level removed | arXiv (69) 51.6 → 51.9, +0.3 (0.0 to +0.6), 4/65/0; GitHub (100) 75.7 → 75.3, −0.4 (−1.0 to 0.0), 0/97/3 | docling results "Risk check" |
| Docling option, top level only | 0.0 on 100 + 100 | docling results "Risk check" |
| Titles among demotions; key agrees | 57 of 68; 56 of 57 | docling results "What gets demoted", "Title variant" |
| Title-relabel variant | arXiv +8.4 (+6.4 to +10.5); GitHub +3.4 | docling results "Title variant" |
| READMEs hurt by partial outlines | 3 of 100 lose 10–17 points | docling results "Risk check" |
| Off identical to stock Docling | 200 of 200 documents | docling results "Summary" |
| Fresh arXiv papers outside READoc | 8 papers, +4.4 (+0.3 to +10.7), 4 better, 0 worse; +5.5 with title | docling results "Fresh documents (22 Oct)" |
| Canadian federal acts, pre-registered | 9 acts, 0.0 (nothing demoted) | docling results "Fresh documents (22 Oct)" |
| Qasper sample | 200 of 415 papers, 707 questions, 653 with locatable evidence | qasper "Setup", "Evidence recall" |
| Evidence recall, A vs C | 0.933 vs 0.965 at 6,000 tokens (p = 0.002); 0.496 vs 0.649 at 1,200 tokens (p < 0.001) | qasper "Evidence recall" |
| Section boundaries at equal chunk size | +8.7 points at 1,200 tokens (C − A2 = +0.087) | qasper "Evidence recall" |
| Answer F1, A vs C | 0.541 vs 0.534; C − A = −0.007 (−0.030 to +0.015) | qasper "Answer F1" |
| Noise floor when re-asking | 1.5 F1 points | qasper "Noise floor" |
| Papers that fit in 6,000 tokens | 58 of 200 | qasper "Setup" |
| FinanceBench pilot (51 questions) | evidence 34 vs 27 (ours vs fixed); correct 30 (ours) vs 31 (MinerU) | paper.md Table 9; results.js `rag.rows`; HANDOFF "RAG pilot on FinanceBench" |

**Left out on purpose:**

- **OpenStax.** All 26-, 29- and 32-document corpus figures include the three OpenStax documents, so
  none of them is used. The same goes for the per-category "books" figure, which may include
  OpenStax.
- **Speed comparison with Docling and MinerU.** It was measured on the 32-document sample.

## Where sources disagree (the latest was used)

1. **Full READoc scores.**
   - paper.md Table 2 (run of 20 Oct, before the README and papers fixes): Standard 64.8 / 75.4,
     Quick check 60.3 / 70.3.
   - results.js `readoc.full` and HANDOFF "Full READoc, latest version (21 Oct)": 69.9 / 75.2 and
     63.9 / 74.3.
   - The draft uses the 21 Oct GitHub numbers. **paper.md Table 2 is stale.**
2. **Docling bookmark option.**
   - paper.md §5.4 and Table 8 report only the offline simulation (+4.7 arXiv and +5.8 GitHub on all
     bookmarked documents; v4 +1.5 / +5.1).
   - docling results (21–22 Oct) has the real conversions: +5.4 / +3.7 on 100 + 100 documents (rechecked 22 Oct with the fixes, code 183f1dd; +5.2 before them). On
     those same documents the simulation gave +1.6 / +5.5.
   - The draft uses the real-run numbers. **paper.md §5.4 is stale.**
3. **Papers-fix held-out check.**
   - HANDOFF "Held-out check of the papers fix", on 620 papers: Standard 70.7, +4.9, Docling 48.9,
     lead +21.8.
   - Final 905-paper result: 70.0, +5.1, 49.4, +20.6.
   - The draft uses the final 905.
4. **Standard on the development READMEs.**
   - HANDOFF "Competitor baselines" (before the papers fix): 71.8.
   - results.js `readoc.sample` (after the fix): 71.3.
   - The draft uses 71.3.
5. **Cost per 1,000 pages.**
   - results.js: $0.07 (Quick check) and $2.9 (Standard, Sol).
   - PLAN, measured on the 23-document set: $0.04 and $2.33.
   - Both appear in the draft and are labelled. How the results.js figures were computed is not
     documented (paper.md TODO).
6. **Minor.**
   - results.js `rag.date` says 2026-10-19, but its note already includes the 21 Oct Qasper result.
   - results.js `readoc.about` calls READoc "MIT-licensed", but the code repo states no licence
     (paper.md §7).
   - `../venue_fit.md` lists "retrieval-augmented systems" as a topic. On the site it appears in the
     intro text, not in the bulleted topic list.
