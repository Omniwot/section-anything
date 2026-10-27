"""Command line: ``section-anything FILE.pdf --mode quick --format md``.

The result goes to stdout (or ``--output``); a one-line cost summary goes to stderr.
Exit codes: 0 done, 2 bad arguments or configuration, 3 refused by a cost cap, 4 the PDF could not
be read, 1 anything else.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from section_anything.errors import ConfigError, CostCapExceeded, ExtractionFailed, ExtractionTimeout, PdfError


def build_parser() -> argparse.ArgumentParser:
    from section_anything import __version__
    from section_anything.config import Settings

    p = argparse.ArgumentParser(
        prog="section-anything",
        description="Find the sections (headings, levels, page and character spans) of a PDF.",
    )
    p.add_argument("pdf", type=Path, help="PDF file")
    p.add_argument("--mode", default="free",
                   help="free (default), quick, standard, or local:<ollama model>")
    p.add_argument("--format", choices=("md", "json"), default="md", help="output format (default md)")
    p.add_argument("--body", action="store_true", help="md: include each section's text, not only headings")
    p.add_argument("--max-usd", type=float, default=None, help="per-document cost cap in USD (default 0.50)")
    p.add_argument("--over-budget", choices=("downgrade", "fail"), default=None,
                   help="over the cap: downgrade standard -> quick -> free (default), or fail")
    defaults = Settings.model_fields
    p.add_argument("--model", default=None,
                   help="model for quick/standard, overriding the configured one (defaults: quick "
                        f"{defaults['quick_model'].default}, standard {defaults['standard_model'].default})")
    p.add_argument("--base-url", default=None, help="OpenAI-compatible endpoint (default OpenAI)")
    p.add_argument("--max-pages", type=int, default=None, help="refuse PDFs with more pages (default 500)")
    p.add_argument("--timeout", type=float, default=None, help="extraction time limit in seconds (default 120)")
    p.add_argument("-o", "--output", type=Path, default=None, help="write the result to this file")
    p.add_argument("-q", "--quiet", action="store_true", help="no summary on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from section_anything.api import section

    try:
        tree = section(
            args.pdf, args.mode, model=args.model, base_url=args.base_url, max_usd=args.max_usd,
            over_budget=args.over_budget, max_pages=args.max_pages, extract_timeout=args.timeout,
        )
    except (PdfError, ExtractionTimeout, ExtractionFailed) as exc:
        print(f"section-anything: {exc}", file=sys.stderr)
        return 4
    except CostCapExceeded as exc:
        print(f"section-anything: {exc}", file=sys.stderr)
        return 3
    except (ConfigError, ValueError) as exc:  # includes invalid settings values
        print(f"section-anything: {exc}", file=sys.stderr)
        return 2

    out = tree.to_json() + "\n" if args.format == "json" else tree.to_markdown(body=args.body)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    if not args.quiet:
        s = tree.summary()
        cost = "unpriced" if tree.usage.get("cost_usd") is None else f"${s['cost_usd']:.4f}"
        note = f"; downgraded: {' | '.join(s['downgraded'])}" if s["downgraded"] else ""
        print(f"{s['sections']} sections, {s['pages']} pages, mode {s['mode']}"
              f"{' (' + s['model'] + ')' if s['model'] else ''}, {s['calls']} model calls, {cost}, "
              f"{s['seconds']:.1f} s{note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
