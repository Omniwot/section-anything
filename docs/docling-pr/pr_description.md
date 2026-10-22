# PR description draft (not opened)

**Title:** `feat(heading-hierarchy): demote section headers that a complete PDF outline does not list`

**Branch:** `feat/bookmark-reconciliation` (local only). Patch: `0001-feat-heading-hierarchy-demote-section-headers-that-a.patch`.

---

<!-- Open only after a maintainer replies to the issue. Replace #NNNN with the issue number and
REPRO_LINK with the public link to docs/docling-pr/repro/. Update the text for the label the
maintainers choose (`text` or `title`, issue question 2). -->

This PR adds an opt-in option to the heading-hierarchy stage:
`HeadingHierarchyOptions.demote_unmatched_headings` (default `False`).

When the PDF outline looks complete, a detected section header that matches no bookmark becomes
a `text` item. Matched headers keep the bookmark level, as today. Standard unnumbered headings
(Abstract, Keywords, Acknowledgements, References, Bibliography, Appendix) are always kept. Body
text is never promoted.

The outline counts as complete only when all of these are true:

- it has more than one level;
- every detected heading with a dotted number (`2.1 ...`) matches a bookmark;
- at least half of the detected headings match a bookmark;
- no two of the headings to demote share a heading-like style (larger than the body text, bold,
  or set in a font face other than the body face).

Otherwise nothing is demoted. The option complements #4409: #4409 adds headings that the layout
model misses, and this option removes false headings when the bookmarks show that they are not
headings.

**Issue resolved by this Pull Request:**
Resolves #NNNN

### Changes

- `docling/datamodel/pipeline_options.py`: new field `demote_unmatched_headings`, and an updated
  class docstring.
- `docling/models/stages/heading_hierarchy/heading_hierarchy_model.py`:
  - `_demote_unmatched_headings`, `_outline_looks_complete` and `_share_a_heading_style` (new).
    They reuse the bookmark matches of `_infer_from_bookmarks`, and `_heading_style` and
    `_cluster_sizes` for the style check.
  - `_heading_cells` (new) holds the cell lookup that `_heading_style` did inline. No behavior
    change.
  - `__call__` keeps the parsed pages when `use_style` or `demote_unmatched_headings` is on.
  - A demoted heading is replaced by a `TextItem` (label `text`) at the same place in the tree. It
    keeps `prov`, `orig`, `text`, `formatting`, `hyperlink`, `content_layer`, `meta`, `source` and
    `comments`. All demoted headings are deleted in one `delete_items` call. Headings with
    children are not demoted.
  - The demotion runs before the levels are collected, so the numbering and style passes see only
    the headings that remain.
- `tests/test_heading_hierarchy_bookmarks.py`: 7 new tests (10 cases) with synthetic documents
  (see below).
- `docs/usage/heading_levels.md` and `docling/.agents/skills/docling/references/python-sdk.md`:
  new subsection, options-table row and notes.

**Checklist:**

- [x] Documentation has been updated, if necessary.
- [ ] Examples have been added, if necessary. (Not added: the option is one line in the existing
      heading-levels example. I can add it if you want.)
- [x] Tests have been added, if necessary.

**Review evidence:**

Behavior before and after:

- Option off (the default): no change. The stage code path is the same, and on 200 real
  PDFs the Markdown is byte-identical to stock Docling 2.140.
- Option on: see the tables below.

Tests (Python 3.11, macOS arm64, docling-core 2.102.0, docling-parse 7.22.3):

```text
pytest tests/test_heading_hierarchy.py tests/test_heading_hierarchy_bookmarks.py \
       tests/test_heading_hierarchy_pdf.py
  70 passed, 2 skipped (the 2 skips need reportlab, which is not installed; same on main)
ruff format --check / ruff check (0.15.12) on the changed files: pass
ty check (0.0.33) on the changed modules: pass
scripts/check_max_lines.py: no new file over the limit (heading_hierarchy_model.py is 819 lines)
.github/scripts/check_skill_routes.py: pass
Not run: make validate and tach (uv and prek are not installed in the test env)
```

