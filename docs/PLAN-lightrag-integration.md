# Plan: Section Anything inside LightRAG (first step)

Researched 20 Oct 2026, read-only. Nothing was posted, installed or run (no local models).
Verified against LightRAG `main` @ `aaebfe1` (14 Oct 2026, version 1.5.8, not yet released),
cloned at `<workspace>/.tmp/repos/LightRAG`, and against the
`lightrag-hku` 1.5.7 wheel (PyPI latest, 2 Sep 2026). Code paths below are relative to that clone.

## 0. What the code says (checks of earlier notes)

| Claim | Status | Evidence |
|---|---|---|
| RAG-Anything is merged into LightRAG | Yes | README news "[2026.05] Merge RagAnything into LightRAG" |
| Parser plugins via `lightrag.parsers` entry point | Yes, in 1.5.7 and main | `lightrag/parser/plugins.py:30`, `docs/ThirdPartyParser.md` |
| Chunker plugins via `lightrag.chunkers` | **Main only**, not in 1.5.7 | `lightrag/chunker/plugins.py:19`; absent from the 1.5.7 wheel |
| P chunker splits on `heading`/`level`/`parent_headings` | Yes | `lightrag/chunker/paragraph_semantic.py:2057`, `docs/ParagraphSemanticChunking.md` |
| `ENABLE_CONTENT_HEADINGS` | Yes, **default true** | `lightrag/lightrag.py:755`, `env.example:250` |
| SDK `chunking_func`, `ainsert_custom_chunks`, `ainsert_custom_kg` | Yes. Custom chunks is called "deprecated"; custom KG is outside the recovery guarantee | `lightrag/lightrag.py:838, 2394, 4340` |
| #4226 headings "flat / skip levels" | Narrower: MinerU/Docling IR builders put **non-ancestors in `parent_headings`** when levels skip or start at 2. Open. Fix PR #4227 open, 0 comments, by `hardness1020` (not the owner's `Omniwot`) | `lightrag/parser/external/mineru/ir_builder.py:325`, `.../docling/ir_builder.py:357` |
| Maintainer invites third-party parsers (#3131) | Yes: the sidecar format is "specifically designed to encourage third-party extension of the Parser"; also recommends the API over the SDK | [#3131](https://github.com/HKUDS/LightRAG/issues/3131) |

**New findings that shape the plan:**
- **PDFs get no headings by default.** The default is `LIGHTRAG_PARSER=*:native-teP,*:legacy-R`
  (`env.example:389`). `native` has no PDF support, so PDFs go to `legacy-R` (plain text, no
  sidecar) unless a MinerU or Docling service is set up. LLM `smart_heading` exists for DOCX only.
- **Third-party engines cannot take per-file params.** `_ENGINE_PARAM_SPECS` is hard-coded
  (`lightrag/parser/param_schema.py:360`), so `sectionany(mode=quick)` is impossible without
  an upstream change. Workaround: one engine name per dial position.
- **P treats every `\n` line as a paragraph** (`_block_to_paragraphs`, `paragraph_semantic.py:178`),
  and long blocks split at short paragraphs (≤100 chars). Raw PDF lines must be reflowed into
  paragraphs first.
- **Embeddings see chunk `content` only.** `chunks_vdb` meta fields are `full_doc_id, content,
  file_path` (`lightrag/lightrag.py:1892`), so headings never reach the vector index except the
  `# heading` line at the top of a block's first chunk.
- PyPI name `lightrag-section-anything` is free (404 on 20 Oct).

## 1. First step: `lightrag-section-anything`, a parser plugin

**Why a parser first:** it works on released 1.5.7, needs no upstream PR, and P, the extraction
breadcrumb and `content_headings` all use its headings for free. It fills the PDF gap left by
the default config and works without a MinerU or Docling service.

### 1.1 Package and registration

- Repo `section-anything` → new folder `packages/lightrag-section-anything/` (Apache-2.0).
- Move `backend/app/sectioning/{extract,markers,structure,pipeline,llm}.py` and `strategies/`
  into an importable core. Only `llm.py` (`settings`) and `jobs.py` (database) depend on the app;
  replace `settings` with a small config dataclass.
- Dependencies: `lightrag-hku>=1.5.7,<1.7`, `pdfplumber`, `pypdfium2`, `rapidfuzz`, `openai`,
  `pydantic>=2`, `httpx`. No PyMuPDF (AGPL).

```toml
[project.entry-points."lightrag.parsers"]
sectionany = "lightrag_section_anything.plugin:register_parsers"
# Phase 2, needs LightRAG >= 1.5.8:
[project.entry-points."lightrag.chunkers"]
sectionany_p = "lightrag_section_anything.plugin:register_chunkers"
```

```python
# lightrag_section_anything/plugin.py: import-cheap; no implementation imports here
import os
from lightrag.parser.registry import ParserSpec, register_parser

def register_parsers() -> None:
    impl = "lightrag_section_anything.parser:{}"
    register_parser(ParserSpec(               # mode from SECTIONANY_MODE (default free)
        engine_name="sectionany", impl=impl.format("SectionAnyParser"),
        suffixes=frozenset({"pdf"}), queue_group="sectionany",
        concurrency=int(os.getenv("MAX_PARALLEL_PARSE_SECTIONANY", "2"))))  # only one spec per group may set this
    for mode, cls, ready, need in [
        ("free", "FreeParser", lambda: True, lambda: ""),
        ("quick", "QuickParser", _has_key, lambda: "SECTIONANY_API_KEY or OPENAI_API_KEY"),
        ("standard", "StandardParser", _has_key, lambda: "SECTIONANY_API_KEY or OPENAI_API_KEY"),
        ("local", "LocalParser", lambda: bool(os.getenv("SECTIONANY_LOCAL_MODEL")), lambda: "SECTIONANY_LOCAL_MODEL"),
    ]:
        register_parser(ParserSpec(engine_name=f"sectionany_{mode}", impl=impl.format(cls),
            suffixes=frozenset({"pdf"}), queue_group="sectionany",
            endpoint_configured=ready, endpoint_requirement=need))  # env-only closures, no network
```

- Engine names must not contain `-`, which separates options in hints. Underscores are fine.
- Routing skips an engine whose `endpoint_configured()` is false. A rule chain therefore falls
  back cleanly: `LIGHTRAG_PARSER=pdf:sectionany_quick-P,pdf:sectionany-P,*:native-teP,*:legacy-R`.
- Per file: `contract.[sectionany_standard-P].pdf`.
- SDK: `from lightrag.parser.plugins import load_third_party_parsers; load_third_party_parsers()`.
  The maintainer recommends the server API over the SDK.

### 1.2 Parser class (contract from `lightrag/parser/native_base.py`)

Subclass `NativeParserBase`. It already handles cancellation, rollback, `write_sidecar`,
`full_docs` persistence and archiving.

```python
class SectionAnyParser(NativeParserBase):
    engine_name = "sectionany"
    def validate_source_blocking(self, source, file_path): ...  # page cap, encrypted, text layer
    def extract(self, source, *, parsed_dir, asset_dir, base_name, runtime=None):
        # runs in LightRAG's parser thread: pdfplumber extract -> sectioning (asyncio.run of our
        # async LLM calls; check runtime.cancel_events between calls) -> blocks
        return blocks, warnings, metadata
    def build_ir(self, blocks, *, document_name, asset_dir_name, metadata) -> IRDoc: ...
    def finalize_parse_warnings(self, warnings, metadata, *, parsed_dir, base_name, source,
                                i4_cache_disabled): ...  # write <base>.sectionany.json, return cost summary
```

- Failure contract: raise on empty or no-text PDFs. Only that document becomes FAILED.
- Scanned PDFs: raise `"no text layer; re-upload as name.[mineru-P].pdf"`.
- Thread pool caveat: `extract` runs on the rag's native pool (`max_parallel_parse_native`=5).
  Long LLM parses hold threads that DOCX parsing also uses. Keep our concurrency at 1–2.

### 1.3 Text extraction: ours first, MinerU/Docling re-level later

- **v1 uses our pdfplumber extraction.** It runs locally on CPU with no service. Quick check
  needs our typography (size, bold) anyway, and the line boxes give positions.
- Required for P:
  - **Reflow** lines into paragraphs: one paragraph per line, de-hyphenated.
  - Render the heading line as `#`×level + printed text (helper:
    `lightrag/parser/_markdown.py:render_heading_line`).
  - Drop running headers and footers (`structure.furniture_of`). MinerU and Docling drop them
    too.
- Not in v1:
  - Tables (they arrive as text lines). Phase 2: pdfplumber tables → `<table format="json">`.
  - Images and equations, so the `i`/`e`/`t` flags do nothing.
  - OCR.
- **Phase 2: `sectionany_mineru` / `sectionany_docling`.**
  - Subclass LightRAG's MinerU/Docling parser.
  - Keep their text, tables and images. Replace only the heading decisions and levels (our
    review over their heading items plus pdfplumber typography).
  - Rebuild `parent_headings` with a level-keyed stack, which also avoids #4226.
  - Uses internal classes (`lightrag/parser/external/*/parser.py`), so pin versions.
  - Needed as the clean evaluation arm (same text, only headings change). Build only if the
    Stage 1 evaluation (§4) shows gains beyond 10-Ks: the pilot tied MinerU there.

### 1.4 Mapping sections → `.blocks.jsonl` (spec: `docs/LightRAGSidecarFormat.md`)

| Our section field | Sidecar |
|---|---|
| `number` + `title` (as printed) | `heading`, also the first line of `content` as `## …` |
| `level` (1–8) | `level`, unchanged (skips allowed) |
| ancestors by level-keyed stack | `parent_headings` (ancestors only) |
| `start`…`end` (segment) | block `content`: reflowed paragraphs, no overlap between blocks |
| Front matter | `level` 0, `heading` "", `session_type` "preface" |
| TOC lines (`structure.toc_of`) | separate block, `session_type` "TOC" |
| `title_from_text=false` (Standard, headingless text) | kept only if `SECTIONANY_SYNTHETIC_TITLES=true`; otherwise merged into the previous block |
| `page_start..page_end` + line boxes | `positions`: one `bbox` per page, union of line boxes |
| flags, offsets, cost | `<base>.sectionany.json` (our audit file, like `smart_audit.json`) |

- Positions use the same convention as the Docling adapter:
  - meta `bbox_attributes: {"origin": "LEFTBOTTOM"}`, PDF points;
  - `anchor` = 1-based physical page as a string;
  - `range = [x0, y1, x1, y0]` (left, top, right, bottom). Our lines already store PDF user
    space with the mediabox origin.
- `blockid`, ids and `document_hash` are computed by LightRAG's writer. We fill
  `IRDoc(document_format="pdf", doc_title=<PDF title or first L1>, split_option={...})`.

```jsonl
{"type":"meta","format":"lightrag","version":"1.0","document_name":"acme-10k-2024.pdf","document_format":"pdf","blocks":212,"doc_id":"doc-…","parse_engine":"sectionany_quick","doc_title":"ACME Corp Form 10-K 2024","split_option":{"engine_version":"0.1.0","mode":"quick","model":"gpt-6-luna","cost_usd":0.0042,"llm_calls":1,"sections":211,"flagged":3},"bbox_attributes":{"origin":"LEFTBOTTOM"},"…":"other meta fields written by LightRAG"}
{"type":"content","blockid":"<md5 by writer>","format":"plain_text","content":"## Item 7A. Quantitative and Qualitative Disclosures About Market Risk\nWe are exposed to market risks, including changes in interest rates …\nInterest rate risk. Our investment portfolio …","heading":"Item 7A. Quantitative and Qualitative Disclosures About Market Risk","parent_headings":["PART II"],"level":2,"session_type":"body","table_slice":"none","positions":[{"type":"bbox","anchor":"41","range":[72.0,702.4,540.1,96.3]},{"type":"bbox","anchor":"42","range":[72.0,720.0,540.1,410.8]}]}
```

### 1.5 The dial: config, budget caps and cost reporting

| Mode | Engine | Runs | Heading F1 (23 docs) | Cost / 1,000 pp | Speed | Text sent out |
|---|---|---|---|---|---|---|
| free | `sectionany_free` | rules: bookmarks, TOC, typography | 0.800 | $0 | extraction-bound | none |
| quick | `sectionany_quick` | rules + `gpt-6-luna` reviews candidate lines | 0.911 | ~$0.04 | ~0.5 s/page | candidate lines + 70-char peek |
| standard | `sectionany_standard` | `gpt-6.1-sol` reads all lines | 0.920 | ~$2.33 | ~1.4 s/page | full text |
| local:&lt;model&gt; | `sectionany_local` | quick-style review on Ollama | not measured | $0 | est. 0.5–5 s/page (§3) | none |

Environment variables (read at parse time, except concurrency):
- `SECTIONANY_MODE=free|quick|standard|local:<ollama model>`: what engine `sectionany` does.
  The text after `local:` is the full model tag, including colons.
- `SECTIONANY_API_KEY` (falls back to `OPENAI_API_KEY`), `SECTIONANY_BASE_URL` (any
  OpenAI-compatible endpoint with JSON-schema outputs), `SECTIONANY_QUICK_MODEL=gpt-6-luna`,
  `SECTIONANY_STANDARD_MODEL=gpt-6-luna` (the default since library 0.1.3; was gpt-6.1-sol,
  which the table above used), `SECTIONANY_PRICES_JSON` (USD per 1M tokens).
- `SECTIONANY_MAX_USD_PER_DOC=0.50`, `SECTIONANY_BUDGET_USD` (total across documents; ledger
  `<WORKING_DIR>/sectionany_ledger.jsonl`, append-only with a file lock).
- `SECTIONANY_OVER_BUDGET=downgrade|fail`.
  - Default `downgrade`: standard → quick → free when the pre-run estimate
    (`Strategy.estimate()` × prices) exceeds the per-document cap or the remaining budget.
  - Hitting `CostCapExceeded` mid-run gives free sections for that document plus a warning.
  - `fail` matches the app's "blocked, no override" rule.
- A model with no price may only run with a token cap (`SECTIONANY_MAX_TOKENS_PER_DOC`).
- `SECTIONANY_MAX_PAGES=500`, `SECTIONANY_SYNTHETIC_TITLES=false`,
  `SECTIONANY_BLOCK_MAX_LEVEL` (emit blocks only for levels ≤ N; this sets P's granularity),
  `SECTIONANY_STORE_PROMPTS=false`.
- Local settings: see §3.

Cost reporting (no upstream change needed):
- `parse_warnings` is mirrored verbatim into `doc_status.metadata`. Keys: `sectionany_mode`,
  `_model`, `_cost_usd`, `_calls`, `_tokens_in`, `_tokens_out`, `_seconds`, `_sections`,
  `_flagged`, `_downgraded`.
- Also `meta.split_option`, `<base>.sectionany.json`, one INFO log line per document, and
  `python -m lightrag_section_anything.report <INPUT_DIR>` to total costs.

### 1.6 Tests (copy LightRAG's patterns)

- Fake rag: `_FakeRag` in `tests/parser/test_legacy_parser.py`.
- Registry cleanup: `tests/parser/test_registry.py`. Entry points: `tests/parser/test_plugins.py`.
- Sidecar invariants:
  - blocks cover the text with no overlap;
  - `parent_headings` contains ancestors only;
  - `chunking_by_paragraph_semantic` runs without falling back to R.
- Debug CLI: `python -m lightrag.parser.cli x.pdf --engine sectionany`.
- Golden tests on 3 public PDFs. CI against `lightrag-hku==1.5.7` and `main`.
- Use a fresh venv or `uv`, never conda base.

## 2. How LightRAG uses headings, and what our sections add

| Use | Where | Plugin alone? |
|---|---|---|
| P: one basic block per heading; the chunker never detects headings itself | `paragraph_semantic.py`, doc §3.1 | Yes |
| P HeadingGlue: a body-less heading joins its strictly deeper child | doc §3.5 | Yes (needs correct levels) |
| P LevelMerge: siblings merge only with **identical** `parent_headings`; a shallow block absorbs only its descendants; no overlap across blocks | doc §3.6–3.7 | Yes. This already means "never cross section boundaries" when levels are right; #4226 shows what wrong parents do |
| Extraction prompt `---Section Context---`: full path (parents + own), 80 chars/level, 256 tokens | `operate.py:4120`, `prompt.py:51` | Yes, automatic |
| Answer prompt `content_headings`: **parent path only** (on by default) | `operate.py:5719`, `prompt.py:455`, `chunk_schema.py:148` | Yes, automatic |
| P(drop_rf) drops reference sections by heading name | `paragraph_semantic.py:248` | Yes, better with accurate headings |
| Section-path prefix in the **embedding** | `chunks_vdb` embeds `content` only | Chunker plugin (≥1.5.8, `C` + `CUSTOM_CHUNKER=sectionany_p`, wraps P and prefixes the path), **or** upstream option to embed `path + content` with stored content unchanged (`docs/ThirdPartyChunker.md`: no transform hook for F/R/V/P yet) |
| Per-section summaries | none | SDK: section entities with summary descriptions via `ainsert_custom_kg`. Server: REST `/graph/entity/create` with `source_id` = chunk ids. Both bypass purge/recovery anchors, so clean deletion needs upstream work. Rough cost ~$0.1 per 1,000 pages with luna (estimate) |
| Section nodes and edges (section→subsection, entity→section) | none | Same paths as summaries; gate behind the §4 evaluation (risk: noise in keyword retrieval) |

Chunker plugin caveat: `CUSTOM_CHUNKER` is instance-wide and also replaces the default for
inserts with no selector. It must fall back to `chunking_by_token_size` when there is no
sidecar (`context.sidecar_location` is None).

## 3. Local-LLM option (research only; nothing run)

- **Realistic on a 16 GB M4:** Quick-style review only. Standard reads 120k-char windows
  (~33k tokens). An 8B model plus a 32k KV cache is about 5.2 GB + ~4.7 GB (my estimate for
  Qwen3-8B), which goes past the ~10 GiB Metal budget and swaps.
- **Models:**
  - Default `qwen3:4b`: the 4b-instruct-2507 build, Q4_K_M, 2.5 GB, non-thinking.
  - Step up to `qwen3:8b` (5.2 GB) with thinking off.
  - Avoid `gemma4:12b` (7.7–8.0 GB) and `gemma4:e4b` (6.6–9.5 GB) for long runs. Granite
    looped in our test.
  - Sizes from [ollama.com/library/qwen3/tags](https://ollama.com/library/qwen3/tags) and
    [gemma4/tags](https://ollama.com/library/gemma4/tags).
- **Use Ollama's native `/api/chat`, not `/v1`.**
  - Below 24 GiB VRAM the default context is **4k**
    ([docs.ollama.com/context-length](https://docs.ollama.com/context-length)), and the
    OpenAI-compatible endpoint ignores `num_ctx`. Truncation is silent
    ([particula.tech](https://particula.tech/blog/ollama-num-ctx-silent-prompt-truncation)).
  - Our `llm.py` uses `/v1`, which is why the earlier test needed a custom
    `qwen3-8b-16k` model.
  - Send `format=<JSON schema>`, `options={num_ctx: 8192, temperature: 0, num_predict: cap}`,
    `think: false` and `keep_alive: 0`.
- **Make local calls cheap:**
  - Batches of 60 candidates (300 in the cloud) fit 8k context.
  - Compact output: only `[id, level]` for kept headings, with titles taken from the line text.
  - Decode speed is the bottleneck.
- **Speed estimates:**
  - Published llama.cpp numbers for an M4 with a 10-core GPU, 7B Q4_0: prompt 221 tok/s,
    generation 24 tok/s ([discussion #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)).
  - Quick check needs about 80 input and 80 output tokens per page (implied by $0.04 per
    1,000 pages at luna prices).
  - Current schema: about 4–5 s/page for 8B and 2–3 s/page for 4B.
  - Compact schema: about 1 s/page (8B) and 0.5 s/page (4B), so 100 pages take 1–8 minutes.
- **Quality:**
  - No published heading benchmark exists for general 4–8B models.
  - [md-reheader](https://friendli.ai/models/joelbarmettler/md-reheader), a Qwen3-0.6B
    fine-tune (Apache-2.0), only re-levels markdown headings. Its authors report 80.6%
    per-heading accuracy and 56.1% exact document match, falling to 32% at depth 4.
  - Expect local to score below luna. Measure on 2–3 documents only, with the owner's OK and
    a time limit, or on a remote or rented GPU via `SECTIONANY_OLLAMA_HOST`.
- **Safety caps:**
  - `SECTIONANY_LOCAL_MAX_PAGES=150`; above that, free plus a warning.
  - `SECTIONANY_LOCAL_MAX_SECONDS=600` per document; past that, fall back to free.
  - 120 s per call, a `num_predict` cap and a repetition check against runaway loops.
  - Concurrency 1 and `keep_alive: 0`.
  - `SECTIONANY_LOCAL_COOLDOWN_SECONDS=30` between documents.
  - Optional check of `pmset -g therm` (unverified on M4).
- **When to recommend cloud instead:**
  - More than 150 pages, or batch ingestion.
  - Legislation, manuals and headingless text, which need Standard.
  - Whenever the laptop is needed for other work.
  - Quick costs ~$0.40 per 10,000 pages, so local only pays off for confidential or offline
    documents.
  - LightRAG's own extraction recommends 30B+ models with 32k context, so on 16 GB the
    realistic mix is local sectioning plus cloud extraction.

## 4. Evaluation that would convince LightRAG maintainers

**Published evidence first** (workspace rule):
- [LongDocBench](https://arxiv.org/abs/2608.15064) (Aug 2026; 85 documents, 2,582 pages;
  financial reports, textbooks, papers):
  - human-verified TOC alone lifts QA from 32.98% to 45.95% over fixed chunks + BM25;
  - parsers recover TOCs poorly (TEDS ≤ 0.49; MinerU2.5-Pro 0.44).
- No study varies the heading source inside LightRAG's P pipeline, so our own test is
  justified.
- Our FinanceBench pilot used its own vector harness, not LightRAG, and its differences were
  not significant (p 0.07–0.23).

**Harness:**
- Unmodified LightRAG Server at a pinned commit, one `WORKSPACE` per arm.
- The same LLM, embeddings, `MAX_TOTAL_TOKENS` and query parameters in every arm.
- Modes: `naive` (vector) first, then `mix` (graph).
- Publish each arm's `.env`, the scripts, sidecars, chunks and raw answers.

**Arms** (`LIGHTRAG_PARSER` for `.pdf`):

| Arm | Rule | Purpose |
|---|---|---|
| A0 | `legacy-R` | today's default |
| A1 | `legacy-R(chunk_ts=2000)` | controls for P's larger chunks |
| B1 | `mineru-P`, #4227 applied | recommended config (we don't benchmark against a known bug) |
| B2 | `mineru-P` + MinerU `title_aided` | LightRAG docs recommend it for P |
| C | `docling-P` | other built-in |
| D / E / F | `sectionany_free-P` / `_quick-P` / `_standard-P` | the dial |
| G | gold headings (LongDocBench verified TOC) | upper bound |
| H (phase 2) | MinerU text + our headings | isolates the heading effect |

**Data** (where heading quality differs, not only 10-Ks):
- [MMLongBench-Doc](https://github.com/mayubo2333/MMLongBench-Doc): 135 PDFs of 7 types,
  1,082 questions with evidence pages. Keep text, layout and table questions.
- LongDocBench, if the release link appears.
- FinanceBench, 150 questions, as a control where we expect a tie.
- Optional: our legislation and manuals documents with generated questions, reported
  separately. Our own per-category join suggests the largest heading gaps over MinerU are
  there.

**Metrics:**
- Primary:
  - evidence-page recall in the final context (P chunks map to pages through sidecar
    positions; `legacy-R` chunks through text matching);
  - answer accuracy with the dataset's scorer or a binary judge (shuffled order, ties allowed).
- Secondary:
  - LightRAG's own RAGAS script (`lightrag/evaluation/eval_rag_quality.py`);
  - heading F1/TEDS per document;
  - Spearman correlation between the heading-quality gap and the accuracy gap;
  - chunk statistics; indexing cost and time per arm.
- Statistics: paired McNemar test and bootstrap 95% CIs, broken down by document type.

**Sample size** (80% power, α 0.05, ~25% discordant pairs as in the pilot):

| Detectable gap | Questions needed |
|---|---|
| 10 points | ~200 |
| 7 points | ~400 |
| 5 points | ~800 |

**Stages and costs** (estimates at config prices; state the cost and get the owner's OK
before each paid stage):
1. **Stage 0, ~$0.01.**
   - Plugin tests, plus 3 PDFs through LightRAG with the `!` option (skip the graph).
2. **Stage 1 pilot, ~$10, half a day, light laptop load.**
   - MMLongBench-Doc: 40 documents (~1,900 pages), ~250 questions.
   - Arms A0, A1, B1, D, E; naive mode with `!`.
   - MinerU cloud stays within its free daily quota.
   - Go if E − B1 ≥ 5 points, or there are clear gains by document type.
3. **Stage 2, ~$60–150.**
   - Full sets, all arms, naive plus mix (graph only for A0, B1, E, G).
   - Graph indexing with luna is about $0.6–1 per 1,000 pages per arm (unmeasured).
   - Queries are about $0.01 per question per arm per mode.
   - Standard parsing is ~$2.4 per 1,000 pages.
   - Run Docling and MinerU off the laptop.

## 5. Upstream contributions after the plugin works

1. Publish to PyPI, then publish the evaluation (public repo or Hugging Face dataset). No
   LightRAG PR is needed to ship.
2. **#4226 / #4227:** don't open a competing PR. Review #4227 with independent evidence: count
   our 26 MinerU cloud outputs (`<workspace>/.tmp/mineru-cloud`) that
   have no level-1 heading or skip levels, and show P chunk differences before and after.
3. **Docs PR**: add a "Third-party engines" section to `docs/ThirdPartyParser.md` **and**
   `docs/ThirdPartyParser-zh.md` (docs come in EN/ZH pairs), with install steps and the
   `LIGHTRAG_PARSER` rule. Ask first in a feature-request issue whether they want a list.
4. **RFC issue** (the maintainer runs RFCs with numbered requirements and assigns slices, e.g.
   [#3868](https://github.com/HKUDS/LightRAG/issues/3868)):
   - (a) engine params declared by third-party `ParserSpec`s;
   - (b) a public LLM-bridge API for plugins (today the protected
     `NativeParserBase._build_llm_submit`), including token usage;
   - (c) a `parse_metrics` channel separate from `parse_warnings`;
   - (d) a post-chunk transform hook or an option to embed the heading path;
   - (e) section summaries and nodes with purge-safe anchors.

**Contribution rules** (verified in `.github/CONTRIBUTING.md`, `.github/pull_request_template.md`,
`.pre-commit-config.yaml`, `AGENTS.md`):
- MIT licence. **No CLA or DCO** mentioned anywhere.
- pre-commit runs `trailing-whitespace`, `end-of-file-fixer`, `requirements-txt-fixer`,
  `ruff-format` and `ruff --fix --ignore=E402` (ruff v0.15.17). CI runs it on non-draft PRs.
- Tests: pytest. Run the mirrored subset (`./scripts/test.sh tests/parser`), mock external
  services, and add a regression test for every bug fix.
- `tests/test_docstring_budget.py` enforces: no docstring over 80 lines; no GitHub issue
  numbers in `lightrag/` source (tests may cite them); every `docs/**.md` path the package
  names must exist.
- Commits and comments in English.
- PR template sections: Description, Related Issues, Changes Made, Checklist, Additional
  Notes. AGENTS.md also asks for motivation and "what's broken".
- Issue forms: `bug_report.yml`, `feature_request.yml`.

## 6. Not verified / open risks

- Local speed and quality numbers are estimates from published throughput; no runs.
- Graph-indexing costs are estimates. The MMLongBench text-question count was not checked.
- No release link was found for LongDocBench.
- LightRAG review speed (from the 19 Oct notes) was not re-checked: GitHub API rate limit.
- Not checked: whether the WebUI shows `doc_status.metadata`, and how the writer handles
  literal `{{TBL:` text found in a PDF.
- 1.5.8 release date unknown. The chunker plugin and `ChunkingContext` exist only on main.
- Using `parse_warnings` for cost data stretches its intended meaning (see 4c).
