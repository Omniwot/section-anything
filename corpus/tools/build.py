"""Build the test corpus: download sources, make test PDFs and gold files.

    cd corpus/tools && python build.py                 # every source
    python build.py --only hips wikipedia             # some sources
    python build.py --only hips --force               # rebuild entries

Needs network access. Downloads are cached in corpus/files/cache/.
"""

from __future__ import annotations

import argparse
import importlib
import traceback

SOURCES = [
    "hips", "wikipedia", "arxiv", "pmc", "openstax", "manuals", "reports",
    "legislation", "gutenberg", "slides", "scanned", "synthetic",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=SOURCES)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for name in args.only or SOURCES:
        print(f"[{name}]")
        try:
            importlib.import_module(f"src_{name}").build(force=args.force)
        except ModuleNotFoundError as e:
            if e.name == f"src_{name}":
                print("  (not written yet)")
                continue
            traceback.print_exc()
        except Exception:  # noqa: BLE001
            traceback.print_exc()


if __name__ == "__main__":
    main()
