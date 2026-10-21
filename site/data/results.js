// Section Anything website data. The page renders ONLY these numbers; update them here after new runs.
// Every number below was measured with the scripts in hustles/.tmp/readoc-pilot (to be moved into the
// public repo as benchmarks/) unless marked "published".
window.SA_DATA = {
  updated: "2026-10-21",
  repoUrl: "",          // fill in at launch; empty hides repo links
  appUrl: "",           // the demo app's address; empty hides the "Try it" buttons
  tryIt: {
    intro: "Sign in to the demo, upload a PDF and pick Quick check or Standard with \"Your local model\". " +
           "Your browser sends each prompt to the model on your own computer and returns the answer; it costs nothing.",
    steps: [
      "Install Ollama and a small model, for example: ollama pull qwen3:4b (LM Studio and other OpenAI-compatible local servers work too).",
      "Let the demo reach it: restart Ollama with OLLAMA_ORIGINS set to the demo's address (the demo shows the exact command).",
      "Sign in, upload a PDF, choose \"Your local model…\", press Test connection, then Run. Keep the tab open until it finishes.",
      "Allow local network access if your browser asks."
    ],
    privacy: "Your PDF is uploaded to the demo so its text can be read. Prompts go from your browser to your own model; " +
             "nothing is sent to a paid model provider. Quick check suits small local models best."
  },
  status: "Pre-release. Not yet on PyPI.",
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
      title: "arXiv papers not used while developing the method (every tool on the same papers)",
      date: "2026-10-21", docs: 313, subset: "READoc-arXiv",
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", score: 71.6, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6.1-sol)", score: 67.2 },
        { system: "Section Anything Quick check (gpt-6-luna)", score: 66.1, ours: true },
        { system: "MinerU cloud + its LLM title levels (gpt-6-luna)", score: 62.8 },
        { system: "MinerU cloud (3.4.4, vlm)", score: 57.3 },
        { system: "Docling 2.140 (heading hierarchy on)", score: 49.2 }
      ],
      note: "Paired: Standard beats MinerU + LLM (gpt-6.1-sol) by 4.4 points (95% CI 2.5 to 6.4). These are the 313 held-out papers MinerU's cloud had processed; on all 905 held-out papers Standard scores 70.0, Quick check 63.9 and Docling 49.4 (Standard better on 773, worse on 103)."
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
      date: "2026-10-21", docs: { arxiv: 1003, github: 1224 },
      rows: [
        { system: "Section Anything Standard (gpt-6-luna)", arxiv: 69.9, github: 75.2, ours: true },
        { system: "Section Anything Quick check (gpt-6-luna)", arxiv: 63.9, github: 74.3, ours: true },
        { system: "Section Anything Free (no model)", arxiv: 51.3, github: 75.0, ours: true },
        { system: "Docling 2.140 (heading hierarchy on)", arxiv: 49.3, github: 75.0 }
      ],
      note: "All documents with headings in READoc's arXiv and GitHub sets. On the 1,124 GitHub READMEs not used during development, every setting ties with Docling (Standard +0.3, 95% CI -0.9 to +1.6). Our heading text matches the answer key more closely on READMEs (edit similarity 77.8 vs 73.9)."
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
    "Docling scores higher than us on GitHub READMEs in the 200-document sample (73.2 vs 71.3).",
    "MinerU's own LLM step on a stronger model comes within about 4.4 points of our Standard on held-out arXiv papers (67.2 vs 71.6), and is level with it on the 200-document sample (69.3 vs 69.5).",
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
    note: "Heading-aware chunks retrieved the right page more often than fixed chunks. On 10-K filings our headings tied MinerU's. A larger test on harder documents is planned."
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
    { name: "Docling", status: "planned", detail: "A post-processor, and a proposed bookmark-reconciliation improvement upstream." },
    { name: "LlamaIndex / LangChain", status: "planned", detail: "Markdown with correct heading levels works with their Markdown header splitters." }
  ],
  limitations: [
    "Scanned PDFs need OCR first; Section Anything reads the PDF's text layer.",
    "Quick check and Standard send text to the model provider you configure (or to a local model with Ollama).",
    "Every paid run has a hard cost cap per document; models without a known price are refused.",
    "Results above are from October 2026 versions of every tool."
  ]
};
