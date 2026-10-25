# Data licences

The code in this repository is licensed under Apache-2.0 (see `LICENSE`). **The data is not.** The
files under `corpus/` (answer keys in `corpus/gold/`, run outputs in `corpus/results/`, and
`corpus/manifest.json`) are derived from third-party documents, which keep their own licences.
The source PDFs are not stored here: `corpus/manifest.json` lists each document's source URL and
SHA-256, and `corpus/tools/` fetches or regenerates them.

- Answer keys derived from the HiPS dataset (`hips-*`) come from Wehnert, Changaramkulath and
  Habernal, *HiPS: Hierarchical PDF Segmentation of Doctrinal Legal Books*
  ([arXiv 2509.00909](https://arxiv.org/abs/2509.00909)); the HiPS annotations are CC BY-NC 4.0 and
  may only be used non-commercially, with attribution.
- Wikipedia-derived keys are CC BY-SA 4.0 (attribution, share-alike).
- GFDL manuals: GNU Free Documentation License 1.3.
- Run outputs quote short passages (section titles and boundary markers) from the documents;
  each quoted string is cut to at most 120 characters.
- For sources under non-commercial, no-derivatives or GPL licences, the run outputs keep only the
  headings; their body-text quotes (boundary markers) are removed.
- Documents whose terms allow local testing only are not published here (answer keys and run
  outputs removed).
- OpenStax textbooks are not included: OpenStax's terms forbid using its books with generative AI
  without written permission, so their keys and results were removed before publication.
- READoc evaluation data used in `docs/docling-pr/` comes from the READoc dataset (MIT,
  [Hugging Face](https://huggingface.co/datasets/lazyc/READoc)); READoc's scoring code is not
  included (its repository has no licence).

## Documents by category and licence

| Category | Licence (as recorded in the manifest) | Documents |
|---|---|---|
| law-books | CC BY-NC-ND (per HiPS data_sources.csv); HiPS annotations CC BY-NC 4.0 | 1: hips-04 |
| law-books | Creative Commons Attribution (CC BY); HiPS annotations CC BY-NC 4.0 | 2: hips-02, hips-10 |
| law-books | Creative Commons Attribution-NonCommercial-NoDerivs (CC BY-NC-ND); HiPS annotations CC BY-NC 4.0 | 7: hips-01, hips-03, hips-05, hips-06, hips-07, hips-08, hips-11 |
| law-books | Creative Commons Attribution-ShareAlike (CC BY-SA); HiPS annotations CC BY-NC 4.0 | 2: hips-09, hips-12 |
| legislation | CC BY 4.0 | 1: law-au-privacy-act-1988 |
| legislation | CC BY 4.0 (e-Gov data portal) | 1: law-jp-appi-english |
| legislation | EUR-Lex: reuse authorised with acknowledgement (Commission Decision 2011/833/EU) | 1: law-eu-gdpr |
| legislation | Federal Ministry of Justice translation; free to use with attribution | 1: law-de-basic-law-english |
| legislation | Government of India (GODL-India) | 1: law-in-information-technology-act-2000 |
| legislation | Irish PSI licence (CC BY 4.0 compatible) | 1: law-ie-data-protection-act-2018 |
| legislation | Open Government Licence v3.0 | 1: law-uk-climate-change-act-2008 |
| legislation | South African government publication | 1: law-za-popia-2013 |
| legislation | US public domain | 2: law-us-chips-and-science-act, law-us-music-modernization-act |
| manuals | Apache-2.0 | 1: manual-requests |
| manuals | BSD-2-Clause | 1: manual-sphinx |
| manuals | CC BY-NC-ND 3.0 | 1: manual-tlcl |
| manuals | CC BY-NC-SA 3.0 | 1: manual-progit |
| manuals | GFDL 1.3 | 2: manual-bash, manual-make |
| manuals | GPL-2 or later | 1: manual-r-intro |
| manuals | GPL-3 / CC BY 4.0 | 1: manual-lo-writer |
| manuals | MIT-CMU (HPND) | 1: manual-pillow |
| manuals | PostgreSQL License | 1: manual-postgresql |
| papers | http://creativecommons.org/licenses/by-nc-sa/4.0/ | 1: arxiv-07 |
| papers | http://creativecommons.org/licenses/by-sa/4.0/ | 1: arxiv-02 |
| papers | http://creativecommons.org/licenses/by/4.0/ | 8: arxiv-01, arxiv-03, arxiv-04, arxiv-05, arxiv-06, arxiv-08, arxiv-09, arxiv-10 |
| prose | Public domain (US); Project Gutenberg text, typeset by the corpus generator | 10: prose-emerson-essays, prose-federalist, prose-hamlet, prose-moby-dick, prose-origin-of-species, prose-pride-and-prejudice, prose-sherlock-holmes, prose-walden-no-headings, prose-war-and-peace, prose-yellow-wallpaper |
| reports | CC BY 3.0 IGO | 1: report-undp-hdr-2023 |
| reports | Public domain (US government work) | 8: report-eia-aeo-2023, report-nasa-artemis-plan, report-nasa-se-handbook, report-nist-ir8312, report-nist-sp1270, report-noaa-arctic-report-card-2023, report-nrel-wind-market-2023, report-usgs-mcs-2024 |
| scanned | CC BY-SA 4.0 | 2: scan-01-wiki-01-en, scan-09-wiki-05-en |
| scanned | GFDL 1.3 | 1: scan-06-manual-bash |
| scanned | Generated; filler text from public-domain Project Gutenberg books | 1: scan-08-synth-numbering-only |
| scanned | Open Government Licence v3.0 | 1: scan-05-law-uk-climate-change-act-2008 |
| scanned | Public domain (US government work) | 1: scan-10-report-nist-ir8312 |
| scanned | Public domain (US); Project Gutenberg text, typeset by the corpus generator | 2: scan-04-prose-pride-and-prejudice, scan-07-prose-hamlet |
| scanned | http://creativecommons.org/licenses/by-sa/4.0/ | 1: scan-02-arxiv-02 |
| slides | Generated; bullet text from public-domain Project Gutenberg books | 10: slides-01-wide-dividers, slides-02-4x3-numbered, slides-03-agenda, slides-04-no-dividers, slides-05-title-bar-nav, slides-06-continued, slides-07-centred, slides-08-handout, slides-09-image-heavy, slides-10-merged-fonts |
| synthetic | Generated | 2: synth-encrypted, synth-truncated |
| synthetic | Generated; filler text from public-domain Project Gutenberg books | 11: synth-bold-body-size, synth-dot-leader-toc, synth-false-positives, synth-image-pages, synth-numbering-only, synth-rotated-pages, synth-run-in, synth-running-headers, synth-six-levels, synth-stress-500, synth-two-column |
| wikipedia | CC BY-SA 4.0 | 10: wiki-01-en, wiki-02-en, wiki-03-en, wiki-04-en, wiki-05-en, wiki-06-en, wiki-07-en, wiki-08-en, wiki-09-en, wiki-10-en |
