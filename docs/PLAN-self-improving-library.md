# Future plan: Section Anything as a self-improving open-source library

Status: future plan, agreed in discussion on 18 Oct 2026. Nothing below is built yet.
Personal, non-commercial project (owner confirmed no employer IP agreement applies).

## Goal

An open-source Python library (Apache-2.0) that turns any PDF into a section tree (titles,
levels, exact text spans, a confidence per heading) and **gets more accurate the more it is
used**, by improving its prompts and rules from user corrections. The Section Anything web
app is its first user; its viewer is where people correct sections.

## Decisions

- **Prompt programs only.** No new models, no fine-tuning, no distillation. Improvement comes
  from prompts, examples and rules.
- **Consequence, stated plainly:** cost per page stays roughly flat (today: Quick check about
  $0.25 and Standard about $0.67 per 100 pages on gpt-5.5). Accuracy is what improves.
- **Local first.** Corrections, profiles and prompts stay on the user's machine. No telemetry.
  Document text goes only to the model provider the user picks.
- **Every change must beat the current version** on the golden corpus and public benchmarks
  before it is used (M2 gate).

## Why the foundation comes first

The two user-facing features (M3, M4) need to know when a result is right. Without the
confidence checks (M1) and the evaluation gate (M2), the prompt library's judge has nothing to
judge with, and the library can get worse without anyone noticing.

## Milestones

### M0 — Split the core into a library (≈ 2–3 days)

- The core is about 1,800 lines in `backend/app/sectioning/`; only `jobs.py` touches the
  database. Move it into a package with no web or database code; configuration by arguments.
- One OpenAI-compatible client for OpenAI, Ollama and OpenRouter, with cost tracking.
- The web app depends on the package.
- Done when the app's tests pass on the package and three lines of Python section a PDF.

### M1 — Confidence from agreement, and automatic checks (≈ 3–4 days)

- Independent signals per heading: bookmark entry, contents-page entry, numbering pattern,
  font size and weight, rules pass, model decision. Weight signals by measured independence
  (several font-size rules are not several votes).
- Checks that flag likely errors: numbering order (1 → 1.1 → 1.2), contents entries matched to
  body lines, markers found, levels consistent with numbering, no duplicate "(cont.)" sections.
- Per-heading confidence with the agreeing and disagreeing signals.
- Cascade: only low-confidence regions go to the next stop (Consensus Entropy idea).
- Done when high-confidence headings are right at least 95% of the time on the golden corpus.

### M2 — Evaluation harness and regression gate (≈ 3–5 days)

- `eval` runs the golden corpus (115 English docs, 11 categories) plus benchmark adapters with
  official scorers: DocHieNet (published: GPT-5.2 57.8 TEDS, purpose-built models 71–79),
  Comp-HRDoc, READoc.
- **Answer-key audit** (cleanlab idea): flag gold entries the systems consistently disagree
  with, for human review, before trusting any score. Known suspects: the US music act,
  arxiv-07, arxiv-10.
- Traces and datasets through Langfuse (already wired into `llm.py`).
- CI gate on F1 and TEDS per category. OpenAI Batch API (half price) and resume support.

### M3 — Highlight-and-redo: learning within one document (≈ 1–1.5 weeks)

Idea from eScriptorium (correct a little, apply to the rest).

1. The user marks a section, marks a line as not a heading, or moves a boundary.
2. Each correction becomes:
   - a **pinned fact** that is never undone;
   - **examples** for the prompt: the marked line as a positive, similar-looking lines that
     are not headings as negatives;
   - a **rule** the AI writes, for example "level 1 = bold lines starting ARTICLE + Roman
     numeral; 'Section 1.2' = level 2".
3. The revised prompt must reproduce **every correction made so far in this document** before
   it is used; if not, it is revised (GEPA-style reflection), up to about two retries.
4. The document is re-run and the user sees what changed ("12 sections changed"), with undo.
5. Cost control: the new rule is applied in code first; only conflicting regions go to the
   model.

