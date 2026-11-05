"""Track M: every wrapped-line join Free's merge stage makes (rules._merge_wrapped, same size and weight,
no number), with its geometry, and whether the answer key says it is one heading or two.

usage: PYTHONPATH=<src> <venv python> gapstats.py dev|test  -> gaps-<split>.jsonl
"one": a key heading's printed lines hold both lines; "two": a key heading starts at the joined line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/harshal/Desktop/omni/hustles/.tmp/miss-audit")
import common as C  # noqa: E402
from section_anything.docling_input import hints_of  # noqa: E402
from section_anything.strategies import rules as R  # noqa: E402

OUT = Path(__file__).resolve().parent


def joins(ext):
    side = R.side_notes(ext)
    cands = R.candidates(ext)
    hints = hints_of(ext)
    out = []
    last = None
    merged = []
    for ln, num in cands:
        if merged and last is not None:
            prev, pnum, ptext = merged[-1]
            next_line = ln.i > last.i and all(j in side for j in range(last.i + 1, ln.i)) and ln.page == prev.page
            if next_line and not num and ln.size == last.size and ln.bold == last.bold and (
                    hints is None or hints.same_item(last.i, ln.i)):
                out.append((last, ln, "wrapped", prev))
                merged[-1] = (prev, pnum, ptext + "\n" + ln.text)
                last = ln
                continue
            if (next_line and not num and "\n" not in ptext and R.LABEL_ONLY.match(R._label_text(ptext))
                    and not R.LABEL_ONLY.match(R._label_text(ln.text))):
                out.append((last, ln, "label", prev))
                merged[-1] = (prev, R._label_text(ptext), ptext + "\n" + ln.text)
                last = ln
                continue
        merged.append((ln, num, ln.text))
        last = ln
    return out


def main() -> None:
    split = sys.argv[1]
    reg = C.registry()
    rows = C.OUT / "rows-v2"
    dst = OUT / f"gaps-{split}.jsonl"
    recs = []
    for d in reg:
        if (d["split"] == "test") != (split == "test"):
            continue
        p = rows / f"{d['id']}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if "loc" not in r:
            continue
        ext = C.load_ext(d, "nobm")
        starts, spans = {}, []
        for gi, L in enumerate(r["loc"]):
            if L.get("status") == "page" and L.get("lines"):
                starts[L["lines"][0]] = gi
                spans.append(set(L["lines"]))
        for last, ln, kind, first in joins(ext):
            if any(last.i in s and ln.i in s for s in spans):
                key = "one"
            elif ln.i in starts:
                key = "two"
            else:
                key = "?"
            recs.append({"doc": d["id"], "genre": d["genre"], "kind": kind, "key": key, "a": last.text[:80], "b": ln.text[:80],
                         "size": last.size, "bold": last.bold, "dy": round(last.y0 - ln.y0, 1), "gap": round(last.y0 - ln.y1, 1),
                         "dx": round(ln.x0 - last.x0, 1), "a_x1": round(last.x1, 1), "b_x1": round(ln.x1, 1),
                         "a_end": last.text.rstrip()[-1:], "b_label": bool(R.LABEL_ONLY.match(R._label_text(ln.text))),
                         "b_lower": ln.text[:1].islower(), "first_line": first.i, "a_i": last.i, "b_i": ln.i})
        print(d["id"][:50], len(recs), flush=True)
    dst.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in recs))


if __name__ == "__main__":
    main()
