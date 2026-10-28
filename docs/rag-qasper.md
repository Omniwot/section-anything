# Do better headings give better RAG answers? Qasper, 21 Oct 2026

Run 21 Oct 2026. Nothing was posted. Scripts and raw outputs are in
`<workspace>/.tmp/qasper-rag/` (downloads in `.tmp/qasper-data/`). Before the run, a search for
published work turned up no Qasper study that compares heading-aware chunks with fixed chunks.
Earlier notes ([PLAN-upstream-and-rag.md](PLAN-upstream-and-rag.md)) also found no study that
isolates heading accuracy.

## Short answer

- **Retrieval: yes, any reasonable headings help.** Section-bounded chunks with a section-path
  prefix find the gold evidence more often than fixed 1,200-token chunks: +3 points at a
  6,000-token context, +10 at 2,400 and +15 at 1,200 (all p < 0.01).
- **Heading quality does not matter much.** Gold headings (D), Section Anything Standard (C) and
  Quick check (E) retrieve almost equally well. On the 52 papers with a Docling run, Docling (B)
  matches them too.
- **Much of the retrieval gain is chunk size, not headings.** Section chunks are smaller
  (about 1,900 vs 4,500 characters). Fixed chunks of that size (control A2) recover nearly all
  of the gain at 6,000 tokens and about three quarters of it at 2,400. Section boundaries add a
  significant +9 points only at 1,200 tokens. The section-path prefix adds nothing measurable.
- **Answers: no difference.** Answer F1 is the same for every arm within ±1 point, at both
  6,000 and 2,400 tokens. The 95% CIs on the differences are about ±2.5 points. When C finds
  evidence that A misses, C's answers are clearly better (+16 F1 on those 115 questions). Small
  losses elsewhere cancel this out. Asking the same excerpts a second time moves F1 by 1.5 points,
  as much as any difference between arms.

## Setup

**Data.** Qasper test split v0.3 (official release with its evaluator). 415 test papers have at
least one answerable question. A fixed-seed sample (seed 20261021) took 200 of them, with all
**707 questions**. By the annotators' majority answer type, these are 367 extractive,
169 abstractive, 107 yes/no and 64 unanswerable. All 200 PDFs came from export.arxiv.org (current
version, 3 s apart, no failures). Papers are short: median 9 pages and 8,600 tokens of text;
58 of the 200 fit entirely in 6,000 tokens. 109 have PDF bookmarks.

**Arms.** Every arm uses the same text: our extraction (`app.sectioning.extract`) of the arXiv
PDF. Only the headings change:

| Arm | Headings | Headings anchored on our text |
|---|---|---|
| A | none: fixed chunks of about 1,200 tokens (4,800 chars), 100-token overlap | — |
| B | Docling 2.140, heading-hierarchy stage on (52 papers only, see below) | 909/925 (98.3%) |
| C | Section Anything Standard (`llm_text`, gpt-6-luna) | 3,463/3,507 (98.7%) |
| D | gold Qasper `full_text` section names (`:::` = nesting), plus "Abstract": oracle | 2,850/3,105 (91.8%) |
| E | Section Anything Quick check (`llm_review`, gpt-6-luna) | 3,409/3,435 (99.2%) |

- **Chunks (B–E).** Chunks never cross an anchored heading. Each starts with its section path
  (`[Section: Model > Response Generation]`) and uses the same size cap and overlap as A.
- **Anchoring.** One title matcher serves every arm and uses no page numbers (gold has none).
  It drops leading numbers from both sides. The heading must start a line and end within
  4 lines, or be a run-in heading followed by `.`, `:` or a dash. When a title repeats, the
  first match after the previous heading wins.
- **Why D anchors less.** Most of the 8% of gold headings that do not anchor are run-in
  headings with no punctuation ("Datasets The training sets…"). The rest were renamed between
  paper versions or are missing from the PDF.

**Shared settings.**
- Embeddings: text-embedding-3-small, cosine similarity on the question.
- Retrieval: chunks are taken greedily, best first, until the context budget is full.
- Context budgets: 6,000 tokens as planned, plus 2,400, because 6,000 tokens is most of a
  Qasper paper. Evidence recall was also checked at 1,200 tokens, retrieval only.
- Answer model and prompt: gpt-6-luna, one call per arm, budget and question, all at default
  settings. The prompt says: answer concisely, preferably copying from the excerpts; answer
  yes/no questions with "Yes" or "No"; answer "Unanswerable" if the excerpts do not contain the
  answer.

**Metrics.**
- **Answer F1:** the official Qasper evaluator's token F1, max over annotators. Our numbers
  match the evaluator script to four decimals.