### Experiment before M4 (≈ 1 day, about $5–10)

On three corpus categories, compare type-specific prompts with the general prompt on
held-out documents. Published work shows retrieving the right examples per input helps, but
not that routed prompts beat one well-optimised prompt (the 2026 p1 paper argues for fewer
prompts). Build M4 only if type-specific prompts clearly win.

### M4 — Profile library with a trial-based judge (≈ 2 weeks)

- **Profile** = one library entry per document type or layout:
  - layout fingerprint (fonts of heading-like lines, numbering scheme, running headers, page
    size, producer) plus a text embedding of the first pages;
  - rules for the free stop;
  - prompt and positive/negative examples for the LLM stops;
  - a short **lessons** note learned from past corrections (Reflexion idea);
  - usage statistics: documents processed, corrections needed.
- **Choosing a profile for a new file:** retrieve the 2–3 closest profiles, run each on sample
  pages, and score them with the M1 checks plus self-consistency (GLaPE idea). The judge is a
  trial run, not a prediction from the file alone.
- **No profile passes:** the AI writes a new profile from the document's opening pages,
  contents page and styles. It joins the library only if its checks pass with high
  confidence or the user confirms or corrects the result.
- **Library health:** profiles that keep needing corrections are retired; every version is
  kept with rollback (GROBID, Voyager and Darwin Gödel Machine ideas).
- Corrections from M3 update the profile used for that document.

### M5 — Library-wide prompt tuning (≈ 1 week)

- Periodically run GEPA (or DSPy) over the profiles, using all collected corrections as the
  answer key, under a budget cap.
- A tuned profile replaces the old one only through the M2 gate.

### M6 — Optional: shared profiles (later)

Opt-in sharing of profiles built from public documents only.

## Metrics

| Metric | Source |
|---|---|
| Heading F1 and tree similarity (TEDS) | Golden corpus and benchmarks (M2) |
| **Corrections per document, per profile, over time** | Correction store. The main self-improvement measure |
| Calibration: accuracy of high-confidence headings | M1 |
| Share of documents matched to an existing profile | M4 |
| Cost per 100 pages, by stop | Eval runs (expected flat) |

## Risks

- Routed prompts may not beat one tuned prompt; the experiment before M4 decides.
- New profiles written without user input can be wrong; gated by checks or user confirmation.
- Over-generalising from one highlight; limited by the "reproduce every correction" check.
- Benchmarks are image-based (DocHieNet, Comp-HRDoc); we need text-layer PDFs.
- Full re-runs on long documents take minutes; show progress and re-run only affected regions
  where possible.

## Research borrowed

| Idea | From | Used in |
|---|---|---|
| Correct a little, apply to the rest | eScriptorium / Kraken | M3 |
| Label-free prompt scoring by self-consistency | GLaPE | M4 judge |
| Lessons learned from failures | Reflexion | M4 profiles |
| Keep a change only if the benchmark improves; archive versions | Voyager, Darwin Gödel Machine, GROBID | M4, M5 |
| Answer-key audit | cleanlab | M2 |
| Traces become datasets | Langfuse | M2, M5 |
| Confidence routing | Consensus Entropy | M1 |
| Reflective prompt optimisation | GEPA, DSPy | M3, M5 |

## Sources

- eScriptorium: https://escriptorium.eu/about/
- GLaPE: https://arxiv.org/abs/2402.02408
- GEPA: https://arxiv.org/abs/2507.19457
- p1 (fewer prompts): https://arxiv.org/abs/2604.08801
- Consensus Entropy: https://arxiv.org/abs/2504.11101
- cleanlab: https://github.com/cleanlab/cleanlab
- GROBID training: https://grobid.readthedocs.io/en/latest/training/General-principles/
- Self-improving agent frameworks: https://futureagi.com/blog/self-improving-ai-agents-open-source-frameworks/
- DocHieNet: https://aclanthology.org/2024.emnlp-main.65/
