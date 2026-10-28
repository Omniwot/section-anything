# Changelog

Releases of the `section-anything` library on [PyPI](https://pypi.org/project/section-anything/).
Scores are READoc heading-tree TEDS (0-100) with READoc's own scoring code.

## 0.1.4 (2026-10-28)

- **Claude models on Anthropic's own API**, as a provider next to OpenAI: `pip install
  "section-anything[anthropic]"` (`anthropic>=2.0,<3`), then `ANTHROPIC_API_KEY` and a Claude
  model, for example `SECTIONANY_STANDARD_MODEL=claude-haiku-5-5` or `model="claude-haiku-5-5"`.
  Requests stream through `messages.stream` with the JSON schema in `output_config.format` and
  `output_config.effort="medium"` (at `"low"`, Claude Haiku 5.5 skipped thinking and returned one
  section where there were 21); refusals and answers cut off at `max_tokens` are retried once and
  counted against the cost cap. The defaults are unchanged (`gpt-6-luna` for `quick` and
  `standard`), and OpenAI requests are sent exactly as before. `standard` on development documents
  only (98 READoc papers and 100 READMEs, same code): `claude-haiku-5-5` tied `gpt-6-luna` (papers
  -0.2, 95% CI -3.2 to +2.4; READMEs +0.0, CI -3.8 to +4.0) at about 3 times the cost;
  `claude-sonnet-5-5` scored lower (papers -4.5, CI -7.8 to -1.7; READMEs -8.4, CI -14.0 to -3.4)
  at about 26 times the cost. Not confirmed on held-out documents; `quick`, Opus and Fable were
  not tested.
- **Provider selection**: `SECTIONANY_PROVIDER` / `provider=` / `--provider` (`openai` or
  `anthropic`); unset, `claude-*` model ids go to Anthropic and all others to OpenAI-compatible
  endpoints. A `claude-*` model served by an OpenAI-compatible gateway now needs
  `SECTIONANY_PROVIDER=openai`.
- **Keys never cross providers**: for Claude models the key is `api_key=`, then
  `SECTIONANY_API_KEY`, then `ANTHROPIC_API_KEY` (only while requests go to Anthropic's own
  endpoint). `OPENAI_API_KEY` is never sent to Anthropic, nor `ANTHROPIC_API_KEY` to OpenAI, and a
  key that is plainly the other provider's is refused before anything is sent.
  `SECTIONANY_BASE_URL` works for both, so a gateway or local relay can sit in front of either.
- **Prices**: `claude-haiku-5-5` ($0.10 / $0.50 per 1M tokens; $0.50 / $2.50 for prompts over
  100,000 tokens), `claude-sonnet-5-5` ($2 / $10), `claude-opus-5-5` ($4 / $20) and
  `claude-fable-5-1` ($10 / $50), with cache-read and cache-write prices. `Price` gains optional
  `cache_write`, `cache_write_1h`, `long_prompt_tokens` and `long_prompt`.
- A downgrade (standard -> quick -> free) skips a mode whose model has no key configured, for
  example a Claude `standard` with no OpenAI key for `quick`.
- `lightrag-section-anything` 0.1.1: `ANTHROPIC_API_KEY` also makes the `quick` and `standard`
  engines ready; it now needs `section-anything>=0.1.4`.
- **Up-front estimate for Claude models**: the cost estimate checked against `max_usd` before a
  run now counts Claude prompts at 1.5 characters per token (OpenAI models: 3.6, unchanged) and adds
  an allowance for thinking at the effort sent (half the prompt's tokens at `"medium"`, capped at each
  call's 32,000-token output limit). Before, a Claude estimate could be about half the real cost, so
  the per-document cap and the downgrade could let an over-budget Claude run start.

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
