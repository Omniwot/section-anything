"""arXiv papers under Creative Commons licences, one per field so templates
differ (two-column ACL/CVPR/IEEE/REVTeX, single-column NeurIPS/amsart,
AASTeX). Gold levels come from the LaTeX source's sectioning commands; titles
are the heading lines as printed in the PDF."""

from __future__ import annotations

import gzip
import io
import re
import tarfile
import urllib.parse

from common import Entry, anchor, built, extraction, fetch, fetch_text, register

# (arXiv category, search terms, template the field usually uses)
FIELDS = [
    ("cs.CL", "language model evaluation", "ACL two-column"),
    ("cs.CV", "image segmentation", "CVPR two-column"),
    ("cs.LG", "reinforcement learning", "NeurIPS/ICLR single-column"),
    ("eess.SP", "signal processing", "IEEE two-column"),
    ("cond-mat.mtrl-sci", "thin films", "REVTeX two-column"),
    ("astro-ph.GA", "galaxies", "AASTeX"),
    ("math.AP", "partial differential equations", "amsart, theorem-heavy"),
    ("q-bio.PE", "epidemic model", "biology"),
    ("econ.GN", "labor market", "economics working paper"),
    ("stat.ME", "causal inference", "statistics, long appendix"),
]

LEVELS = {"part": 1, "chapter": 1, "section": 1, "subsection": 2, "subsubsection": 3}
OPEN = ("creativecommons.org/licenses/by", "creativecommons.org/publicdomain")


SETS = {"cs": "cs", "eess": "eess", "cond-mat": "physics:cond-mat", "astro-ph": "physics:astro-ph",
        "math": "math", "q-bio": "q-bio", "econ": "econ", "stat": "stat"}
DAY = ("2026-09-01", "2026-09-02")


def _candidates(cat: str) -> list[tuple[str, str]]:
    """(id, licence) of papers updated on one day whose primary category is
    `cat`, via OAI-PMH (the search API rate-limits hard)."""
    s = SETS[cat.split(".")[0]]
    q = urllib.parse.urlencode({"verb": "ListRecords", "metadataPrefix": "arXiv", "set": s, "from": DAY[0], "until": DAY[1]})
    xml = fetch_text(f"https://oaipmh.arxiv.org/oai?{q}", f"arxiv/oai-{s.replace(':', '_')}-{DAY[0]}.xml")
    out = []
    for rec in re.findall(r"<arXiv .*?</arXiv>", xml, flags=re.DOTALL):
        aid = re.search(r"<id>([^<]+)</id>", rec)
        cats = re.search(r"<categories>([^<]+)</categories>", rec)
        lic = re.search(r"<license>([^<]+)</license>", rec)
        if aid and cats and lic and cats.group(1).split()[0] == cat:
            out.append((aid.group(1).strip(), lic.group(1).strip()))
    return out


def _sources(aid: str) -> dict[str, str]:
    blob = fetch(f"https://arxiv.org/e-print/{aid}", f"arxiv/{aid.replace('/', '_')}.src").read_bytes()
    files: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.endswith(".tex"):
                    files[m.name] = tf.extractfile(m).read().decode("utf-8", "replace")
    except tarfile.ReadError:
        try:
            files["main.tex"] = gzip.decompress(blob).decode("utf-8", "replace")
        except OSError:
            files["main.tex"] = blob.decode("utf-8", "replace")
    return files


def _strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


def _main_tex(files: dict[str, str]) -> str:
    mains = [k for k, v in files.items() if re.search(r"\\documentclass", _strip_comments(v))]
    main = max(mains or files, key=lambda k: len(files[k]))
    seen: set[str] = set()

    def expand(name: str) -> str:
        seen.add(name)
        text = _strip_comments(files.get(name, ""))

        def sub(m: re.Match) -> str:
            ref = m.group(2).strip()
            for cand in (ref, ref + ".tex", ref.lstrip("./"), ref.lstrip("./") + ".tex"):
                for k in files:
                    if (k == cand or k.endswith("/" + cand)) and k not in seen:
                        return expand(k)
            return ""

        return re.sub(r"\\(input|include|subfile)\s*\{([^}]+)\}", sub, text)

    return expand(main)


