# Issue draft (not posted)

**Title:** Opt-in: demote section headers that a complete PDF outline does not list

**Labels (suggested):** enhancement

<!-- Before posting: replace REPRO_LINK with the public link to docs/docling-pr/repro/. -->

---

### Requested feature

The heading-hierarchy stage already trusts the PDF outline: a matched header takes the bookmark's
level, and a matched list item becomes a header. A section header that matches no bookmark is
always kept, though, and the layout model labels many such lines `section_header`: the paper title,
author lines, algorithm captions, lead-ins such as "Properties:". When the outline is complete,
these are easy to find, because they match no bookmark.

Proposal: an option on `HeadingHierarchyOptions`, off by default:

```python
HeadingHierarchyOptions(enabled=True, demote_unmatched_headings=True)
```

When the outline looks complete, an unmatched section header is demoted. Matched headers keep the
bookmark level. Standard unnumbered headings that outlines often skip (Abstract, References,
Appendix, …) are always kept, also when letter-spaced, and nothing is promoted. A header whose
section number belongs to a bookmark that matched nothing counts as matched (bookmark titles
sometimes differ from the printed heading, for example unresolved LaTeX references). The outline counts as complete only if it
has more than one level, every dotted-number header (`2.1 …`) matches a bookmark, at least half of
the headers match, and no two of the headers to demote share a heading-like style (larger, bold, or
a non-body face), since such a family usually means the outline skips a level. The style check
needs `generate_parsed_pages=True`; without parsed pages nothing is demoted.

### Evidence

[READoc](https://arxiv.org/abs/2409.05137) heading-tree TEDS (0–100) on Docling 2.140.0's
Markdown export, on every READoc document whose PDF has an outline (at least 3 entries) and whose
answer key has headings: 796 arXiv papers and 1,210 GitHub READMEs. Same conversion per document,
option off vs on. The table shows two ways to demote the first header, which is usually the paper
title (see question 2):

| READoc subset | off | on, demoted → `text` | on, demoted first header → `title` |
|---|---|---|---|
| arXiv papers (796) | 49.5 | 55.1 (+5.6, 95% CI +5.0 to +6.2) | 57.9 (+8.4, +7.7 to +9.2) |
| GitHub READMEs (1,210) | 75.4 | 79.6 (+4.2, +3.6 to +4.7) | 79.4 (+4.0, +3.5 to +4.5) |

- With the option off, the Markdown is byte-identical to stock Docling 2.140 on all 2,006 documents.
- Better / same / worse with `text`: arXiv 328 / 429 / 39 (largest loss −4.2), GitHub 396 / 764 / 50.
  The GitHub losses include a few large ones (−30, −24, −22) where the outline omits real headings
  that the style check does not catch: repeated "Declaration" / "Usage" subsections under each
  function, or short sibling headings such as "32 bit" / "64 bit".
- Partial outlines: with only the top level, nothing changes (0 of 2,006). With the deepest level
  removed, the mean change is +0.2 on arXiv (603 documents; 19 better, 7 worse) and −0.4 on GitHub
  (1,195; 10 better, 61 worse).
- Excluding the documents I looked at while designing the option (75 arXiv, 98 GitHub), the
  results are the same: arXiv +5.6, GitHub +4.2.
- Documents not used in the design: on 8 other arXiv papers (keys from their LaTeX source) the
  change is +4.4 TEDS with `text` and +5.5 with `title`, none worse. On 9 Canadian federal acts
  (keys from the official XML) the option does nothing: the layout model labels the marginal notes
  as section headers, so far fewer than half of the headers match a bookmark and the completeness
  check stops it. That run was pre-registered (code, keys and metrics fixed before any output).
- On 11 law books whose keys include headings the bookmarks omit
  ([HiPS](https://arxiv.org/abs/2509.00909), also pre-registered), it acts in 1 book, demotes no
  section heading, and changes nothing in the other 10. On 15 UK government reports (keys from
  their HTML versions, pre-registered), heading F1 rises +1.7 (95% CI +0.3 to +3.5); 2 of 18
  demotions were real sections the outline omits, both in one report.
- On all 84 PDFs in `tests/data`, the output with the option on is identical to off except for the
  2 files with multi-level outlines where it demotes headers (`elsevier-00`, `llncsdoc`).
- Limits of this evidence: the thresholds and the font-face part of the style check were tuned
  while looking at READoc documents; the unseen sets above are the check on that.

Scripts, document IDs and per-document scores: REPRO_LINK

<details>
<summary>What gets demoted, and the documents that got worse</summary>

- arXiv: 601 headers demoted in 448 papers; the first header (usually the paper title) in 439,
  and READoc's answer key has that exact text as the document title (`#`) in at least 395 of them.
  Others: author lines, algorithm captions, "Properties:".
- GitHub: 1,003 headers demoted in 461 READMEs, for example "Say we set a role like so:",
  "Example:", "IMPORTANT NOTICE:", "Table of Contents".
- `title` variant: on GitHub a demoted first header is rarely a title (20 READMEs; `title` makes
  them worse). Requiring the first header to be on page 1 and no smaller than any other header keeps
  those as `text`; with that check, our estimate is +8.1 on arXiv and +4.2 on GitHub (font sizes from
  a separate PDF parser, so approximate).
- Runtime: the extra checks take about 0.01 s per document.

</details>

### Questions for maintainers

1. Would you accept this as an opt-in option? Is `demote_unmatched_headings` a good name?
2. A demoted first header is usually the paper title, and in at least 395 of 439 papers READoc's key marks it
   as the title. Should it become `text` (the code today), or `title` when it is on page 1 and no
   smaller than any other header? #3957 says `TITLE` is collapsed into `SECTION_HEADER` on purpose,
   so I did not want to change that without asking. `title` also gives chunkers the document title
   as the top of each heading path (compare #4701).
3. Are private constants for the thresholds (for example the 50% match share) OK?
4. Order with open PRs: should this wait for #4169 (page-aware bookmarks, same file)? Its page
   check would also stop a printed table-of-contents line from taking a bookmark's match. And
   should headers that #4148 takes from a tagged-PDF structure tree be exempt?

Related: #4409 proposes the opposite direction (promote body-size lines set in a non-dominant face
to headers); the face part of my style check uses the same signal to detect a skipped outline
level. #4114 reports other false headers (bold CLI examples) that this option would demote when an
outline exists. I have a local branch with tests and docs and can open a PR if you agree with the
approach.

### Alternatives

- Post-processing outside Docling. This works, but the stage already has the outline, the matches
  and the parsed pages, so the check is cheap there.
- Always drop unmatched headers when bookmarks exist. This removes real headers when the outline is
  partial (for example, every subsection when the outline lists only chapters), so the completeness
  checks are needed.