- **Evidence recall:** does the retrieved context contain any gold evidence paragraph (text or
  `FLOAT SELECTED` captions) of any annotator? A paragraph counts if its normalized text is a
  substring of the context, or if 60% or more of its word trigrams appear there. Qasper's
  `BIBREF`/`INLINEFORM`… placeholders are removed first.
  - Checks: 1,779 of 1,893 gold paragraphs (94%) are found in our full text, so evidence recall
    covers the 653 questions with at least one paragraph found. In a spot check, no paragraph
    matched a different paper.
- **Statistics:**
  - 95% CIs: paired bootstrap that resamples papers (10,000 draws), because questions about the
    same paper are correlated.
  - Tests: Wilcoxon signed-rank on per-question F1 differences (checked against scipy) and an
    exact McNemar test on evidence hits.
  - No correction for multiple comparisons.

## Results: all 200 papers, 707 questions (arms A, C, D, E)

### Answer F1 (official evaluator)

| Arm | @6,000 tokens | @2,400 tokens |
|---|---|---|
| A fixed chunks | 0.541 [0.515, 0.567] | 0.511 [0.482, 0.539] |
| C SA Standard | 0.534 [0.506, 0.562] | 0.513 [0.484, 0.541] |
| D gold headings | 0.535 [0.508, 0.562] | 0.513 [0.487, 0.540] |
| E SA Quick check | 0.537 [0.510, 0.564] | 0.514 [0.485, 0.541] |

| Paired difference | @6,000 | @2,400 |
|---|---|---|
| C − A | −0.007 [−0.030, +0.015], Wilcoxon p = 0.28 | +0.002 [−0.023, +0.026], p = 0.83 |
| D − C | +0.002 [−0.019, +0.022], p = 0.75 | +0.001 [−0.020, +0.021], p = 0.40 |
| E − C | +0.003 [−0.018, +0.024], p = 0.88 | +0.001 [−0.016, +0.017], p = 0.56 |

**By answer type** (fixed majority type per question; mean F1):

| Type | n | @6,000: A / C / D / E | @2,400: A / C / D / E |
|---|---|---|---|
| extractive | 367 | .543 / .540 / .546 / .547 | .485 / .493 / .514 / .503 |
| abstractive | 169 | .425 / .424 / .419 / .415 | .395 / .403 / .406 / .408 |
| yes/no | 107 | .697 / .646 / .706 / .671 | .639 / .663 / .618 / .629 |
| unanswerable | 64 | .581 / .604 / .498 / .579 | .751 / .662 / .619 / .662 |

- No C − A difference by type reaches p < 0.05 except unanswerable at 2,400 (p = 0.03). In that
  case A, which retrieves less, says "Unanswerable" more often (19% of all answers vs 15% for C).
  That helps on truly unanswerable questions and hurts on the rest.
- D − C on unanswerable questions at 6,000 has p = 0.01 (64 questions).
- With about 20 tests in these tables, a few p-values under 0.05 are expected by chance.

### Evidence recall (653 questions with locatable evidence)

| Arm | @6,000 | @2,400 | @1,200 |
|---|---|---|---|
| A fixed 4,800 chars | 0.933 [0.912, 0.952] | 0.703 [0.665, 0.741] | 0.496 [0.456, 0.536] |
| A2 fixed 1,900 chars (control) | 0.960 [0.943, 0.976] | 0.775 [0.744, 0.806] | 0.562 [0.524, 0.600] |
| C0 = C without the path prefix (control) | 0.959 [0.943, 0.973] | 0.809 [0.776, 0.841] | 0.637 [0.595, 0.678] |
| C SA Standard | 0.965 [0.951, 0.978] | 0.799 [0.765, 0.833] | 0.649 [0.607, 0.692] |
| D gold headings | 0.962 [0.948, 0.975] | 0.796 [0.763, 0.829] | 0.639 [0.596, 0.681] |
| E SA Quick check | 0.966 [0.953, 0.979] | 0.812 [0.778, 0.844] | 0.651 [0.608, 0.693] |