def _arg(s: str, i: int) -> tuple[str, int]:
    """Balanced {...} starting at s[i] == '{'."""
    depth, j = 0, i
    while j < len(s):
        if s[j] == "{" and s[j - 1] != "\\":
            depth += 1
        elif s[j] == "}" and s[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return s[i + 1 :], len(s)


def _clean(t: str) -> str:
    t = re.sub(r"\\texorpdfstring\s*\{((?:[^{}]|\{[^{}]*\})*)\}\s*\{[^{}]*\}", r"\1", t)
    t = re.sub(r"\\(label|cite[pt]?|ref|footnote|thanks|index)\*?\s*(\[[^\]]*\])?\{[^{}]*\}", "", t)
    for _ in range(3):
        t = re.sub(r"\\[a-zA-Z]+\*?\s*(\[[^\]]*\])?\{((?:[^{}]|\{[^{}]*\})*)\}", r"\2", t)
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", t)
    t = t.replace("~", " ").replace("$", "").replace("{", "").replace("}", "").replace("\\", "")
    return re.sub(r"\s+", " ", t).strip()


def _macros(tex: str) -> dict[str, str]:
    """Argument-free \\newcommand / \\def definitions, e.g. \\newcommand{\\name}{FedBay}."""
    out = {}
    for m in re.finditer(r"\\(?:re)?(?:newcommand|providecommand|def)\*?\s*\{?\\([a-zA-Z]+)\}?\s*(?=\{)", tex):
        body, _ = _arg(tex, m.end())
        if "#" not in body and len(body) < 80:
            out[m.group(1)] = body.replace("\\xspace", "").replace("\\xspace{}", "")
    return out


def _expand(t: str, macros: dict[str, str]) -> str:
    for _ in range(3):
        t = re.sub(r"\\([a-zA-Z]+)(\{\})?", lambda m: macros.get(m.group(1), m.group(0)), t)
    return t


def headings(tex: str) -> list[tuple[int, str]]:
    macros = _macros(tex)
    body = tex.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    used = sorted({m.group(1) for m in re.finditer(r"\\(part|chapter|section|subsection|subsubsection)\*?\s*[\[{]", body)},
                  key=lambda c: list(LEVELS).index(c))
    rank = {c: i + 1 for i, c in enumerate(used)}  # shallowest command present is level 1
    out = []
    for m in re.finditer(r"\\(part|chapter|section|subsection|subsubsection)(\*?)\s*", body):
        i = m.end()
        if i < len(body) and body[i] == "[":
            i = body.index("]", i) + 1
            while i < len(body) and body[i].isspace():
                i += 1
        if i >= len(body) or body[i] != "{":
            continue
        title, _ = _arg(body, i)
        title = _clean(_expand(title, macros))
        if title:
            out.append((rank[m.group(1)], title))
    return out


def build(force: bool = False) -> None:
    for n, (cat, _terms, template) in enumerate(FIELDS, 1):
        eid = f"arxiv-{n:02d}"
        if built(eid) and not force:
            continue
        chosen = None
        tried = 0
        for aid, lic in _candidates(cat):
            if not any(o in lic for o in OPEN) or tried >= 6:
                continue
            tried += 1
            try:
                items = headings(_main_tex(_sources(aid)))
            except Exception as e:  # noqa: BLE001 — a bad source archive skips the candidate
                print(f"    skip {aid}: {type(e).__name__}")
                continue
            if len(items) < 5:
                continue
            pdf = fetch(f"https://arxiv.org/pdf/{aid}", f"arxiv/{aid.replace('/', '_')}.pdf")
            gold, missing = anchor(extraction(pdf), items, pdf_titles=True, run_in=True)
            if len(missing) <= 0.25 * len(items):  # otherwise the source doesn't match the PDF
                chosen = (aid, lic, pdf, gold, missing)
                break
        if not chosen:
            print(f"  ✗ {cat}: no CC-licensed paper whose source matches its PDF")
            continue
        aid, lic, pdf, gold, missing = chosen
        register(
            Entry(
                id=eid, category="papers", title=f"arXiv:{aid} ({cat})", source_url=f"https://arxiv.org/abs/{aid}",
                license=lic, gold_source="latex", variant=template,
                notes=f"unanchored: {missing[:5]}" if missing else "",
            ),
            pdf, gold, len(missing),
        )
