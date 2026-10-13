"""Find a model-quoted marker in the document text.

The model quotes markers "verbatim", but quotes rarely survive byte-for-byte:
curly vs straight quotes, dashes, ligatures (ﬁ), soft hyphens, words split by a
line-break hyphen, and stray spacing all differ between what a PDF stores and
what a model types back. Both sides are therefore reduced to a canonical form
— case-folded letters and digits separated by single spaces — while keeping a
map from every canonical character back to its position in the original
text. Matching happens in canonical space; results are mapped back so the
section boundary lands on the exact original character.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

from rapidfuzz import fuzz

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}
FUZZY_MIN = 85.0


def _canon(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    origin: list[int] = []
    pending_space = False
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        # "infor-\nmation" → "information": a hyphen ending a line before a
        # lowercase continuation is a typesetting artifact, not punctuation.
        if ch in "-­" and i + 2 < n and text[i + 1] == "\n" and text[i + 2].islower():
            i += 2
            continue
        for c in LIGATURES.get(ch, ch).casefold():
            if c.isalnum():
                if pending_space and out:
                    out.append(" ")
                    origin.append(i)
                out.append(c)
                origin.append(i)
                pending_space = False
            else:
                pending_space = True
        i += 1
    return "".join(out), origin


def canon(text: str) -> str:
    return _canon(text)[0]


@dataclass
class Hit:
    start: int  # original-text char offsets
    end: int
    score: float
    method: str  # "exact" | "fuzzy"


class Locator:
    def __init__(self, text: str) -> None:
        self.text = text
        self.s, self.origin = _canon(text)

    def _to_canon(self, pos: int) -> int:
        return min(bisect.bisect_left(self.origin, pos), len(self.s))

    def find_all(self, marker: str, lo: int = 0, hi: int | None = None, limit: int = 50) -> list[Hit]:
        """Every exact (canonical) occurrence of `marker` in [lo, hi), in order."""
        m = canon(marker)
        if len(m) < 3:
            return []
        hi = len(self.text) if hi is None else hi
        clo, chi = self._to_canon(lo), self._to_canon(hi)
        out: list[Hit] = []
        k = self.s.find(m, clo, chi)
        while k != -1 and len(out) < limit:
            out.append(Hit(self.origin[k], self.origin[k + len(m) - 1] + 1, 100.0, "exact"))
            k = self.s.find(m, k + 1, chi)
        return out

    def find(self, marker: str, near: int | None = None, lo: int = 0, hi: int | None = None) -> Hit | None:
        """Locate `marker` within original-text range [lo, hi), preferring the
        occurrence closest to `near`."""
        m = canon(marker)
        if len(m) < 3:
            return None
        hi = len(self.text) if hi is None else hi
        clo, chi = self._to_canon(lo), self._to_canon(hi)
        target = self._to_canon(near) if near is not None else clo

        best = None
        k = self.s.find(m, clo, chi)
        while k != -1:
            if best is None or abs(k - target) < abs(best - target):
                best = k
            k = self.s.find(m, k + 1, chi)
        if best is not None:
            return Hit(self.origin[best], self.origin[best + len(m) - 1] + 1, 100.0, "exact")

        # Fuzzy fallback, bounded so a 500-page document stays fast.
        span = max(4000, len(m) * 40)
        wlo, whi = max(clo, target - span), min(chi, target + span)
        if whi - wlo < len(m):
            return None
        al = fuzz.partial_ratio_alignment(m, self.s[wlo:whi], score_cutoff=FUZZY_MIN)
        if al is None:
            return None
        a, b = wlo + al.dest_start, wlo + al.dest_end
        return Hit(self.origin[a], self.origin[max(a, b - 1)] + 1, round(al.score, 1), "fuzzy")
