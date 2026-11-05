# Match failures of the miss audit, and answer keys v2.1

Research tools for track M of the zero-miss plan (research finding F063, 5 Nov 2026). They build on the
miss audit of F056 (`audit.py`, `common.py` and `gold_v2.py` are copies of `corpus/tools/miss_audit/` on
branch `eval/miss-audit`, with `common.py` pointed at this track's folders and able to read keys v2.1). They
read saved extractions, saved runs and answer keys from the owner's local work folders (absolute paths in
`common.py`), so they document how the numbers were made rather than run out of the box. `chain.sh` ran them
from the work folder `.tmp/match-fail/tools/`, where they live beside their outputs.

- `match_audit.py`: the F056 audit for the code on `PYTHONPATH` (`TAG=base` for rc/0.1.7, `TAG=fix` for this
  branch) and answer keys v1, v2 and v2.1 in one pass. Every miss keeps F056's cause and gets a second one:
  a match failure (cause e) only when a prediction starts on the heading's printed line, or when the same
  title (90% plain similarity, or 95% with numbers set aside) was predicted elsewhere and paired with no other
  heading. Otherwise the miss goes down F056's b/c/d path. Side metrics: bare-label key headings matched by a
  label-and-title prediction, and a maximum one-to-one pairing.
- `breakdown.py`: every F056 match failure (keys v2) split into answer-key errors (fixed by rule R3, or
  printed only far from the key page), scorer artifacts, real system errors and misses that are not match
  failures at all.
- `match_report.py`: tables (`audit`) and paired comparisons with bootstrap CIs over documents (`compare`).
- `gold_v21.py`: answer keys v2.1, one more written rule (R3, a heading anchored on a mention moves to its
  printed copy) on top of v2, written beside v1 and v2 with a log of every change. `../../gold-v2.1/` holds
  the corpus sample's v2.1 keys (the rule changes none of them).
- `gapstats.py`: the layout of every same-style join Free's merge stage made on development documents, with
  what the key says (one heading or two); it set the 1.65 line-spacing limit.
- `ablate.py`: the fix with one of its two parts switched off (development documents only). Release 0.1.8 takes
  only the run-on part into the library (its `_merge_wrapped` has no layout test and no `ext` argument), so
  `ablate.py merge` needs branch `fix/match-failures`.
- `page.py`: prints a page's lines with size, weight and position, for checking cases by hand.
- `readoc/`: Free on the READoc development set from saved extractions, and READoc's heading-tree TEDS
  (copied from F045's scripts).
