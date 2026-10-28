# Issue (posted 25 Oct 2026 as docling-project/docling#5002)

**Title:** Opt-in: demote section headers that a complete PDF outline does not list

**Labels (suggested):** enhancement

<!-- Evidence is linked from the public repo; attaching the zip is optional. -->

---

### Summary

- **Problem:** the layout model often labels non-headings as `section_header` (paper titles, author
  names, captions, theorem statements). The heading-hierarchy stage keeps them, even when the PDF's
  own outline (its bookmarks) shows they are not sections.
- **Proposal:** an opt-in option, off by default, that turns those headers back into text when the
  outline looks complete.
- **Result:** on every bookmarked READoc document, heading-tree TEDS goes up **+5.6 on 796 arXiv
  papers** and **+4.2 on 1,210 GitHub READMEs**. With the option off, output is byte-identical to
  today.

### How I found it

I was benchmarking a PDF heading library I'm building
([Section Anything](https://github.com/Omniwot/section-anything)) against Docling on
[READoc](https://arxiv.org/abs/2409.05137). Its rule-based mode, which uses the PDF outline as the
skeleton, scored higher than Docling on READoc's arXiv papers only when the PDF had an outline: 53.6 vs 49.1 on the
825 papers with one, 41.0 vs 50.2 on the 178 without (heading-tree TEDS, our 20 Oct run). Docling already reads the outline, but only to set levels for headers
that match it. So I tried using it the other way, to drop headers that match nothing, first on
Docling's saved output and then as a change to the stage itself.

### Example

[arXiv 1705.02778](https://arxiv.org/abs/1705.02778), *Simplicity of Ore monoid rings*, Docling
2.140 with `HeadingHierarchyOptions(enabled=True)`:

| Docling today | PDF outline (bookmarks) | With the option |
|---|---|---|
| `#####` SIMPLICITY OF ORE MONOID RINGS | | (text) |
| `##` PATRIK NYSTEDT | | (text) |
| `##` JOHAN ÖINERT | | (text) |
| `##` JOHAN RICHTER | | (text) |
| `##` 1. Introduction | 1. Introduction | `##` 1. Introduction |
| `###` Outline. In this article, we consider… | 1.1 Background, 1.2 Outline | `###` Outline. In this article, we consider… |
| `##` 2. The center | 2. The center | `##` 2. The center |
| `####` Proposition 6. The following assertions hold: | | (text) |
| `##` 3. Simplicity | 3. Simplicity | `##` 3. Simplicity |
| `##` 4. The monoid N(I) | 4. The monoid N(I) | `##` 4. The monoid N(I) |
| `##` References | References | `##` References |

READoc heading-tree TEDS for this paper: **24.0 → 50.7** (52.9 if the title becomes a `title`
item; see question 2). The option only removes false headers; it does not add missed ones
(here "1.1 Background", which is #4409's territory).

### Proposal

```python
HeadingHierarchyOptions(enabled=True, demote_unmatched_headings=True)  # default False
```

When the outline looks complete, a detected section header that matches no bookmark becomes a
`text` item. Matched headers keep the bookmark level, as today. Always kept: standard headings
that outlines often skip (Abstract, Keywords, Acknowledgements, References, Bibliography,
Appendix), also when letter-spaced.

The outline counts as complete only if **all** of these hold, so partial outlines change nothing:

1. It has more than one level (a flat outline usually lists only chapters).
2. Every detected header with a dotted number (`2.1 …`) matches a bookmark.
3. At least half of the detected headers match a bookmark.
4. No two of the headers to demote share a heading-like style (larger, bold, or a non-body font
   face): such a family usually means the outline skips a level.

A header whose section number belongs to a bookmark that matched nothing also counts as matched
(bookmark titles sometimes differ from the printed heading, for example unresolved LaTeX
references). The style check needs `generate_parsed_pages=True`; without parsed pages nothing is
demoted. Cost: about 0.01 s per document.

### Results

Every READoc document whose PDF has an outline (at least 3 entries) and whose answer key has
headings. Same conversion per document, option off vs on; READoc's own scorer.

| READoc | n | off | on | change (95% CI) | better / same / worse |
|---|---|---|---|---|---|
| arXiv papers | 796 | 49.5 | 55.1 | **+5.6** (+5.0 to +6.2) | 328 / 429 / 39 |
| GitHub READMEs | 1,210 | 75.4 | 79.6 | **+4.2** (+3.6 to +4.7) | 396 / 764 / 50 |

- **Off = today:** byte-identical Markdown on all 2,006 documents.
- **Where it goes wrong:** when the outline omits real headings that the style check misses. On
  arXiv the largest loss is −4.2. On GitHub, 50 READMEs get worse, a few by 20–30 points, e.g.
  repeated "Declaration" / "Usage" subsections under each function, or "32 bit" / "64 bit".
- **Partial outlines:** with only the top outline level, nothing changes (0 of 2,006). With the
  deepest level removed: +0.2 on arXiv, −0.4 on GitHub (61 of 1,195 READMEs worse).
- **Not tuned to these documents:** excluding the 173 documents I looked at while designing it, the
  results are the same (+5.6 / +4.2).

<details>
<summary>More evidence: documents never used in the design (pre-registered where noted)</summary>

| Documents | Answer key from | n | Result |
|---|---|---|---|
| arXiv papers outside READoc | LaTeX source + arXiv title | 8 | TEDS +4.4, none worse |
| UK government reports (gov.uk), pre-registered | each report's HTML version | 15 | heading F1 +1.7 (95% CI +0.3 to +3.5); 2 of 18 demotions were real sections, both in one report |
| Law books ([HiPS](https://arxiv.org/abs/2509.00909)), pre-registered | outline plus headings an annotator added | 11 | acts in 1 book; no section heading demoted |
| Canadian federal acts, pre-registered | official XML | 9 | never acts: Docling labels the marginal notes as headers, so under half match the outline |
| Docling's `tests/data` PDFs | off vs on | 84 | identical except the 2 multi-level-outline files (`elsevier-00`, `llncsdoc`) |

"Pre-registered" means the code, document selection, answer keys and metrics were written down
before any output existed.

</details>

<details>
<summary>What gets demoted, and the title question in numbers</summary>

- arXiv: 601 headers in 448 papers, mostly the paper title (in 439 papers; READoc's key has that
  exact text as the document title in at least 395), plus author names, algorithm captions and
  lead-ins such as "Properties:".
- GitHub: 1,003 headers in 461 READMEs, e.g. "Say we set a role like so:", "Example:",
  "IMPORTANT NOTICE:", "Table of Contents".
- Turning a demoted first header into `title` instead of `text`: arXiv +8.4 instead of +5.6, but on
  GitHub such a header is rarely a title. Requiring it to be on page 1 and no smaller than any
  other header gives +8.1 / +4.2 (estimated with font sizes from a separate PDF parser).

</details>

**Evidence:** [docs/docling-pr/attachments/docling-demote-unmatched-evidence](https://github.com/Omniwot/section-anything/tree/main/docs/docling-pr/attachments/docling-demote-unmatched-evidence)
(also as a [zip](https://github.com/Omniwot/section-anything/raw/main/docs/docling-pr/attachments/docling-demote-unmatched-evidence.zip)): document IDs, per-document
scores (off, on, `title`, reduced outlines), the conversion and scoring scripts, and the example above. READoc's
scoring code is not included (its repository has no licence); the README says how to get it.

### Questions for maintainers

1. Would you accept this as an opt-in option? Is `demote_unmatched_headings` a good name?
2. Should a demoted first header become `text` (my code today) or a `title` item when it is on
   page 1 and no smaller than any other header? #3957 says `TITLE` is collapsed into
   `SECTION_HEADER` on purpose, so I did not want to change that without asking.
3. Are private constants for the thresholds (for example the 50% match share) OK?
4. Should this wait for #4169 (page-aware bookmarks, same file)? And should headers that #4148 takes
   from a tagged-PDF structure tree be exempt?

Related: #4409 (the opposite direction: promote missed headings; my style check uses the same
font-face signal), #4114 (other false headers), #4701 (title in chunk headings). I have a local
branch with tests and docs and can open a PR if you agree with the approach.
