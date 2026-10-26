// Section Anything website data. The page renders ONLY these numbers; update them here after new runs.
// Every number below was measured with the scripts in hustles/.tmp/readoc-pilot (to be moved into the
// public repo as benchmarks/) unless marked "published".
window.SA_DATA = {
  updated: "2026-10-25",
  repoUrl: "https://github.com/Omniwot/section-anything",
  appUrl: "",           // the demo app's address; empty hides the "Try it" buttons
  tryIt: {
    intro: "The demo app is not online yet. The library and command line work today: install from PyPI (Python 3.11 or newer) and run it on your own PDFs.",
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
    { id: "standard", name: "Standard", model: "an LLM (gpt-6-luna or gpt-6.1-sol)", sends: "the document text",
      how: "The model reads every line, with font hints, and marks where each section starts and ends.",
      costPer1000Pages: 0.16, costPer1000PagesStrong: 2.9 },
    { id: "local", name: "Local", model: "a local model through Ollama", sends: "nothing leaves your machine",
      how: "Quick check run on your own hardware. Slower; quality depends on the model.",
      costPer1000Pages: 0 }
  ],
  readoc: {
    about: "READoc (ACL Findings 2025; dataset MIT-licensed on Hugging Face) converts real PDFs to Markdown and scores the heading tree " +
           "with tree edit distance similarity (Heading Tree TEDS, 0-100, higher is better). We use READoc's own scoring code.",
    link: "https://github.com/icip-cas/READoc",
    heldout: {
      title: "arXiv papers not used while developing the method",
      date: "2026-10-25", docs: 905, subset: "READoc-arXiv",
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", score: 70.0, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna)", score: 63.9, ours: true },
        { system: "Section Anything Free (no model, outline check)", score: 54.8, ours: true },
        { system: "Docling 2.140 (heading hierarchy on)", score: 49.4 }
      ],
      note: "Standard leads Docling by 20.6 points on these 905 papers. Free includes the outline check shipped on 25 Oct (52.0 before it)."
    },
    heldoutMinerU: {
      title: "The same held-out papers with MinerU (every tool on the same papers)",
      date: "2026-10-25", docs: 905, subset: "READoc-arXiv",
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", score: 70.0, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6.1-sol)", score: 64.8 },
        { system: "Section Anything Quick check (gpt-6-luna)", score: 63.9, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6-luna)", score: 62.7 },
        { system: "MinerU cloud (3.4.4, vlm)", score: 53.9 },
        { system: "Docling 2.140 (heading hierarchy on)", score: 49.4 }
      ],
      note: "Paired: Standard beats MinerU + LLM (gpt-6.1-sol) by 5.1 points (95% CI 4.0 to 6.2). MinerU's cloud processed all 905 held-out papers. Its LLM step with gpt-6.1-sol gave up on 154 of them and kept MinerU's raw levels; without those papers the lead is 2.8 points (95% CI 1.6 to 3.9)."
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
      title: "Full READoc, latest version of every setting",
      date: "2026-10-25", docs: { arxiv: 1003, github: 1224 },
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", arxiv: 69.9, github: 75.2, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna)", arxiv: 63.9, github: 74.3, ours: true },
        { system: "Section Anything Free (no model, outline check)", arxiv: 54.2, github: 81.3, ours: true },
        { system: "Docling 2.140 (heading hierarchy on)", arxiv: 49.3, github: 75.0 }
      ],
      note: "All documents with headings in READoc's arXiv and GitHub sets. On the 1,124 GitHub READMEs not used during development, every setting ties with Docling (Standard +0.3, 95% CI -0.9 to +1.6). Our heading text matches the answer key more closely on READMEs (edit similarity 77.8 vs 73.9). Free includes the outline check shipped on 25 Oct (51.3 / 75.0 before it)."
    },
    published: {
      title: "Published READoc results (older tool versions, from the READoc paper)",
      rows: [
        { system: "Nougat-base", arxiv: 88.5, github: 37.0 },
        { system: "GOT-OCR 2.0", arxiv: 57.7, github: 50.1 },
        { system: "MinerU", arxiv: 42.0, github: 47.2 },
        { system: "Marker", arxiv: 39.4, github: 37.5 },
        { system: "Docling", arxiv: 38.3, github: 22.8 }
      ],
      note: "Not comparable to our runs: tools have changed since. Nougat, trained on arXiv papers, still leads on arXiv."
    }
  },
  where_others_win: [
    "On GitHub READMEs our quick and standard only tie with Docling (about 75); free with the outline check (25 Oct) leads, 81.9 vs Docling 75.5 on 1,112 bookmarked READMEs not used in development.",
    "MinerU's own LLM step on a stronger model comes within about 5 points of our Standard on held-out arXiv papers (64.8 vs 70.0), and is level with it on the 200-document sample (69.3 vs 69.5).",
    "Nougat, an OCR model trained on arXiv, scores far higher on arXiv papers (88.5, published).",
    "Free mode depends on PDF bookmarks: without them it is weaker than Docling on papers."
  ],
  rag: {
    title: "Do better headings give better RAG answers?",
    date: "2026-10-19",
    about: "FinanceBench pilot: 27 public SEC filings, 51 questions. Same text, embeddings, context size and models in every arm; only the headings change.",
    rows: [
      { arm: "Fixed-size chunks, no headings", evidence: 27, correct: 25 },
      { arm: "Chunks split at MinerU's headings", evidence: 34, correct: 31 },
      { arm: "Chunks split at Section Anything's headings", evidence: 34, correct: 30, ours: true }
    ],
    of: 51,
    note: "Heading-aware chunks retrieved the right page more often than fixed chunks. On 10-K filings our headings tied MinerU's. " +
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
  examplesNote: "Examples from the 200-document sample (Standard with gpt-6.1-sol, 2026-10-19). Answer keys are READoc's.",
  integrations: [
    { name: "LightRAG", status: "built, not yet released",
      detail: "A parser plugin: engines sectionany_free, sectionany_quick, sectionany_standard and sectionany_local write LightRAG's .blocks.jsonl, so its heading-aware chunker works on PDFs without a MinerU or Docling service." },
    { name: "RAG-Anything", status: "planned", detail: "Converter to its content-list format." },
    { name: "Docling", status: "proposed upstream", detail: "An opt-in option that demotes headers a complete PDF outline does not list: +5.6 TEDS on 796 bookmarked READoc papers, +4.2 on 1,210 READMEs. Issue docling-project/docling#5002 (open)." },
    { name: "LlamaIndex / LangChain", status: "planned", detail: "Markdown with correct heading levels works with their Markdown header splitters." }
  ],
  limitations: [
    "Scanned PDFs need OCR first; Section Anything reads the PDF's text layer.",
    "Quick check and Standard send text to the model provider you configure (or to a local model with Ollama).",
    "Every paid run has a hard cost cap per document; models without a known price are refused.",
    "Free drops headings that a complete-looking PDF outline does not list; when the bookmarks stop at the top levels, real deeper headings are lost (about 6% of READMEs lose more than 5 points). SECTIONANY_DEMOTE_UNLISTED_HEADINGS='[]' turns this off.",
    "Results above are from October 2026 versions of every tool."
  ]
};
