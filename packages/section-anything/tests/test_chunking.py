"""Section-aware chunks with a size cap: `chunk_sections` and `SectionTree.chunks`."""

from __future__ import annotations

import section_anything
from section_anything.chunking import Chunk, chunk_sections

SENTENCE = "Keep the material cool and dry at all times."  # 44 characters


def sec(number: str, title: str, level: int, body: str = "", pages: tuple[int, int] = (1, 1), flags: list[str] | None = None) -> dict:
    head = f"{number} {title}".strip()
    return {"number": number, "title": title, "level": level, "flags": flags or [], "page_start": pages[0],
            "page_end": pages[1], "text": f"{head}\n{body}" if body else head}


def paragraphs(n: int, sentences: int = 3) -> str:
    return "\n\n".join(" ".join(f"{SENTENCE[:-1]} ({k}.{j})." for j in range(sentences)) for k in range(n))


def test_long_section_splits_at_paragraphs():
    body = paragraphs(6)  # six paragraphs of about 150 characters
    chunks = chunk_sections([sec("1", "Intro", 1, body)], max_chars=320, min_chars=0)
    assert len(chunks) == 3
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert all(len(c.text) <= 320 for c in chunks)
    paras = body.split("\n\n")
    assert chunks[0].text == "\n\n".join(paras[:2]) and chunks[2].text == "\n\n".join(paras[4:])  # whole paragraphs
    assert all((c.section_index, c.heading_path) == (0, ["1 Intro"]) for c in chunks)


def test_sentence_fallback_for_a_long_paragraph():
    body = " ".join(f"{SENTENCE[:-1]} number {k}." for k in range(10))  # one paragraph, no blank line
    chunks = chunk_sections([sec("1", "Intro", 1, body)], max_chars=120, min_chars=0)
    assert len(chunks) > 1 and all(len(c.text) <= 120 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)  # cut between sentences
    assert " ".join(c.text for c in chunks) == body


def test_hard_cut_for_a_long_sentence():
    body = "x" * 250 + " " + "y" * 30  # one 250-character word: no sentence or space to cut at
    chunks = chunk_sections([sec("1", "Intro", 1, body)], max_chars=100, min_chars=0)
    assert [len(c.text) for c in chunks] == [100, 100, 81]  # the last cut keeps the space-separated tail
    assert "".join(c.text for c in chunks).replace(" ", "") == body.replace(" ", "")


def test_short_siblings_merge_under_the_same_parent_only():
    sections = [
        sec("1", "Safety", 1, "An overview paragraph that is long enough to stand on its own as a chunk here."),
        sec("1.1", "Scope", 2, "Short."),
        sec("1.2", "Storage", 2, "Also short."),
        sec("1.3", "Handling", 2, "Still short."),
        sec("2", "Disposal", 1, "Short too."),  # a different parent: never merged into 1.x
    ]
    chunks = chunk_sections(sections, max_chars=2000, min_chars=30)
    assert [(c.section_index, c.heading_path) for c in chunks] == [(0, ["1 Safety"]), (1, ["1 Safety"]), (4, ["2 Disposal"])]
    merged = chunks[1]
    assert merged.text == "1.1 Scope\n\nShort.\n\n1.2 Storage\n\nAlso short.\n\n1.3 Handling\n\nStill short."
    assert merged.prefixed_text.startswith("1 Safety\n\n1.1 Scope")
    assert chunks[2].text == "Short too."


def test_merge_stops_once_min_chars_is_reached():
    sections = [sec("1", "A", 1, "a" * 10), sec("2", "B", 1, "b" * 10), sec("3", "C", 1, "c" * 10), sec("4", "D", 1, "d" * 10)]
    chunks = chunk_sections(sections, max_chars=2000, min_chars=25)
    assert [c.section_index for c in chunks] == [0, 2]  # 1 + 2 reach 25 together, then 3 + 4
    chunks = chunk_sections(sections[:3], max_chars=2000, min_chars=25)
    assert [c.section_index for c in chunks] == [0] and chunks[0].text.endswith("3 C\n\ncccccccccc")  # a last short one joins
    chunks = chunk_sections(sections[:3], max_chars=35, min_chars=25)
    assert [c.section_index for c in chunks] == [0, 2]  # unless that would pass max_chars


def test_heading_only_section_is_a_chunk():
    sections = [sec("1", "Introduction", 1), sec("1.1", "Scope", 2), sec("2", "Methods", 1)]
    chunks = chunk_sections(sections, max_chars=2000, min_chars=200)
    assert [c.text for c in chunks] == ["1 Introduction", "1.1 Scope", "2 Methods"]  # a child is not a sibling: no merge
    assert chunks[1].heading_path == ["1 Introduction", "1.1 Scope"]
    assert chunks[1].prefixed_text == "1 Introduction > 1.1 Scope"  # the heading is not repeated under its path
    assert chunk_sections([sec("1", "A", 1), sec("2", "B", 1)], min_chars=200)[0].text == "1 A\n\n2 B"


