"""Track M (F063): the fix with one of its two parts switched off, for an ablation on development documents.

usage: PYTHONPATH=<fix src> TAG=abl-<part> SPLIT=dev <venv python> ablate.py <merge|runon> run
  merge: the merge stage as before (no layout test, labels may be joined as wrapped lines)
  runon: the run-on rule as before (a bold title wrapping onto a lowercase line loses its first line)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_anything.strategies import rules as R  # noqa: E402

part = sys.argv.pop(1)
if part == "merge":
    _orig = R._merge_wrapped
    R._merge_wrapped = lambda cands, hints=None, side=frozenset(), ext=None: _orig(cands, hints, side, None)
elif part == "runon":
    R._wrapped_title = lambda ext, ln: False
else:
    sys.exit(f"unknown part {part}")

import match_audit  # noqa: E402

match_audit.main()
