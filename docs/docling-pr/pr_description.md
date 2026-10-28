# PR description draft (not opened)

Everything above the line `<!-- PR BODY BELOW THIS LINE -->` is internal and is not posted.

**When:** on or after 1 Nov 2026, if issue
[#5002](https://github.com/docling-project/docling/issues/5002) (posted 25 Oct) still has no
maintainer reply. If a maintainer replies first, follow the reply (for example the `text` or
`title` question) and update the body.

## Title (owner chooses)

All three pass Docling's conventional-commit check (`.github/mergify.yml`). Only the `--title`
argument changes; the branch, commits and body stay the same.

| | Title | Why |
|---|---|---|
| **A (recommended)** | `feat(pdf): demote section headers that a complete PDF outline does not list` | `pdf` is the scope of the earlier heading-hierarchy feature PRs (#3633, #3688, #3984, #5071); same words as the issue title |
| B | `feat(heading-hierarchy): demote section headers that a complete PDF outline does not list` | same as the first commit subject; the scope that #4204 used |
| C | `feat(pdf): add opt-in demote_unmatched_headings to the heading-hierarchy stage` | names the option; says less about what it does |

## Branch

- Local clone `.tmp/repos/docling`, branch `feat/bookmark-reconciliation`, rebased on 28 Oct 2026
  onto docling `main@9051777` (2.144.0).
- Commits: `fdb92fd` (feat) and `1b445e0` (fix). Author, committer and DCO sign-off:
  `Omniwot <Omniwot@users.noreply.github.com>`. No other identity or trailer.
- Pre-rebase state kept as local branch `backup/pre-rebase-183f1dd`.
- Rebase conflict: #5071 (merged 28 Oct) keeps only the heading and list-item text lines when
  `generate_parsed_pages=False`. The demotion's style check needs the body lines too, so
  `retain_parsed_lines` now keeps all text lines when the option is on, and the docs no longer
  ask for `generate_parsed_pages=True`. New test:
  `test_demotion_works_on_the_lines_the_pipeline_retains`.
- `0001`/`0002` patches in this folder are the pre-rebase commits; the PR uses the branch.

## Before opening

- [ ] Real-PDF check on the rebased branch. Started on 28 Oct and stopped by the laptop swap
      guard after 1 of 16 conversions. Four PDFs (READoc arXiv `1705.02778`, GitHub `100181`,
      no-outline arXiv `0707.1301`, Docling's `tests/data/pdf/sources/elsevier-00.pdf`); settings
      `off` (upstream main and branch), `on`, `on_gpp`. Expected: branch `off` byte-identical to
      upstream `off`; `on` equal to `on_gpp`; demotions as in the issue example; no change on
      `0707.1301`. Script: `.tmp/bookmark-recon/realpdf-rebase/run_all.sh` (4 runs in a row,
      about 3–5 minutes, swap and pressure guard). Add one line to "Review evidence" when done.
- [ ] Rerun `pytest tests/test_heading_hierarchy_pdf.py` (loads the layout model) on the final
      commits. It passed (3) on the first rebased commit; the second commit and the docs fixup
      came after the swap guard stopped model runs. They touch only the demotion code, which
      those tests do not turn on.
- [ ] `git fetch origin`; if `main` moved, rebase again and rerun the tests and hooks.

## Commands

From the `hustles` workspace root:

```bash
cd .tmp/repos/docling
git fetch origin && git log --oneline -1 origin/main      # 9051777 or newer
gh repo fork docling-project/docling --clone=false --default-branch-only   # once
git remote add fork git@github.com:Omniwot/docling.git                   # once
git push -u fork feat/bookmark-reconciliation

sed '1,/^<!-- PR BODY BELOW THIS LINE -->$/d' \
  ../../sa-doclingpr/docs/docling-pr/pr_description.md > /tmp/docling-pr-body.md
grep -c 'Resolves #5002' /tmp/docling-pr-body.md         # expect 1
url=$(gh pr create --repo docling-project/docling --base main \
  --head Omniwot:feat/bookmark-reconciliation \
  --title "feat(pdf): demote section headers that a complete PDF outline does not list" \
  --body-file /tmp/docling-pr-body.md) && echo "$url"
gh pr view "$url" --json body --jq .body | diff - /tmp/docling-pr-body.md   # expect no output
```

<!-- PR BODY BELOW THIS LINE -->
This PR adds an opt-in option to the heading-hierarchy stage:
`HeadingHierarchyOptions.demote_unmatched_headings` (default `False`).

When the PDF outline looks complete, a detected section header that matches no bookmark becomes
a `text` item. Matched headers keep the bookmark level, as today. Standard unnumbered headings
(Abstract, Keywords, Acknowledgements, References, Bibliography, Appendix) are always kept, also
when letter-spaced. Body text is never promoted.

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
Resolves #5002

### Changes

- `docling/datamodel/pipeline_options.py`: new field `demote_unmatched_headings`, and an updated
  class docstring.
- `docling/models/stages/heading_hierarchy/heading_hierarchy_model.py`:
  - `_demote_unmatched_headings`, `_outline_looks_complete` and `_share_a_heading_style` (new).
    They reuse the bookmark matches of `_infer_from_bookmarks`, and `_heading_style` and
    `_cluster_sizes` for the style check.
  - A heading whose section number belongs to a bookmark that matched no heading counts as
    matched. Bookmark titles sometimes differ from the printed heading, for example unresolved
    LaTeX references in hyperref bookmarks.
  - `_heading_cells` (new) holds the cell lookup that `_heading_style` did inline. No behavior
    change.
  - `retain_parsed_lines` (from #5071): with the option on, it keeps all text lines of each page
    (no character or word cells), because the style check compares the headings with the body
    text. With the option off, it returns what it returns on `main`. So the option does not need
    `generate_parsed_pages=True`.
  - `__call__` collects the parsed pages when `use_style` or `demote_unmatched_headings` is on.
  - A demoted heading is replaced by a `TextItem` (label `text`) at the same place in the tree. It
    keeps `prov`, `orig`, `text`, `formatting`, `hyperlink`, `content_layer`, `meta`, `source` and
    `comments`. All demoted headings are deleted in one `delete_items` call. Headings with
    children are not demoted.
  - The demotion runs before the levels are collected, so the numbering and style passes see only
    the headings that remain.
- `tests/test_heading_hierarchy_bookmarks.py`: 10 new tests (14 cases) with synthetic documents
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

- Option off (the default): no change. The stage takes the same code path as on `main`. Before
  the rebase, on 2,006 READoc PDFs, the Markdown with the option off was byte-identical to stock
  Docling 2.140.0.
- Option on: see the tables below.

Tests and checks on this branch (rebased on `main@9051777`, 2.144.0; Python 3.11, macOS arm64,
docling-core 2.104.0, docling-parse 7.23.0):

```text
pytest tests/test_heading_hierarchy.py tests/test_heading_hierarchy_bookmarks.py
  75 passed, 2 skipped (the 2 skips need reportlab, which uv.lock does not include; same on main)
pytest tests/test_heading_hierarchy_pdf.py
  3 passed
prek run --files <the 5 changed files>   (the hooks that `make validate` runs on a changeset)
  all hooks pass: whitespace, end of file, merge conflict, large files, license header,
  ruff 0.17.2 (lint and format), ty 0.0.33, tach 0.35.3, tach module coverage, max lines
ruff format --check / ruff check on docling tests docs/examples perfs: pass
tach check, check_tach_module_coverage.py, check_skill_routes.py: pass
check_max_lines.py: same output as on main (no new file over the limit)
Not run: dprint and uv lock --locked (no dprint or dependency files changed), the full test suite
```

New unit tests (synthetic `DoclingDocument` plus a `SegmentedPdfPage`):

| Test | Checks |
|---|---|
| `test_complete_bookmarks_demote_unmatched_heading` | complete outline: the extra header becomes `text`, keeps its prov and its place in the Markdown |
| `test_standard_headings_are_never_demoted` | Abstract, Acknowledgements, References stay headings |
| `test_letter_spaced_standard_heading_is_kept` | "A B S T R A C T" stays a heading |
| `test_heading_with_the_number_of_an_unmatched_bookmark_is_kept` | a heading numbered like a bookmark whose title differs stays a heading |
| `test_top_level_only_bookmarks_demote_nothing` | flat outline: nothing demoted |
| `test_outline_missing_its_deepest_level_demotes_nothing[numbered / unnumbered / unnamed-bold-face]` | deepest level missing (dotted number, bold family, `CMBX10` family): nothing demoted |
| `test_outline_matching_under_half_of_the_headings_demotes_nothing` | under 50% matched: nothing demoted |
| `test_demotion_needs_the_option_and_parsed_pages[option-off / no-parsed-pages]` | option off, or no parsed pages: nothing demoted |
| `test_call_collects_parsed_pages_for_demotion` | `__call__` keeps the parsed pages when `use_style=False` |
| `test_demotion_works_on_the_lines_the_pipeline_retains[style-on / style-off]` | the demotion gives the expected result on the page that `retain_parsed_lines` keeps |

Each completeness check is guarded by its own test: when we disable one check in the code, the
matching test fails (and only that one). The last test fails when `retain_parsed_lines` keeps
only the heading lines.

Real PDFs, heading-tree TEDS from [READoc](https://arxiv.org/abs/2409.05137) (0–100, higher is
better) on Docling's Markdown export. Same conversion, option off vs on, per document. Measured
before the rebase: Docling 2.140.0 with this change, default `PdfPipelineOptions`,
`generate_parsed_pages=True`, `HeadingHierarchyOptions(enabled=True)`. The rebase changes how
the pipeline keeps the text lines, not the demotion rules; with the option on, the stage now
gets the same text lines as with `generate_parsed_pages=True`. I did not re-run READoc on the
rebased branch.

| READoc subset | n | off | on | mean change | 95% CI (bootstrap) | better / same / worse | Wilcoxon p |
|---|---|---|---|---|---|---|---|
| arXiv papers | 796 | 49.5 | 55.1 | +5.55 | +4.96 to +6.15 | 328 / 429 / 39 | 1.6e-55 |
| GitHub READMEs | 1,210 | 75.4 | 79.6 | +4.15 | +3.64 to +4.67 | 396 / 764 / 50 | 4.8e-56 |

Documents: every READoc PDF with at least 3 outline entries and headings in its answer key.
With the option off, the Markdown is byte-identical to stock Docling 2.140.0 on all 2,006
documents.

If a demoted first header becomes `title` instead of `text` (only when it is on page 1 and no
smaller than any other header), our estimate on the same documents is +8.1 TEDS on arXiv (796)
and +4.2 on GitHub (1,210), with font sizes from a separate PDF parser.

Partial outlines (risk check). The outline is read only by this stage, so we ran the stage again
on the same converted document with a reduced outline (same setup and metric):

| READoc subset | Outline | n | mean change (off → on) | 95% CI | better / same / worse |
|---|---|---|---|---|---|
| arXiv | deepest level removed | 603 | +0.19 | +0.08 to +0.31 | 19 / 577 / 7 |
| arXiv | top level only | 796 | 0.00 | 0.00 to 0.00 | 0 / 796 / 0 |
| GitHub | deepest level removed | 1,195 | −0.40 | −0.59 to −0.20 | 10 / 1,124 / 61 |
| GitHub | top level only | 1,210 | 0.00 | 0.00 to 0.00 | 0 / 1,210 / 0 |

The GitHub losses come from removed levels that the style check cannot see: a level holding a
single heading, or headings set like body text. With the full outline, 50 of 1,210 READMEs get
worse, a few by 20–30 points (repeated "Declaration" / "Usage" subsections, "32 bit" / "64 bit").

Notes:

- On READoc arXiv papers, the most common demotion is the paper title: a real title that the
  layout model labels `section_header` (#3957). Of the 439 papers where the first header is
  demoted, READoc's answer key marks it as the title in at least 395. Other demotions: author
  lines, algorithm captions, and lead-ins such as "Properties:" or "Example:".
- The thresholds and the font-face part of the style check were tuned while looking at READoc
  documents, including the arXiv papers above. Without the 173 documents we looked at during the
  design, the TEDS change is the same: +5.58 on 721 arXiv papers and +4.17 on 1,112 READMEs. READoc
  has only papers and READMEs; #5002 lists results on documents not used in the design (other
  arXiv papers, UK government reports, law books, Canadian acts, and Docling's `tests/data`
  PDFs).
- Known misses: (1) a single real heading that the outline omits is demoted; (2) a missing outline
  level set in the body face and size is not detected, unless its headings have dotted numbers.
- Time: the stage adds about 0.01–0.02 s per document (200 READoc PDFs, Docling 2.140.0,
  Apple-silicon laptop, CPU). Memory: with the option on and `generate_parsed_pages=False`, the
  pipeline keeps the text-line cells of every page until the stage has run.
- Conflicts: #4169 changes the same file (`_infer_from_bookmarks`). This PR does not change
  `_infer_from_bookmarks`.

Scripts, document IDs and per-document scores: https://github.com/Omniwot/section-anything/tree/main/docs/docling-pr/attachments/docling-demote-unmatched-evidence
