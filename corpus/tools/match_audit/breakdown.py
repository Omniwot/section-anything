"""Track M (F063): every match-failure miss as F056 tags it (cause e, keys v2) split into four groups.

usage: <venv python> breakdown.py <split> [tag]   -> breakdown-<split>-<tag>.txt, .json
Groups, in this order:
  key      the answer key is wrong: the heading is matched once rule R3 moves its page (keys v2.1), or its
           title is printed only more than a page from the key page (F056's gold_page_far);
  scorer   a scorer artifact: the prediction on the heading's line has its title but the one-to-one pairing gave
           it to another heading; a bare-label key heading ("ANNEXE I", "Condition 4") whose label and title
           were predicted as one heading ("ANNEXE I CERTIFICAT DE GEL"); or a maximum pairing would match it;
  system   a real system error (match_audit's e2 sub-causes: merged, split, predicted elsewhere, ...);
  notmatch not a match failure: the only predictions with a similar title belong to other headings, and the
           heading went down F056's b/c/d path (cause2).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from gold_v21 import CONTENTS_TITLE  # noqa: E402
from match_audit import BARE_LABEL, same_title  # noqa: E402
from section_anything.evaluate import _sim  # noqa: E402

GROUPS = ["key", "scorer", "system", "notmatch"]


def rows(tag, gold, split):
    d = C.OUT / f"rows-{tag}-{gold}"
    out = {}
    for p in sorted(d.glob("*.json")):
        r = json.loads(p.read_text())
        if "runs" in r and ("test" if r["doc"]["split"] == "test" else "dev") == split:
            out[r["doc"]["id"]] = r
    return out


def label_side(g, preds) -> bool:
    if not BARE_LABEL.match(g["title"]):
        return False
    lab = C.norm(g["title"])
    return any(abs(p - g["page"]) <= 1 and C.norm(t).startswith(lab) and len(C.norm(t)) > len(lab) + 2
               for t, p, _ in preds)


def max_extra(gold, preds, matched_gis) -> set[int]:
    """Key headings a maximum pairing adds to the scorer's (augmenting paths from its pairs)."""
    edges = defaultdict(list)
    for gi, g in enumerate(gold):
        for pj, (t, p, _) in enumerate(preds):
            if abs(p - g["page"]) <= 1 and _sim(g["title"], t) >= C.THRESHOLD:
                edges[gi].append(pj)
    pairs = C.pair(gold, [{"title": t, "page": p} for t, p, _ in preds])
    g2p, p2g = dict(pairs), {p: g for g, p in pairs.items()}
    sys.setrecursionlimit(100000)

    def aug(gi, seen):
        for pj in edges.get(gi, []):
            if pj not in seen:
                seen.add(pj)
                if pj not in p2g or aug(p2g[pj], seen):
                    g2p[gi], p2g[pj] = pj, gi
                    return True
        return False

    for gi in list(edges):
        if gi not in g2p:
            aug(gi, set())
    return set(g2p) - set(pairs)


_EXT: dict[str, object] = {}


def under_contents_title(doc: dict, gold: list[dict], gi: int, preds: list) -> bool:
    """The unpaired same-title prediction nearest the key page sits on a page under a printed contents title
    ("CONTENTS", "Arrangement of sections"): a contents list the library did not detect."""
    pairs = C.pair(gold, [{"title": t, "page": p} for t, p, _ in preds])
    owned = set(pairs.values())
    g = gold[gi]
    free = [(t, p, ln) for j, (t, p, ln) in enumerate(preds) if j not in owned and same_title(t, g["title"]) and ln is not None]
    if not free:
        return False
    _t, page, line = min(free, key=lambda x: abs(x[1] - g["page"]))
    if doc["id"] not in _EXT:
        _EXT.clear()
        _EXT[doc["id"]] = C.load_ext(doc, "nobm")
    ext = _EXT[doc["id"]]
    return any(ln.page == page and ln.i < line and CONTENTS_TITLE.match(ln.text.strip()) for ln in ext.lines)


def main() -> None:
    split = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else "base"
    reg = {d["id"]: d for d in C.registry()}
    r2, r21 = rows(tag, "v2", split), rows(tag, "v2.1", split)
    tally = defaultdict(Counter)  # (genre|ALL, mode) -> group counts
    gold_n = Counter()
    detail = defaultdict(Counter)
    for doc_id, r in r2.items():
        gold = C.gold_of(reg[doc_id], "v2")
        genre = r["doc"]["genre"]
        other = r21.get(doc_id)
        for k, x in enumerate(r["runs"]):
            for key in ((genre, x["mode"]), ("ALL", x["mode"])):
                gold_n[key] += x["n_gold"]
            es = [m for m in x["misses"] if m["cause"] == "e"]
            if not es:
                continue
            y = other["runs"][k] if other else None
            missed21 = {m["gi"] for m in y["misses"]} if y else set()
            mx = max_extra(gold, x["preds"], None)
            for m in es:
                g = gold[m["gi"]]
                if (y is not None and m["gi"] not in missed21) or m["sub2"] == "gold_page_far":
                    grp, why = "key", ("R3 fixes the page" if m["sub2"] != "gold_page_far" else "printed only far from the key page")
                elif m["sub2"] == "paired_with_another_heading":
                    grp, why = "scorer", "paired with another heading"
                elif label_side(g, x["preds"]):
                    grp, why = "scorer", "bare label key, label and title predicted as one"
                elif m["gi"] in mx:
                    grp, why = "scorer", "maximum pairing matches it"
                elif m["cause2"] == "e":
                    grp, why = "system", m["sub2"]
                    if why == "predicted_elsewhere:body" and under_contents_title(reg[doc_id], gold, m["gi"], x["preds"]):
                        why = "predicted_elsewhere:contents_not_detected"
                else:
                    grp, why = "notmatch", f"{m['cause2']}:{m['sub2']}"
                for key in ((genre, x["mode"]), ("ALL", x["mode"])):
                    tally[key][grp] += 1
                    detail[key][f"{grp}|{why}"] += 1
    lines = [f"Match failures as F056 tags them (cause e, keys v2, {tag} code, {split} documents), by group, per 1,000",
             "reference headings, with the share of the e misses in brackets.\n",
             f"{'genre':26s} {'mode':16s} {'e/1k':>6s} " + " ".join(f"{g:>16s}" for g in GROUPS)]
    out = {}
    for key in sorted(tally, key=lambda k: (k[0] != "ALL", k)):
        t, n = tally[key], gold_n[key]
        e = sum(t.values())
        out["|".join(key)] = {"gold": n, "e_per1000": round(1000 * e / n, 1),
                              **{g: {"per1000": round(1000 * t[g] / n, 1), "share": round(t[g] / e, 3)} for g in GROUPS},
                              "detail": {k: round(1000 * v / n, 2) for k, v in detail[key].most_common()}}
        lines.append(f"{key[0]:26s} {key[1]:16s} {1000 * e / n:6.1f} "
                     + " ".join(f"{1000 * t[g] / n:7.1f} ({t[g] / e:4.0%}) " for g in GROUPS))
    lines.append("\nDetail (ALL genres), per 1,000:")
    for key in sorted(k for k in tally if k[0] == "ALL"):
        lines.append(f"  {key[1]}: " + "; ".join(f"{k} {round(1000 * v / gold_n[key], 1)}" for k, v in detail[key].most_common(14)))
    (C.OUT / f"breakdown-{split}-{tag}.txt").write_text("\n".join(lines) + "\n")
    (C.OUT / f"breakdown-{split}-{tag}.json").write_text(json.dumps(out, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
