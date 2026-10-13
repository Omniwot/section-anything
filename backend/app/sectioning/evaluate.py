"""Score proposed sections against a gold annotation.

Gold files list headings as {"level", "title", "page"}; title includes any
numbering ("2.3 Cell Cycle"). A predicted section matches a gold heading when
its title (number + title) is ≥85% similar after normalization and it starts
within ±1 page. Each gold heading matches at most one prediction.

Metrics: precision, recall, F1, and level agreement — the share of
consecutive matched pairs whose relative depth (deeper / same / shallower)
agrees with gold, which compares hierarchies without assuming both sides
number their levels the same way.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.sectioning.markers import canon

THRESHOLD = 85.0


def _sim(a: str, b: str) -> float:
    a, b = canon(a).replace(" ", ""), canon(b).replace(" ", "")
    if not a or not b:
        return 0.0
    score = fuzz.ratio(a, b)
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 0.5 * len(long_):
        score = max(score, fuzz.partial_ratio(a, b))
    return score


def score(gold: list[dict], sections: list[dict]) -> dict:
    pred = [
        {"title": f"{s.get('number', '')} {s['title']}".strip(), "level": s["level"], "page": s["page_start"]}
        for s in sections
    ]
    cands = []
    for gi, g in enumerate(gold):
        for pj, p in enumerate(pred):
            if abs(p["page"] - g["page"]) <= 1:
                s = _sim(g["title"], p["title"])
                if s >= THRESHOLD:
                    cands.append((s, -abs(p["page"] - g["page"]), gi, pj))
    pairs: dict[int, int] = {}
    used: set[int] = set()
    for _s, _d, gi, pj in sorted(cands, reverse=True):
        if gi not in pairs and pj not in used:
            pairs[gi] = pj
            used.add(pj)
    precision = len(used) / len(pred) if pred else 0.0
    recall = len(pairs) / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    order = sorted(pairs)
    agree = total = 0
    for a, b in zip(order, order[1:], strict=False):
        g = (gold[b]["level"] > gold[a]["level"]) - (gold[b]["level"] < gold[a]["level"])
        p = (pred[pairs[b]]["level"] > pred[pairs[a]]["level"]) - (pred[pairs[b]]["level"] < pred[pairs[a]]["level"])
        agree += g == p
        total += 1
    return {
        "gold_headings": len(gold),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "level_agreement": round(agree / total, 3) if total else None,
        "missed": [gold[i]["title"] for i in range(len(gold)) if i not in pairs][:50],
        "extra": [pred[j]["title"] for j in range(len(pred)) if j not in used][:50],
    }
