# Issue draft (not posted)

**Title:** Opt-in: demote section headers that a complete PDF outline does not list

**Labels (suggested):** enhancement

---

### Requested feature

The heading-hierarchy stage already trusts the PDF outline: a heading that matches a bookmark
takes the bookmark's level, and a matched list item becomes a heading. But a section header that
matches no bookmark is always kept. The layout model labels many non-headings as
`section_header`, for example the paper title, author lines, algorithm captions and lead-ins such
as "Properties:" or "Example:". When the outline is complete, these extra headers are easy to
find: they match no bookmark.

I propose an opt-in option on `HeadingHierarchyOptions`, off by default:

```python
HeadingHierarchyOptions(enabled=True, demote_unmatched_headings=True)
```

When the outline looks complete, every detected section header that matches no bookmark becomes
a `text` item. Matched headers keep the bookmark level, as today. Standard unnumbered headings
that outlines often skip (Abstract, Keywords, Acknowledgements, References, Bibliography,
Appendix) are always kept. Body text is never promoted.

Many outlines are partial, so the option does nothing unless all of these are true:

1. The outline has more than one level. A flat outline usually lists only the chapters.
2. Every detected heading with a dotted number (`2.1 ...`) matches a bookmark.
3. At least half of the detected headings match a bookmark.
4. No two of the headings to demote share a heading-like style: larger than the body text, bold,
   or set in a font face other than the body face. A family like this usually means that the
   outline omits a level.

The change reuses the stage's bookmark matching and its style helpers. It needs
`generate_parsed_pages=True` for check 4. Without parsed pages, nothing is demoted.

### Evidence

Docling 2.140.0 (`main@d01c9c0`) plus the change, default PDF pipeline,
`generate_parsed_pages=True`, `HeadingHierarchyOptions(enabled=True)`. Documents: bookmarked PDFs
from [READoc](https://arxiv.org/abs/2409.05137) (arXiv and GitHub subsets), picked with a fixed
seed. Metric: READoc's heading-tree TEDS (0–100) on Docling's Markdown export. Each document is
compared with the option off and on.

| READoc subset (bookmarked PDFs) | n | off | on | mean change (95% CI) | better / same / worse |
|---|---|---|---|---|---|
| arXiv papers | 100 | 50.4 | 55.6 | +5.2 (+3.8 to +6.8) | 41 / 57 / 2 |
| GitHub READMEs | 100 | 75.7 | 79.4 | +3.7 (+2.1 to +5.4) | 27 / 67 / 6 |

- With the option off, the output is the same as Docling 2.140 on every document (headings
  compared).
- Partial outlines (risk check): we removed the deepest bookmark level, and in a second run kept
  only the top level. With a top-level-only outline, nothing changes (0 of 200 documents). With
  the deepest level removed, the mean change is +0.3 (arXiv, 69 documents) and −0.4 (GitHub, 100
  documents). Three GitHub documents lose 10–17 points: in each, the removed level held a single
  heading, which the style check cannot tell from a false header.
- On arXiv, the most common demotion (56 of 67) is the paper title, which the layout model labels
  `section_header` and the outline does not list. Other demotions: author lines, algorithm
  captions, lead-ins such as "Properties:" or "Example:".

### Questions for maintainers

1. Would you accept this as an opt-in option? Is `demote_unmatched_headings` a good name?
2. Should a demoted heading become `text`, or should a title-like first heading become `title`?
3. Are private constants for the thresholds (for example the 50% match share) OK?
4. Do you prefer to wait for #4169 (page-aware bookmarks), which changes the same file?

This complements #4409. #4409 adds headings that the layout model misses (style promotion). This
proposal removes false headings when the bookmarks show that they are not headings. I have a
local branch with tests and docs, and I can open a PR if you agree with the approach.

### Alternatives

- A post-processing step outside Docling. This works, but the stage already has the outline,
  the matches and the parsed pages, so the check is cheap there (about 0.01 s per document).
- Always drop unmatched headings when bookmarks exist. This removes real headings when the
  outline is partial (for example, every subsection when the outline lists only chapters), so
  the completeness checks are necessary.
