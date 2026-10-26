# Changelog

Releases of the `section-anything` library on [PyPI](https://pypi.org/project/section-anything/).
Scores are READoc heading-tree TEDS (0-100) with READoc's own scoring code.

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
