"""Command line: ``section-anything FILE.pdf --mode quick --format md``.

Docling's output works too: ``section-anything FILE.pdf --docling FILE.json`` uses it as hints for
the PDF's own lines, and ``section-anything FILE.json`` sections the Docling document itself (for a
scanned PDF).

The result goes to stdout (or ``--output``); a one-line cost summary goes to stderr.
Exit codes: 0 done, 2 bad arguments or configuration, 3 refused by a cost cap, 4 the PDF could not
be read, 1 anything else.

Folder mode (``section-anything DIR -o OUT``, or several PDFs): one output per PDF in ``OUT``, one
line per PDF and a total on stderr. Exit codes: 0 every PDF done or skipped, 4 one or more failed
(each failure is on its line; the others are written), 2 bad arguments or configuration (before any
PDF is read), 1 anything else (for example an output that cannot be written).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from section_anything.errors import ConfigError, CostCapExceeded, ExtractionFailed, ExtractionTimeout, PdfError


def build_parser() -> argparse.ArgumentParser:
    from section_anything import __version__
    from section_anything.config import Settings

    p = argparse.ArgumentParser(
        prog="section-anything",
        description="Find the sections (headings, levels, page and character spans) of a PDF.",
    )
    p.add_argument("pdf", type=Path, nargs="+",
                   help="PDF file, or Docling's JSON of one; a folder or several PDFs run in folder mode "
                        "(needs -o DIR)")
    p.add_argument("--mode", default="free",
                   help="free (default), quick, standard, auto (free, then quick only where free is unsure), "
                        "or local:<ollama model>")
    p.add_argument("--format", choices=("md", "json"), default="md", help="output format (default md)")
    p.add_argument("--body", action="store_true",
                   help="include each section's text: md reflowed under its heading; json as `text`, "
                        "exactly tree.text[start:end]")
    p.add_argument("--max-usd", type=float, default=None, help="per-document cost cap in USD (default 0.50)")
    p.add_argument("--over-budget", choices=("downgrade", "fail"), default=None,
                   help="over the cap: downgrade standard -> quick -> free (default), or fail")
    defaults = Settings.model_fields
    p.add_argument("--model", default=None,
                   help="model for quick/standard, overriding the configured one (defaults: quick "
                        f"{defaults['quick_model'].default}, standard {defaults['standard_model'].default})")
    p.add_argument("--provider", choices=("openai", "anthropic"), default=None,
                   help="API for --model (default: anthropic for claude-* models, otherwise openai)")
    p.add_argument("--base-url", default=None,
                   help="endpoint for the provider (default OpenAI's; Anthropic's for Claude models)")
    p.add_argument("--docling", type=Path, default=None, metavar="JSON",
                   help="Docling's output of the same PDF (saved as JSON) as hints: its section headers, page "
                        "headers and footers (one PDF only)")
    p.add_argument("--max-pages", type=int, default=None, help="refuse PDFs with more pages (default 500)")
    p.add_argument("--timeout", type=float, default=None, help="extraction time limit in seconds (default 120)")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="write the result to this file; in folder mode, the folder for one output per PDF")
    p.add_argument("-q", "--quiet", action="store_true", help="no summary on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    g = p.add_argument_group("folder mode", "a folder or several PDFs: one <name>.md or <name>.json per PDF in -o DIR")
    g.add_argument("--recursive", action="store_true", help="also PDFs in subfolders (kept as subfolders of DIR)")
    g.add_argument("--skip-existing", action="store_true",
                   help="skip PDFs whose output file exists, to resume a stopped run")
    g.add_argument("--max-usd-total", type=float, default=None,
                   help="cost cap in USD for the whole run; each PDF's cap is lowered to what is left")
    return p


def _options(args: argparse.Namespace) -> dict:
    return {"model": args.model, "provider": args.provider, "base_url": args.base_url, "max_usd": args.max_usd,
            "over_budget": args.over_budget, "max_pages": args.max_pages, "extract_timeout": args.timeout}


def _render(tree, args: argparse.Namespace) -> str:
    return tree.to_json(text=args.body) + "\n" if args.format == "json" else tree.to_markdown(body=args.body)


def _summary(tree) -> str:
    s = tree.summary()
    cost = "unpriced" if tree.usage.get("cost_usd") is None else f"${s['cost_usd']:.4f}"
    note = f"; downgraded: {' | '.join(s['downgraded'])}" if s["downgraded"] else ""
    return (f"{s['sections']} sections, {s['pages']} pages, mode {s['mode']}"
            f"{' (' + s['model'] + ')' if s['model'] else ''}, {s['calls']} model calls, {cost}, "
            f"{s['seconds']:.1f} s{note}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if len(args.pdf) > 1 or args.pdf[0].is_dir():
        if args.docling is not None:
            print("section-anything: --docling: only for a single PDF", file=sys.stderr)
            return 2
        return _folder_mode(args)
    batch_only = [flag for flag, on in (("--recursive", args.recursive), ("--skip-existing", args.skip_existing),
                                        ("--max-usd-total", args.max_usd_total is not None)) if on]
    if batch_only:
        print(f"section-anything: {', '.join(batch_only)}: only for a folder or several PDFs (with -o DIR)",
              file=sys.stderr)
        return 2
    from section_anything.api import section

    try:
        tree = section(args.pdf[0], args.mode, docling=args.docling, **_options(args))
    except (PdfError, ExtractionTimeout, ExtractionFailed) as exc:
        print(f"section-anything: {exc}", file=sys.stderr)
        return 4
    except CostCapExceeded as exc:
        print(f"section-anything: {exc}", file=sys.stderr)
        return 3
    except (ConfigError, ValueError) as exc:  # includes invalid settings values
        print(f"section-anything: {exc}", file=sys.stderr)
        return 2

    out = _render(tree, args)
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    if not args.quiet:
        print(_summary(tree), file=sys.stderr)
    return 0


def _pdfs_in(folder: Path, recursive: bool) -> list[Path]:
    """The folder's PDFs (any case of ``.pdf``), sorted; hidden files and folders are left out."""
    def wanted(name: str) -> bool:
        return name.lower().endswith(".pdf") and not name.startswith(".")

    if not recursive:
        return sorted(p for p in folder.iterdir() if wanted(p.name) and p.is_file())
    found: list[Path] = []
    for root, dirs, files in os.walk(folder):  # does not follow symlinked folders
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        found += [Path(root, f) for f in sorted(files) if wanted(f)]
    return found


