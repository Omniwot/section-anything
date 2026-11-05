"""Print the extraction's lines on given pages (with size vs body and bold), optionally only lines matching a word.
usage: page.py <doc-id> <page>[,<page>...] [grep]"""

from __future__ import annotations

import sys

sys.path.insert(0, "/Users/harshal/Desktop/omni/hustles/.tmp/miss-audit")
import common as C  # noqa: E402
from section_anything.structure import furniture_of  # noqa: E402

doc = next(d for d in C.registry() if d["id"] == sys.argv[1])
pages = [int(x) for x in sys.argv[2].split(",")]
grep = sys.argv[3].lower() if len(sys.argv) > 3 else ""
ext = C.load_ext(doc, "nobm")
body = ext.body_size()
cont, furn = C.contents_lines(ext), furniture_of(ext)
for ln in ext.lines:
    if ln.page in pages and (not grep or grep in ln.text.lower()):
        tag = "C" if ln.i in cont else "F" if ln.i in furn else " "
        print(f"p{ln.page} l{ln.i} {tag} {ln.size - body:+.1f}{'B' if ln.bold else ' '} y{ln.y0:.0f} x{ln.x0:.0f} {ln.text[:110]!r}")