| Paired difference (McNemar) | @6,000 | @2,400 | @1,200 |
|---|---|---|---|
| C − A | +0.032 [+0.014, +0.051], 32 vs 11, p = 0.002 | +0.096 [+0.055, +0.137], 115 vs 52, p < 0.001 | +0.153 [+0.101, +0.204], p < 0.001 |
| D − C | −0.003, p = 0.75 | −0.003, p = 0.88 | −0.011, p = 0.47 |
| E − C | +0.002, p = 1 | +0.012 [+0.003, +0.023], p = 0.04 | +0.002, p = 1 |
| A2 − A (chunk size only) | +0.028, p = 0.02 | +0.072, p < 0.001 | +0.066, p = 0.003 |
| C − A2 (headings at equal size) | +0.005, p = 0.74 | +0.025 [−0.012, +0.059], p = 0.18 | +0.087 [+0.045, +0.129], p < 0.001 |
| C − C0 (path prefix only) | +0.006, p = 0.34 | −0.009, p = 0.36 | +0.012, p = 0.32 |

Results are the same when only text evidence is counted (`FLOAT SELECTED` excluded).

### Why better retrieval does not show up in answer F1 (C − A at 2,400 tokens)

| Questions | n | Mean F1 change, C − A |
|---|---|---|
| C retrieved the evidence, A did not | 115 | **+0.164** (0.547 vs 0.384, p < 0.001) |
| A retrieved it, C did not | 52 | −0.089 (0.402 vs 0.490, p = 0.03) |
| both retrieved it | 407 | −0.015 |
| neither retrieved it | 79 | −0.029 |
| no gold evidence found in our text (mostly unanswerable) | 54 | −0.084 |
| all | 707 | +0.002 |

The retrieval gain does turn into better answers where it happens. But it affects only about
one question in six. Small losses on the other questions cancel it out. Most of those losses
are answer-model noise, and some come from saying "Unanswerable" less often.

**Noise floor.** We asked arm A's 2,400-token excerpts a second time: same excerpts, prompt and
model.
- F1 went from 0.511 to 0.496 (−0.015 [−0.030, +0.000]).
- 288 of the 707 questions changed F1 (125 up, 163 down). Only 328 answers were word-for-word
  identical.
- Wilcoxon p = 0.03 even though nothing changed. Single-run answer F1 differences of 1–2 points
  are therefore not interpretable here.

## Results: the 52 papers with a Docling run (178 questions, all five arms)

We stopped the Docling run after 52 papers because our laptop was short of memory (see Costs and
what went wrong). The Docling arm is sorted by arXiv id, so these are the **oldest** papers in the
sample (2016–2018, ids 1602–1803), not a random subset.

| Arm | Answer F1 @6,000 | Answer F1 @2,400 | Evidence recall @6,000 / @2,400 / @1,200 (n = 164) |
|---|---|---|---|
| A fixed chunks | 0.547 | 0.522 | 0.915 / 0.640 / 0.451 |
| B Docling | 0.562 | 0.508 | 0.957 / 0.750 / 0.610 |
| C SA Standard | 0.565 | 0.525 | 0.963 / 0.720 / 0.610 |
| D gold headings | 0.566 | 0.532 | 0.963 / 0.744 / 0.579 |
| E SA Quick check | 0.554 | 0.506 | 0.963 / 0.738 / 0.591 |

- **C − B, answer F1:** +0.003 [−0.027, +0.034] at 6,000 (p = 0.59) and +0.017 [−0.024, +0.057]
  at 2,400 (p = 0.66).
- **C − B, evidence recall:** +0.006 at 6,000, −0.030 at 2,400 (C 0 vs B 5 discordant,
  p = 0.06), 0.000 at 1,200.
- **D − C, answer F1:** +0.000 at 6,000 and +0.007 at 2,400 (both n.s.).
- **Power:** with 178 questions, this subset can only detect differences of about 4–5 F1 points.

**Heading agreement with gold section names** (same 52 papers; titles matched after dropping
numbers; document title, Abstract and References left out):

| Arm | Precision | Recall | F1 | Same parent as gold |
|---|---|---|---|---|
| B Docling | 0.756 | 0.977 | 0.852 | 0.416 |
| C SA Standard | 0.850 | 0.953 | 0.899 | 0.485 |
| E SA Quick check | 0.848 | 0.972 | 0.906 | 0.483 |

- On these 52 papers our headings have higher precision against gold than Docling's (0.850 vs
  0.756: fewer extra headings), Docling's have higher recall (0.977 vs 0.953), and our nesting
  matches gold a little more often (0.485 vs 0.416).
- Parent agreement is low for every arm. Qasper's names often leave out parent sections that the
  PDF prints ("Sexist Tweets" without "3 Datasets"), so this column understates everyone.
- Even so, none of this made a difference to retrieval or answers.

## Interpretation