def plan_outputs(inputs: list[Path], out_dir: Path, fmt: str, recursive: bool = False) -> list[tuple[Path, Path]]:
    """(pdf, output file) for each PDF to run, each PDF once. A folder's PDFs keep their place below it
    (``docs/a/x.pdf`` -> ``OUT/a/x.md``); a PDF named on its own goes straight into ``OUT``. Names that
    would clash (ignoring case) get ``-2``, ``-3``, ...: ``x.md``, ``x-2.md``."""
    found: list[tuple[Path, Path]] = []
    seen: set[Path] = set()
    for src in inputs:
        pairs = ([(p, p.relative_to(src)) for p in _pdfs_in(src, recursive)] if src.is_dir()
                 else [(src, Path(src.name))])
        for pdf, rel in pairs:
            if (key := pdf.resolve()) not in seen:
                seen.add(key)
                found.append((pdf, rel.with_suffix("." + fmt)))
    natural = {str(rel).casefold() for _, rel in found}
    used: set[str] = set()
    jobs = []
    for pdf, rel in found:
        target, n = rel, 2
        while str(target).casefold() in used or (target != rel and str(target).casefold() in natural):
            target, n = rel.with_name(f"{rel.stem}-{n}{rel.suffix}"), n + 1
        used.add(str(target).casefold())
        jobs.append((pdf, out_dir / target))
    return jobs


def _write(target: Path, text: str) -> None:
    """Write via a temporary file, so a stopped run never leaves a half-written output for
    --skip-existing to take as done."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(f".{target.name}.part")
    part.write_text(text, encoding="utf-8")
    os.replace(part, target)


def _folder_mode(args: argparse.Namespace) -> int:
    def say(msg: str) -> None:
        if not args.quiet:
            print(msg, file=sys.stderr)

    if args.output is None:
        print("section-anything: a folder or several PDFs need -o/--output DIR for the results", file=sys.stderr)
        return 2
    if args.output.exists() and not args.output.is_dir():
        print(f"section-anything: -o {args.output}: not a folder", file=sys.stderr)
        return 2
    from section_anything.batch import section_many

    t0 = time.monotonic()
    jobs = plan_outputs(args.pdf, args.output, args.format, args.recursive)
    todo = []
    for pdf, target in jobs:
        if args.skip_existing and target.exists():
            say(f"{pdf}: skipped, {target} exists")
        else:
            todo.append((pdf, target))
    done = failed = calls = 0
    spent = 0.0
    try:
        results = section_many([pdf for pdf, _ in todo], args.mode, max_usd_total=args.max_usd_total, **_options(args))
        for k, r in enumerate(results):
            pdf, target = todo[k]
            spent += r.cost_usd
            if r.tree is None:
                failed += 1
                say(f"[{k + 1}/{len(todo)}] {pdf}: failed, {type(r.error).__name__}: {r.error}")
                continue
            calls += r.tree.usage.get("calls", 0)
            try:
                _write(target, _render(r.tree, args))
            except OSError as exc:
                print(f"section-anything: cannot write {target}: {exc.strerror or exc}", file=sys.stderr)
                return 1
            done += 1
            say(f"[{k + 1}/{len(todo)}] {pdf}: {_summary(r.tree)} -> {target}")
    except (ConfigError, ValueError) as exc:  # raised before the first PDF is read
        print(f"section-anything: {exc}", file=sys.stderr)
        return 2
    total = f" of the ${args.max_usd_total:.2f} total cap" if args.max_usd_total is not None else ""
    say(f"{len(jobs)} PDFs: {done} done, {failed} failed, {len(jobs) - len(todo)} skipped; {calls} model calls, "
        f"${spent:.4f}{total}, {time.monotonic() - t0:.1f} s")
    return 4 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
