"""Software and technical manuals, one per documentation toolchain, so
heading styles and page furniture differ. Gold from bookmarks, removed from
the test copy."""

from __future__ import annotations

from common import Entry, built, fetch, from_bookmarks

# (id suffix, url, cache name, title, licence, toolchain, from_bookmarks kwargs)
MANUALS = [
    ("progit", "https://github.com/progit/progit2/releases/download/2.1.450/progit.pdf", "progit.pdf",
     "Pro Git, 2nd edition", "CC BY-NC-SA 3.0", "AsciiDoc / asciidoctor-pdf", {"max_pages": 250}),
    ("bash", "https://www.gnu.org/software/bash/manual/bash.pdf", "bash.pdf",
     "GNU Bash Reference Manual", "GFDL 1.3", "Texinfo", {}),
    ("make", "https://www.gnu.org/software/make/manual/make.pdf", "make.pdf",
     "GNU Make Manual", "GFDL 1.3", "Texinfo", {}),
    ("r-intro", "https://cran.r-project.org/doc/manuals/r-release/R-intro.pdf", "R-intro.pdf",
     "An Introduction to R", "GPL-2 or later", "Texinfo (R)", {}),
    ("requests", "https://requests.readthedocs.io/_/downloads/en/latest/pdf/", "requests.pdf",
     "Requests documentation", "Apache-2.0", "Sphinx / LaTeX", {}),
    ("sphinx", "https://www.sphinx-doc.org/_/downloads/en/master/pdf/", "sphinx.pdf",
     "Sphinx documentation (excerpt)", "BSD-2-Clause", "Sphinx / LaTeX", {"max_pages": 300}),
    ("pillow", "https://pillow.readthedocs.io/_/downloads/en/stable/pdf/", "pillow.pdf",
     "Pillow documentation (excerpt)", "MIT-CMU (HPND)", "Sphinx / LaTeX, API reference", {"max_pages": 200}),
    ("postgresql", "https://www.postgresql.org/files/documentation/pdf/16/postgresql-16-US.pdf", "postgresql-16.pdf",
     "PostgreSQL 16 manual, Part II: The SQL Language", "PostgreSQL License", "DocBook / FOP",
     {"match": r"^Part II\. The SQL Language", "max_pages": 400}),
    ("lo-writer", "https://documentation.libreoffice.org/assets/Uploads/Documentation/en/WG7.6/WG76-WriterGuide.pdf",
     "WG76-WriterGuide.pdf", "LibreOffice Writer Guide 7.6 (excerpt)", "GPL-3 / CC BY 4.0",
     "LibreOffice Writer export", {"max_pages": 250}),
    ("tlcl", "https://sourceforge.net/projects/linuxcommand/files/TLCL/19.01/TLCL-19.01.pdf/download", "TLCL-19.01.pdf",
     "The Linux Command Line, 19.01 (excerpt)", "CC BY-NC-ND 3.0", "LibreOffice book layout", {"max_pages": 300}),
]


def build(force: bool = False) -> None:
    for key, url, name, title, licence, tool, kw in MANUALS:
        eid = f"manual-{key}"
        if built(eid) and not force:
            continue
        src = fetch(url, f"manuals/{name}", timeout=900)
        from_bookmarks(
            Entry(id=eid, category="manuals", title=title, source_url=url, license=licence,
                  gold_source="bookmarks", complete=False, variant=tool),
            src, **kw,
        )
