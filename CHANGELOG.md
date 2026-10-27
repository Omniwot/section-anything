# Changelog

Releases of the `section-anything` library on [PyPI](https://pypi.org/project/section-anything/).
Scores are READoc heading-tree TEDS (0-100) with READoc's own scoring code.

## 0.1.3 (2026-10-27)

- **`standard` now defaults to `gpt-6-luna`** (was `gpt-6.1-sol`). Every published `standard`
  score (held-out READoc: 70.0 on 905 arXiv papers, 75.5 on 1,124 GitHub READMEs) and its cost
  (about $0.16 per 1,000 pages) was measured on `gpt-6-luna`, so the default now matches them.
  `gpt-6.1-sol` (about $2.90 per 1,000 pages, roughly 18 times the cost) is still priced and can be
  chosen with `SECTIONANY_STANDARD_MODEL=gpt-6.1-sol`, `model="gpt-6.1-sol"` or `--model
  gpt-6.1-sol`. On development documents only (98 READoc papers and 100 READMEs, same code) it scored
  5.8 points higher on READMEs (95% CI +2.1 to +9.6) and 0.9 higher on papers (CI -0.3 to +2.1,
  not significant); this is not confirmed on held-out documents. `quick` (`gpt-6-luna`) and `free` are unchanged.
- The command line's `--model` help names the default models.

## 0.1.2 (2026-10-26)

- **Section numbers split off their titles are kept.** The PDF extractor (pdfminer) splits a line
  where a space is wider than twice the letters beside it, which happens after a section number
  when the title starts with a narrow letter: "1" | "Introduction". The bare "1" looked like a page
  number and was dropped, so the heading lost its number and, in `free`, its level ("###
  Introduction" next to "## 2 Related Work"). Such a number (same baseline, size and weight as the
  title right after it) is now joined to its title in `free` and `quick`, also when a bookmark
  names only the title. Pre-registered held-out test on 905 READoc arXiv papers: `free` +0.7 (95%
  CI +0.5 to +1.0); `quick` +1.7 (95% CI +1.2 to +2.3) on the 291 papers it changes, +0.5 (95% CI
  +0.4 to +0.8) on all; GitHub READMEs unchanged. Held-out scores are now `free` 57.9 (was 57.2) and
  `quick` 68.0 (was 67.4). `standard` is unchanged.
- Not fixed: in `free`, unnumbered headings that share the section style (References, appendices
  lettered without a dot) can still come out one level below the numbered sections when the paper
  title takes the largest style. This is a separate cause.

## 0.1.1 (2026-10-26)

- **Abstract headings are found.** Journals often set "Abstract" bold but smaller than body text,
  or run it into the abstract's first line ("Abstract—We study…", "Abstract. Let…"), so the rules
  never offered it as a heading. On pages 1-2 it is now a candidate whatever its size, in `free`
  and `quick`; `free` gives it the level of the section that follows. Pre-registered held-out test
  on 905 READoc arXiv papers: `free` +2.4 (95% CI +2.0 to +2.7), `quick` +3.7 (95% CI +3.3 to
  +4.1); GitHub READMEs unchanged (-0.02). Held-out scores are now `free` 57.2 (was 54.8) and
  `quick` 67.4 (was 63.9). `standard` does not use the candidates and is unchanged.
- Docs: a Providers section in the package README (tested and untested endpoints, requirements,
  setup).
- Release workflow: `pypa/gh-action-pypi-publish` v1.13.0.

## 0.1.0 (2026-10-25)

- First release on PyPI: `pip install section-anything`. Modes `free`, `quick`, `standard` and
  `local:<model>`, a command line, Markdown and JSON output, and a hard cost cap on every paid run.
- `free` drops headings that a complete-looking PDF outline does not list (the outline check, on by
  default for `free`).