New unit tests (synthetic `DoclingDocument` plus a `SegmentedPdfPage`):

| Test | Checks |
|---|---|
| `test_complete_bookmarks_demote_unmatched_heading` | complete outline: the extra header becomes `text`, keeps its prov and its place in the Markdown |
| `test_standard_headings_are_never_demoted` | Abstract, Acknowledgements, References stay headings |
| `test_top_level_only_bookmarks_demote_nothing` | flat outline: nothing demoted |
| `test_outline_missing_its_deepest_level_demotes_nothing[numbered / unnumbered / unnamed-bold-face]` | deepest level missing (dotted number, bold family, `CMBX10` family): nothing demoted |
| `test_outline_matching_under_half_of_the_headings_demotes_nothing` | under 50% matched: nothing demoted |
| `test_demotion_needs_the_option_and_parsed_pages[option-off / no-parsed-pages]` | option off, or no parsed pages: nothing demoted |
| `test_call_collects_parsed_pages_for_demotion` | `__call__` keeps the parsed pages when `use_style=False` |

Each completeness check is guarded by its own test: when we disable one check in the code, the
matching test fails (and only that one).

Real PDFs, heading-tree TEDS from [READoc](https://arxiv.org/abs/2409.05137) (0–100, higher is
better) on Docling's Markdown export. Same conversion, option off vs on, per document.
Settings: default `PdfPipelineOptions`, `generate_parsed_pages=True`,
`HeadingHierarchyOptions(enabled=True)`.

| READoc subset | n | off | on | mean change | 95% CI (bootstrap) | better / same / worse | Wilcoxon p |
|---|---|---|---|---|---|---|---|
| arXiv papers | 100 | 50.4 | 55.6 | +5.22 | +3.77 to +6.78 | 41 / 57 / 2 | 3.2e-08 |
| GitHub READMEs | 100 | 75.7 | 79.4 | +3.69 | +2.07 to +5.37 | 27 / 67 / 6 | 2.3e-05 |

Documents: READoc PDFs with at least 3 outline entries, 100 per subset, picked with a fixed seed.
With the option off, the Markdown is byte-identical to stock Docling 2.140 on all 200 documents.

If a demoted first header becomes `title` instead of `text` (only when it is on page 1 and no
smaller than any other header), our estimate is +7.6 on arXiv and +3.7 on GitHub.

Partial outlines (risk check). The outline is read only by this stage, so we ran the stage again
on the same converted document with a reduced outline:

| READoc subset | Outline | n | mean change (off → on) | 95% CI | better / same / worse |
|---|---|---|---|---|---|
| arXiv | deepest level removed | 69 | +0.29 | +0.01 to +0.64 | 4 / 65 / 0 |
| arXiv | top level only | 100 | 0.00 | 0.00 to 0.00 | 0 / 100 / 0 |
| GitHub | deepest level removed | 100 | −0.43 | −1.00 to 0.00 | 0 / 97 / 3 |
| GitHub | top level only | 100 | 0.00 | 0.00 to 0.00 | 0 / 100 / 0 |

The 3 GitHub losses (−10 to −17 points) have one cause: the removed level held a single heading,
and the style check needs two headings to see a missing level.

Notes:

- On arXiv papers, the most common demotion is the paper title: a real title that the layout
  model labels `section_header` (#3957). In 55 of 56 papers, READoc's answer key marks it as the
  title. Other demotions: author lines, algorithm captions, and lead-ins such as "Properties:" or
  "Example:".
- The thresholds and the font-face part of the style check were tuned while looking at READoc
  documents, including the arXiv papers above. READoc has only papers and READMEs.
- Known misses: (1) a single real heading that the outline omits is demoted; (2) a missing outline
  level set in the body face and size is not detected, unless its headings have dotted numbers.
- The stage adds about 0.01–0.02 s per document.
- Conflicts: #4169 changes the same file (`_infer_from_bookmarks`). This PR does not change
  `_infer_from_bookmarks`.

Scripts, document IDs and per-document scores: REPRO_LINK