1. **For short, well-formatted papers, heading quality is not the bottleneck.** Arms with
   clearly different heading accuracy perform the same, from Docling (F1 0.85 against gold) to
   ours (0.90) to the gold names. The only clear effect comes from having section boundaries at
   all: chunks then follow the paper's topics, so a tight budget is spent on fewer off-topic
   lines. Most of that effect can also be had by simply using smaller fixed chunks. Qasper
   papers are 2016–2020 LaTeX arXiv papers, the easiest case for every heading detector.
2. **Retrieval gains are real but do not move Qasper answer F1.** The context budget covers
   most of the paper, answer F1 is noisy (±1.5 points between identical runs), and token F1
   rewards answer style as much as content. The effect we can measure is too small to show
   through.
3. **What this does not show.** It says nothing about long documents (filings, manuals,
   textbooks), where a budget covers a small fraction of the text and the heading tree is deep.
   It also says nothing about documents where heading detection (Docling's, ours or plain rules)
   makes many mistakes. Those are the cases where heading quality could matter, and they are where
   the next test should go.
4. **For claims.** We cannot claim "better headings give better answers" from Qasper. We can
   claim "section-aware chunks retrieve the evidence more often at small budgets (+10 to
   +15 points); on Qasper this does not change answer F1".

## Costs

| Item | Cost |
|---|---|
| Local relay (cap $8): gpt-6-luna answers, 6,719 calls (this includes a 100-call smoke test and the 707-call noise rerun) | $2.958 |
| Local relay: text-embedding-3-small, 221 calls (all arms and both controls) | $0.264 |
| Sectioning pipeline, direct to OpenAI (cap $1.5): Standard $0.414 + Quick check $0.154 | $0.568 |
| **Total** | **$3.79** |

- One HTTP 429 response was retried.
- The relay bills the 26M prompt tokens that OpenAI reported as cache writes at the ordinary
  input price. If cache writes cost more, the true total is somewhat higher, but still far under
  the cap.

**What went wrong.**
- **The Docling run was not completed.** This was our laptop's memory limit, not a Docling error.
  The laptop's swap was already 13.3 GB at the start. It reached 16–17 GB during the run, from
  other apps and from another job's Docling run under the shared lock.
  - Each Docling start added about 2 GB of swap within seconds. The watchdog stopped it twice,
    after which `docling_batches.sh` refused to start while swap was over 14.8 GB.
  - We stopped retrying after 52 papers, so arm B covers only those 52.
- **Two of our own runs were also stopped by the watchdog.** Extraction/sectioning and the RAG
  run were each stopped once by its system-wide swap-growth rule; both resumed from their caches
  with nothing lost.

## Limitations

- **One answer run per arm.** Rerunning the same excerpts moved F1 by 1.5 points. Several runs per
  arm, or a deterministic answer model, would be needed to see small effects.
- **The planned 6,000-token budget is near the whole paper** for most Qasper papers. That is
  why we added the 2,400 and 1,200 budgets.
- **The arm B subset is small and not random:** 52 papers, the oldest in the sample.
- **The gold "oracle" is weakened:**
  - 8% of gold headings did not anchor on our text.
  - Qasper's section names come from its own parse, sometimes of a different paper version, and
    often leave out parent sections.
- **Our extraction sometimes misorders two-column text.** Example: §6 is placed before §5.2 in
  1808.07231. It is the same text in every arm, but it can split sections oddly.
- **Evidence matching is approximate** (substring or 60% of trigrams).
- **The current arXiv PDF versions may differ** from the versions Qasper annotated.
- **This is vector retrieval only:** no reranking and no graph mode (LightRAG).

## Files (`<workspace>/.tmp/qasper-rag/`)

- `step0_data.py`: sample and PDF download (`selection.json`).
- `step1_ours.py`: our extraction plus Standard and Quick check (`out/ext`, `out/sa_llm_text`,
  `out/sa_llm_review`, `out/pipeline_costs.jsonl`).
- `step2_docling.sh`: Docling under the shared lock (`out/docling`).
- `step3_rag.py`: anchoring, chunking, embeddings, retrieval, answers.
  - `out/rag/retrieval.jsonl`: per arm and question.
  - `out/rag/answers.jsonl`: per arm, budget and question, with the answer, references and F1.
- `step4_report.py`: statistics (`out/rag/report.txt`, `out/rag/report.json`).
- `step5_controls.py`: the A2 and C0 controls (`out/rag/controls.txt`,
  `out/rag/retrieval_controls.jsonl`).
- `step6_noise.py`: the noise rerun (`out/rag/noise.txt`, `out/rag/answers_noise.jsonl`).
- `qasper_evaluator.py`: the official evaluator, copied unchanged after review.
- `usage.jsonl`: the relay's per-call cost log.
