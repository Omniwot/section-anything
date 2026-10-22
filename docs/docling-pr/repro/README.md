# Reproduce: Docling `demote_unmatched_headings` on READoc

Files:

- `selection.json`: the 100 arXiv and 100 GitHub READoc document IDs (seed 20261021).
- `per_document_scores.csv`: heading-tree TEDS (×100) per document for each setting. Columns:
  `off`, `on` (demoted headers become `text`), `title` (a demoted first header becomes `title`),
  the same with the deepest outline level removed (`*_deep`) and with the top level only (`*_top`),
  the demoted first header, whether READoc's key has it as the `#` title, and its font size against
  the largest other header (from a separate PDF parser, used only for the size-check estimate).
- `run_docling.py`: converts the PDFs once and saves the Markdown for each setting.
- `score.py`: scores the Markdown with READoc's own heading code and prints the paired tables.

Steps:

1. Get the data: the READoc dataset (MIT) from https://huggingface.co/datasets/lazyc/READoc
   (`arxiv/` and `github/`, each with `pdfs/` and `gt/`), and a clone of
   https://github.com/icip-cas/READoc for its scoring code (not bundled here: that repository has
   no licence).
2. Install Docling from the branch with the option (editable install), plus `scipy` and READoc's
   evaluation requirements (`apted`, `nltk`, …).
3. Convert, for each subset:

   ```bash
   python run_docling.py runs/arxiv $(jq -r '.arxiv[]' selection.json | sed 's#^#READOC/arxiv/pdfs/#; s#$#.pdf#')
   python run_docling.py runs/github $(jq -r '.github[]' selection.json | sed 's#^#READOC/github/pdfs/#; s#$#.pdf#')
   ```

   Our run took about 4 s per arXiv PDF and 1.5 s per README PDF on an M-series laptop (CPU).
4. Score:

   ```bash
   READOC_SRC=<READoc clone>/src/evaluation READOC_DATA=READOC python score.py runs
   ```

Settings: Docling 2.140.0 with the change (branch commits `97c09a7` and `183f1dd`), default `PdfPipelineOptions`,
`generate_parsed_pages=True`, `HeadingHierarchyOptions(enabled=True)`; the option is the only
difference between `off` and `on`. Paired statistics: mean of per-document differences, 95%
bootstrap CI (4,000 resamples, seed 0), better / same / worse at ±0.5 points, Wilcoxon signed-rank.

Selection rule: READoc PDFs whose outline has at least 3 entries and whose answer key has headings,
excluding the documents we used while developing the option; then `random.Random(20261021)` picks
100 per subset (pools of 721 arXiv and 1,112 GitHub documents). Outline entries were counted with
pypdfium2, so Docling's own outline depth differs for some documents (31 arXiv PDFs have a flat
outline in Docling, where the option does nothing).
