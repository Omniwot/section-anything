// Section Anything website data. The page renders ONLY these numbers; update them here after new runs.
// Every number below was measured with the scripts in hustles/.tmp/readoc-pilot (to be moved into the
// public repo as benchmarks/) unless marked "published".
window.SA_DATA = {
  updated: "2026-10-28",
  repoUrl: "https://github.com/Omniwot/section-anything",
  appUrl: "https://huggingface.co/spaces/Omniwot/section-anything",  // the demo app's address; empty hides the "Try it" buttons
  tryIt: {
    intro: "Try Free mode in the browser on the Hugging Face Space (no key; up to 100 pages and 20 MB; don't upload confidential documents), or install the library and run it on your own PDFs (Python 3.11 or newer).",
    steps: [
      "Install: pip install section-anything (latest from GitHub: pip install \"git+https://github.com/Omniwot/section-anything#subdirectory=packages/section-anything\")",
      "Free mode, no model and no key: section-anything paper.pdf",
      "Quick check with a model: set SECTIONANY_API_KEY (or OPENAI_API_KEY), then section-anything paper.pdf --mode quick --max-usd 0.5",
      "Fully local: install Ollama and a small model (for example ollama pull qwen3:4b), then section-anything paper.pdf --mode local:qwen3:4b"
    ],
    privacy: "Free and local modes send nothing anywhere. Quick check and Standard send text to the model provider you configure, with a hard cost cap per document."
  },
  status: "Pre-release (0.1). The API may change before 1.0.",
  modes: [
    { id: "free", name: "Free", model: "none", sends: "nothing leaves your machine",
      how: "PDF bookmarks or the printed table of contents as the skeleton, then typography and numbering rules for the rest.",
      costPer1000Pages: 0 },
    { id: "quick", name: "Quick check", model: "a small LLM (we test gpt-6-luna)", sends: "only the candidate heading lines",
      how: "The rules propose candidate lines; a small model keeps the real headings and sets their levels.",
      costPer1000Pages: 0.07 },
    { id: "standard", name: "Standard", model: "an LLM (gpt-6-luna by default, as in every READoc table here; gpt-6.1-sol optional)", sends: "the document text",
      how: "The model reads every line, with font hints, and marks where each section starts and ends.",
      costPer1000Pages: 0.16, costPer1000PagesStrong: 2.9 },
    { id: "local", name: "Local", model: "a local model through Ollama", sends: "nothing leaves your machine",
      how: "Quick check run on your own hardware. Slower; quality depends on the model.",
      costPer1000Pages: 0 }
  ],
  readoc: {
    about: "READoc (ACL Findings 2025; dataset MIT-licensed on Hugging Face) converts real PDFs to Markdown and scores the heading tree " +
           "with tree edit distance similarity (Heading Tree TEDS, 0-100, higher is better). We use READoc's own scoring code. " +
           "Docling and MinerU convert whole documents (layout, tables, figures, formulas, OCR); these tables compare only the heading tree.",
    link: "https://github.com/icip-cas/READoc",
    heldout: {
      title: "arXiv papers not used while developing the method",
      date: "2026-10-28", docs: 905, subset: "READoc-arXiv",
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", score: 70.0, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna)", score: 68.0, ours: true },
        { system: "Section Anything Free (no model)", score: 60.0, ours: true },
        { system: "Docling 2.140 (heading hierarchy on)", score: 49.4 }
      ],
      note: "Paired per paper, Standard minus Docling is +20.6 points on these 905 papers (95% CI 19.3 to 21.8); Standard scored higher on 773 papers and Docling on 103 (by more than 0.5 points). Quick check is release 0.1.2 and Free release 0.1.5. Release 0.1.1 found the abstract's heading (journals often set it small, bold or run into the first line): in a pre-registered held-out test it added 2.4 points to Free (95% CI 2.0 to 2.7) and 3.7 to Quick check (95% CI 3.3 to 4.1) on these papers (0.1.0: 54.8 and 63.9). Release 0.1.2 keeps a section number that the PDF extractor split off its title (\"1\" | \"Introduction\"): in a second pre-registered test it added 0.7 to Free (95% CI 0.5 to 1.0) and 0.5 to Quick check (95% CI 0.4 to 0.8; 1.7 on the 291 papers it changes) (0.1.1: 57.2 and 67.4). Release 0.1.5 gives back matter (References, Acknowledgements, Appendix) and appendix sections the level of the numbered sections: in a fourth pre-registered test on these papers it added 2.1 points to Free (95% CI 1.7 to 2.4; 136 papers better, 4 worse) (0.1.4: 57.9), with READMEs unchanged. Standard uses none of these. Free includes the outline check (52.0 before it)."
    },
    heldoutMinerU: {
      title: "The same held-out papers with MinerU (every tool on the same papers)",
      date: "2026-10-26", docs: 905, subset: "READoc-arXiv",
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", score: 70.0, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna)", score: 68.0, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6.1-sol)", score: 64.8 },
        { system: "MinerU cloud + its LLM title levels (gpt-6-luna)", score: 62.7 },
        { system: "MinerU cloud (3.4.4, vlm)", score: 53.9 },
        { system: "Docling 2.140 (heading hierarchy on)", score: 49.4 }
      ],
      note: "Paired per paper, Standard minus MinerU + LLM (gpt-6.1-sol) is +5.1 points (95% CI 4.0 to 6.2). MinerU's cloud processed all 905 held-out papers. We ran its LLM title-level step through our own relay; with gpt-6.1-sol it returned no parsable levels for 154 of them after three tries and kept MinerU's raw levels (failures in the first 313 papers were not logged; with gpt-6-luna none of the 592 logged papers failed); without those 154 papers the difference is +2.8 points (95% CI 1.6 to 3.9). Quick check (release 0.1.2; 67.4 in 0.1.1, 63.9 in 0.1.0), which sends only candidate lines, is 3.1 points above MinerU + LLM (gpt-6.1-sol) (95% CI 2.1 to 4.1), but level with it without the 154 papers (+1.0, 95% CI −0.03 to 2.0)."
    },
    sample: {
      title: "Every tool on the same READoc sample (200 documents drawn; 198 have headings in the answer key)",
      date: "2026-10-21", docs: { arxiv: 98, github: 100 },
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", arxiv: 69.5, github: 71.3, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6.1-sol)", arxiv: 69.3, github: 56.5 },
        { system: "MinerU cloud + its LLM title levels (gpt-6-luna)", arxiv: 65.2, github: 52.5 },
        { system: "Section Anything Quick check (gpt-6-luna)", arxiv: 64.5, github: 70.1, ours: true },
        { system: "MinerU cloud (3.4.4, vlm)", arxiv: 56.0, github: 48.2 },
        { system: "PyMuPDF4LLM (pymupdf 2.0)", arxiv: 52.1, github: 57.5 },
        { system: "Docling 2.140 (heading hierarchy on)", arxiv: 48.4, github: 73.2 },
        { system: "Section Anything Free (no model)", arxiv: 45.7, github: 71.5, ours: true }
      ],
      note: "These 200 documents were also used while improving the method, so the held-out table above is the fairer test for our settings."
    },
    full: {
      title: "Full READoc, latest measured version of every setting",
      date: "2026-10-28", docs: { arxiv: 1003, github: 1224 },
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", arxiv: 69.9, github: 75.2, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna, 0.1.0)", arxiv: 63.9, github: 74.3, ours: true },
        { system: "Section Anything Free (no model)", arxiv: 59.4, github: 81.3, ours: true },
        { system: "Docling 2.140 (heading hierarchy on)", arxiv: 49.3, github: 75.0 }
      ],
      note: "All documents with headings in READoc's arXiv and GitHub sets. Free is release 0.1.5 (0.1.4: 57.3 / 81.3; 0.1.1: 56.6 / 81.3; 0.1.0: 54.2 / 81.3; 51.3 / 75.0 before the outline check). Quick check is 0.1.0 (its 0.1.1 and 0.1.2 gains were measured on the 905 held-out papers above). On the 1,124 GitHub READMEs not used during development, Standard and Quick check tie with Docling (Standard +0.3, 95% CI -0.9 to +1.6) and Free scores 6.2 higher (95% CI 5.3 to 7.2). Over all 1,224 READMEs, Standard's heading text is a little closer to the answer key than Docling's (READoc heading edit similarity 77.8 vs 73.9)."
    },
    published: {
      title: "Published READoc results (older tool versions, from the READoc paper, arXiv 2409.05137)",
      rows: [
        { system: "Nougat-base", arxiv: 88.5, github: 37.0 },
        { system: "GOT-OCR 2.0", arxiv: 57.7, github: 50.1 },
        { system: "MinerU", arxiv: 42.0, github: 47.2 },
        { system: "Marker", arxiv: 39.4, github: 37.5 },
        { system: "Docling", arxiv: 38.3, github: 22.8 }
      ],
      note: "Not comparable to our runs: tools have changed since (current Docling scores 49.3 on the full arXiv set in our run, against 38.3 published). Nougat, trained on arXiv papers, has the highest published arXiv score."
    }
  },
  where_others_win: [
    "On the 1,124 READoc GitHub READMEs not used in development, our quick and standard only tie with Docling (about 75 Heading TEDS). Free with the outline check scores 81.9 vs Docling's 75.5 on the 1,112 of them with bookmarks; Docling reaches 79.7 with the same outline idea, proposed upstream in docling#5002.",
    "MinerU with its own LLM title levels on gpt-6.1-sol scores 64.8 vs our Standard's 70.0 on the 905 held-out arXiv papers, and is level with it on the 98 arXiv papers of the development sample (69.3 vs 69.5).",
    "Nougat, an OCR model trained on arXiv, has the highest published Heading TEDS on READoc's arXiv papers (88.5 in the READoc paper, older versions; we have not run it).",
    "Free mode depends on PDF bookmarks: on full READoc arXiv papers without them, Free (20 Oct, before the outline check) scored 41.0 vs Docling's 50.2 on the 178 papers without bookmarks, and 53.6 vs 49.1 on the 825 with them (heading-tree TEDS).",
    "Docling and MinerU also read scanned pages with OCR; Section Anything needs a PDF text layer."
  ],
  rag: {
    title: "Do better headings give better RAG answers?",
    date: "2026-10-19",
    about: "FinanceBench pilot: 27 public SEC filings, 51 questions. Same text, embeddings, context size and models in every arm; only the headings change.",
    rows: [
      { arm: "Fixed-size chunks, no headings", evidence: 27, correct: 25 },
      { arm: "Chunks split at MinerU's headings", evidence: 34, correct: 31 },
      { arm: "Chunks split at Section Anything's headings (Quick check)", evidence: 34, correct: 30, ours: true }
    ],
    of: 51,
    note: "Heading-aware chunks retrieved the right page more often than fixed chunks (a pilot; not significant at 51 questions). On these 10-K filings our headings tied MinerU's. " +
          "A larger test on Qasper (200 NLP papers, 707 questions, official answer F1) found the same pattern: section-aware chunks found the " +
          "evidence more often (96.5% vs 93.3%, and 64.9% vs 49.6% with a small context), mostly because their chunks were smaller, but answer " +
          "quality did not change (F1 0.534 vs 0.541), and better headings (ours, the papers' own, Docling's) made no difference on these short papers."
  },
  examples: [
    { id: "arXiv 0908.3175", title: "The Impact of Stellar Populations on the Dynamics of Merger Remnants",
      problem: "Structure: the title should contain the sections, and References belongs at section level.",
      key: ["# The Impact of Stellar Populations…", "###### Abstract", "## 1 Introduction", "## 2 Sample Selection & Observations", "## 3 The Fundamental Plane and Stellar Populations", "## References"],
      docling: ["## The Impact of Stellar Populations… (same level as the sections)", "(Abstract missing)", "## 1 Introduction", "## 2 Sample Selection & Observations", "## 3 The Fundamental Plane and Stellar Populations", "#### References (nested inside section 3)"],
      ours: ["## The Impact of Stellar Populations…", "### Abstract", "### 1 Introduction", "### 2 Sample Selection & Observations", "### 3 The Fundamental Plane and Stellar Populations", "### References"],
      scores: { docling: 33, ours: 98 } },
    { id: "arXiv 2212.03174", title: "A class of naturally generalized special generic maps",
      problem: "Missed subsections and a false heading.",
      key: ["2. Preliminaries", "  2.1 A short exposition on cell complexes…", "  2.2 Differentiable maps and singular points", "  2.3 Diffeomorphisms and bundles", "  2.4 Special generic maps", "  2.5 Fundamental classes…"],
      docling: ["NAOKI KITAZAWA (author name as a heading)", "2. Preliminaries", "  2.4 Special generic maps", "(2.1, 2.2, 2.3, 2.5 and Abstract missing)"],
      ours: ["Abstract", "2. Preliminaries", "  2.1 … 2.5 (all five)", "(also adds 'Conflict of interest' and 'Data availability', which the key does not count)"],
      scores: { docling: 7, ours: 66 } },
    { id: "GitHub 139609621", title: "RCAN image super-resolution README",
      problem: "Sentences and list steps turned into headings.",
      key: ["Contents", "Introduction", "Train / Prepare training data / Begin to train", "Test / Quick start / The whole test pipeline", "Results / Quantitative Results / Visual Results", "Citation", "Acknowledgements"],
      docling: ["… 14 real headings, plus:", "You can use scripts in file 'TrainRCAN_scripts'…", "1. Prepare test data.", "2. Conduct image SR.", "See Quick start", "underlined"],
      ours: ["All 14 answer-key headings, at the right levels, nothing extra"],
      scores: { docling: 51, ours: 100 } }
  ],
  examplesNote: "Examples from the 200-document development sample (Section Anything Standard with gpt-6.1-sol, an earlier version, 2026-10-19; Docling 2.140 with heading hierarchy on). Answer keys are READoc's. They were chosen to show common heading errors, not typical scores: on the 905 held-out papers Docling scored higher than Standard on 103, and on the sample READMEs Docling scored highest of all tools (73.2).",
  integrations: [
    { name: "LightRAG", status: "on PyPI",
      detail: "pip install lightrag-section-anything. A parser plugin: engines sectionany_free, sectionany_quick, sectionany_standard and sectionany_local write LightRAG's .blocks.jsonl, so its heading-aware chunker works on PDFs without a MinerU or Docling service." },
    { name: "LangChain", status: "on PyPI",
      detail: "pip install langchain-section-anything. SectionAnythingLoader returns one Document per section, with the heading path, pages and character span as metadata." },
    { name: "LlamaIndex", status: "on PyPI",
      detail: "pip install llama-index-readers-section-anything. SectionAnythingReader returns one Document per section, with the heading path, pages and parent/child links; it also works as the .pdf reader of SimpleDirectoryReader." },
    { name: "RAG-Anything", status: "planned", detail: "Converter to its content-list format." },
    { name: "Docling", status: "proposed upstream", detail: "An opt-in option that demotes headers a complete PDF outline does not list: +5.6 Heading TEDS on 796 bookmarked READoc papers, +4.2 on 1,210 READMEs (Docling 2.140, option off vs on, same conversion). Issue docling-project/docling#5002 (open)." }
  ],
  limitations: [
    "Scanned PDFs need OCR first; Section Anything reads the PDF's text layer.",
    "Quick check and Standard send text to the model provider you configure (or to a local model with Ollama).",
    "Every paid run has a hard cost cap per document; models without a known price are refused.",
    "Free drops headings that a complete-looking PDF outline does not list; when the bookmarks stop at the top levels, real deeper headings are lost (about 6% of READMEs lose more than 5 points). SECTIONANY_DEMOTE_UNLISTED_HEADINGS='[]' turns this off.",
    "Results above are from October 2026 versions of every tool."
  ]
};
