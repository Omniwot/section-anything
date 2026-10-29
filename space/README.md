---
title: Section Anything
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
suggested_hardware: cpu-basic
pinned: false
license: apache-2.0
short_description: "Find the sections of a PDF: headings, levels, pages, text"
tags:
  - pdf
  - document-structure
  - headings
  - chunking
  - rag
---

# Section Anything demo

Upload a PDF and get its sections: every heading, its level, the pages it spans and the exact
text under it. The demo runs [Section Anything](https://github.com/Omniwot/section-anything)
(`pip install section-anything`, [PyPI](https://pypi.org/project/section-anything/)) in Free
mode on any PDF: PDF bookmarks or the printed table of contents as the outline, then typography
and numbering rules. No model is called and no API key is used.

On three example papers you can also switch to Quick check and Standard, the two modes that use
a model. Those are saved runs (section-anything 0.1.5, gpt-6-luna, 28 Oct 2026), computed once by
the maintainers with [`make_examples.py`](make_examples.py) and stored in `examples/` as headings,
levels, pages and character spans, with each run's cost and time and, where READoc has an answer
key, the paper's READoc heading-tree TEDS. The Space has no API key and never calls a model.

The page shows:

- the heading tree (`tree.to_markdown()`);
- the chosen section's text (`tree.text[start:end]`), with its level, pages and character range;
- a table of all sections (level, number, title, pages, flags);
- a JSON download: the same as `section-anything paper.pdf --format json`, plus each section's `text`;
- for the example papers, a table of the three modes: sections found, READoc heading-tree TEDS on
  that paper (where READoc has an answer key), cost and time of the saved run.

## Privacy

Free mode runs on this Space's CPU and sends nothing to any model. Quick check and Standard are
shown only as saved runs on the example papers: this Space has no API key, so no document is ever
sent to a model from here. Your PDF is processed in memory
and in a temporary folder: uploaded files and the JSON made from them are deleted within two hours
(Gradio's `delete_cache=(3600, 3600)` removes files older than an hour, every hour) and on every
restart. File names and text are not logged. Don't upload confidential documents: this is a
public demo.

## Limits

- 100 pages and 20 MB per PDF; text extraction is stopped after 120 seconds.
- Reads the PDF's text layer. Scanned PDFs need OCR first.
- Free runs live on any PDF. Quick check and Standard are saved runs on the three example papers
  only. To run them on your own PDFs, install the library and use your own API key; `local` runs
  `quick` with an Ollama model on your machine. See the
  [README](https://github.com/Omniwot/section-anything#readme).
- The three examples are examples, not a benchmark. Over 905 held-out READoc arXiv papers the
  README reports heading-tree TEDS of 70.0 for `standard`, 68.0 for `quick` and 60.0 for `free`
  ([results](https://github.com/Omniwot/section-anything#results)).
- A saved run's section text is cut from this Space's own extraction of the paper, and only where
  the cut matches the saved run (a hash of the section's text or of its lines, and the heading
  where the section starts). pdfminer can order a few table lines differently from one extraction
  to the next; a section that does not match shows its heading without text.

## Examples

All three are licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The Space
downloads each from arXiv the first time someone clicks it and does not modify it; no PDF is
stored in this repository.

| Paper | Pages | Why it is here |
|---|---|---|
| *Visual Instruction Tuning*, Liu et al., [arXiv:2304.08485v2](https://arxiv.org/abs/2304.08485v2) | 25 | the README's demo paper; has PDF bookmarks; not in READoc, so no score |
| *Knowledge Is Flat: A Seq2Seq Generative Framework for Various Knowledge Graph Completion*, Chen et al., [arXiv:2209.07299v2](https://arxiv.org/abs/2209.07299v2) | 13 | no PDF bookmarks |
| *Thermalization, Chaos and Hydrodynamics in Classical Hamiltonian Systems*, Ganapa, [arXiv:2305.06327v1](https://arxiv.org/abs/2305.06327v1) | 88 | long, headings four levels deep |

The two READoc papers were picked by a fixed rule from READoc's 905 held-out arXiv papers: in each
group (no bookmarks, 8-100 pages, at least 8 answer-key headings: 73 papers; or 30-100 pages with
an answer key at least three levels deep: 39 papers), the CC BY paper whose Free (0.1.5)
heading-tree TEDS was closest to the group's median (both came out a little below it, at the
41st and 38th percentiles). Each stands for its group, not for papers in general: without
bookmarks Free has less to go on.

Saved runs (section-anything 0.1.5; Quick check and Standard on gpt-6-luna; READoc heading-tree
TEDS on that one paper, with READoc's own scorer):

| Paper | Mode | Sections | TEDS | Cost | Time |
|---|---|---|---|---|---|
| 2304.08485v2 | Free | 19 | - | $0 | 2.6 s |
| 2304.08485v2 | Quick check | 19 | - | $0.0006 | 13.3 s |
| 2304.08485v2 | Standard | 20 | - | $0.0033 | 18.5 s |
| 2209.07299v2 | Free | 28 | 49.9 | $0 | 0.6 s |
| 2209.07299v2 | Quick check | 30 | 46.6 | $0.0009 | 10.5 s |
| 2209.07299v2 | Standard | 22 | 63.5 | $0.0032 | 18.6 s |
| 2305.06327v1 | Free | 85 | 60.4 | $0 | 2.4 s |
| 2305.06327v1 | Quick check | 83 | 71.7 | $0.0028 | 27.4 s |
| 2305.06327v1 | Standard | 65 | 82.6 | $0.0093 | 55.0 s |

Single runs; Quick check and Standard can vary slightly between runs.

## Run locally

Python 3.11 or newer:

```sh
pip install -r requirements.txt
python app.py   # http://127.0.0.1:7860
```

## Links

- Code, benchmarks and issues: https://github.com/Omniwot/section-anything
- Package: https://pypi.org/project/section-anything/
- Website: https://omniwot.github.io/section-anything/
- Colab notebook: https://colab.research.google.com/github/Omniwot/section-anything/blob/main/notebooks/quickstart.ipynb

Licence: Apache-2.0.