def test_overlap_repeats_the_previous_tail():
    body = paragraphs(4)
    chunks = chunk_sections([sec("1", "Intro", 1, body)], max_chars=200, min_chars=0, overlap_chars=60)
    assert len(chunks) >= 3 and all(len(c.text) <= 200 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        shared = max(n for n in range(61) if prev.text.endswith(nxt.text[:n]))  # the previous chunk's tail
        assert 0 < shared <= 60 and nxt.text[shared].isspace()
        assert prev.text[-shared - 1].isspace()  # the tail starts at a word boundary
    assert chunk_sections([sec("1", "Intro", 1, body)], max_chars=200, min_chars=0, overlap_chars=0)[1].text.startswith("Keep")


def test_custom_length_function():
    words = len  # a stand-in token counter: words
    body = paragraphs(6, sentences=2)
    chunks = chunk_sections([sec("1", "Intro", 1, body)], max_chars=40, min_chars=0, length=lambda s: len(s.split()))
    assert len(chunks) == 3 and all(len(c.text.split()) <= 40 for c in chunks)  # 120 words, 40 per chunk
    assert words(chunks[0].text) > 40  # the cap is in words, not characters


def test_heading_path_follows_nesting_and_pages():
    sections = [
        sec("", "Report", 1, "By someone.", flags=["doc_title"]),
        sec("3", "Safety", 1, paragraphs(2), pages=(2, 3)),
        sec("3.2", "Storage", 2, paragraphs(2), pages=(3, 4)),
        sec("3.2.1", "Cold", 3, paragraphs(1), pages=(4, 4)),
        sec("4", "Disposal", 1, paragraphs(1), pages=(5, 5)),
    ]
    chunks = chunk_sections(sections, min_chars=0)
    assert [c.heading_path for c in chunks] == [["Report"], ["3 Safety"], ["3 Safety", "3.2 Storage"],
                                                ["3 Safety", "3.2 Storage", "3.2.1 Cold"], ["4 Disposal"]]
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (2, 3), (3, 4), (4, 4), (5, 5)]
    assert chunks[3].prefixed_text == f"3 Safety > 3.2 Storage > 3.2.1 Cold\n\n{paragraphs(1)}"
    assert chunk_sections(sections, min_chars=0, prefix=True)[3].text == chunks[3].prefixed_text
    assert chunks[0].text == "By someone."  # the title line is not repeated in the text


def test_front_matter_and_missing_pages():
    sections = [{"number": "", "title": "", "level": 1, "flags": ["front_matter"], "text": "Draft, do not cite."},
                {"number": "1", "title": "Intro", "level": 1, "flags": [], "text": "1 Intro\nHello."}]
    chunks = chunk_sections(sections, min_chars=0)
    assert [(c.text, c.heading_path, c.page_start, c.page_end) for c in chunks] == [
        ("Draft, do not cite.", [], None, None), ("Hello.", ["1 Intro"], None, None)]
    assert chunk_sections([{**sections[0], "text": ""}, sections[1]], min_chars=200)[0].text == "Hello."  # empty front matter: nothing


def test_deterministic():
    sections = [sec("1", "A", 1, paragraphs(5)), sec("1.1", "B", 2, "Short."), sec("1.2", "C", 2, "Also short."), sec("2", "D", 1)]
    runs = [chunk_sections(sections, max_chars=250, min_chars=40, overlap_chars=30) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    assert all(isinstance(c, Chunk) for c in runs[0])


def test_tree_chunks_use_reflowed_bodies(paper_pdf):
    tree = section_anything.section(paper_pdf, mode="free")
    chunks = tree.chunks(max_chars=2000, min_chars=0)
    by_path = {" > ".join(c.heading_path): c for c in chunks}
    scope = by_path["1 Introduction > 1.1 Scope"]
    assert scope.section_index == tree.sections.index(next(s for s in tree.sections if s["title"] == "Scope"))
    assert scope.text.startswith("Sectioning splits") and "1.1 Scope" not in scope.text and "\n" not in scope.text.split("\n\n")[0]
    assert (scope.page_start, scope.page_end) == (1, 1)
    small = tree.chunks(max_chars=200, min_chars=0)
    assert len(small) > len(chunks) and all(len(c.text) <= 200 for c in small)
    assert tree.chunks(max_chars=200, min_chars=0) == small
