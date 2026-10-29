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

# Section Anything: Free mode demo

Upload a PDF and get its sections: every heading, its level, the pages it spans and the exact
text under it. The demo runs [Section Anything](https://github.com/Omniwot/section-anything)
(`pip install section-anything`, [PyPI](https://pypi.org/project/section-anything/)) in Free
mode: PDF bookmarks or the printed table of contents as the outline, then typography and
numbering rules. No model is called and no API key is used.

The page shows:

- the heading tree (`tree.to_markdown()`);
- the chosen section's text (`tree.text[start:end]`), with its level, pages and character range;
- a table of all sections (level, number, title, pages, flags);
- a JSON download: the same as `section-anything paper.pdf --format json`, plus each section's `text`.

## Privacy

Free mode runs on this Space's CPU and sends nothing to any model. Your PDF is processed in memory
and in a temporary folder: uploaded files and the JSON made from them are deleted within two hours
(Gradio's `delete_cache=(3600, 3600)` removes files older than an hour, every hour) and on every
restart. File names and text are not logged. Don't upload confidential documents: this is a
public demo.

## Limits

- 100 pages and 20 MB per PDF; text extraction is stopped after 120 seconds.
- Reads the PDF's text layer. Scanned PDFs need OCR first.
- Free mode only. In the library, `quick` and `standard` use a model with your own API key and
  score higher on papers (READoc heading-tree TEDS on 905 held-out arXiv papers: `free` 60.0,
  `quick` 68.0, `standard` 70.0); `local` runs `quick` with an Ollama model on your machine. See
  the [README](https://github.com/Omniwot/section-anything#readme).

## Example

*Visual Instruction Tuning*, Liu et al.,
[arXiv:2304.08485](https://arxiv.org/abs/2304.08485) (v2), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The Space downloads it from arXiv the
first time someone clicks "Try the example paper" and does not modify it.

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
