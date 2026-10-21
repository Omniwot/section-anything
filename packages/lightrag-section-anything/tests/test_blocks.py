from dataclasses import dataclass

from lightrag_section_anything.blocks import _heading_lines, _reflow, build_blocks


@dataclass
class L:  # minimal stand-in for app.sectioning.extract.Line
    i: int
    page: int
    text: str
    y1: float
    size: float = 10.0
    x0: float = 72.0
    x1: float = 540.0

    @property
    def y0(self) -> float:
        return self.y1 - self.size


@dataclass
class Ext:
    lines: list


def _ext(texts):
    lines, y, page = [], 760.0, 1
    for _i, t in enumerate(texts):
        if t == "<page>":
            page, y = page + 1, 760.0
            continue
        lines.append(L(len(lines), page, t, y))
        y -= 12.0
    return Ext(lines)


def sec(first, level, title, number="", flags=()):
    return {"first_line": first, "level": level, "title": title, "number": number, "flags": list(flags)}


def test_parents_are_ancestors_only_and_title_block():
    ext = _ext(["My Paper", "intro text", "1 Introduction", "body a", "1.1 Scope", "body b", "2 Methods", "body c"])
    blocks, title = build_blocks(ext, [sec(0, 1, "My Paper", flags=["doc_title"]), sec(2, 1, "Introduction", "1"),
                                       sec(4, 2, "Scope", "1.1"), sec(6, 1, "Methods", "2")])
    assert title == "My Paper"
    by = {b["heading"]: b for b in blocks}
    assert by["My Paper"]["level"] == 0 and by["My Paper"]["is_title_block"]
    assert by["1 Introduction"]["parent_headings"] == []
    assert by["1.1 Scope"]["parent_headings"] == ["1 Introduction"]
    assert by["2 Methods"]["parent_headings"] == []
    assert by["1.1 Scope"]["content"].startswith("## 1.1 Scope\n")
    assert "body b" in by["1.1 Scope"]["content"] and "Scope\n1.1" not in by["1.1 Scope"]["content"]


def test_preface_and_wrapped_heading():
    ext = _ext(["Copyright notice", "Article 9", "Freedom of association", "All Germans shall have the right"])
    blocks, _ = build_blocks(ext, [sec(1, 2, "Article 9 Freedom of association")])
    assert blocks[0]["session_type"] == "preface" and blocks[0]["level"] == 0
    body = blocks[1]["content"].split("\n")
    assert body[0] == "## Article 9 Freedom of association" and body[1] == "All Germans shall have the right"


def test_run_in_heading_keeps_its_line():
    ext = _ext(["Short title. This Act may be cited as the Example Act."])
    assert _heading_lines(ext.lines, "Short title.") == 0


def test_reflow_joins_lines_and_dehyphenates():
    ext = _ext(["The quick brown fox jumps over the lazy dog and keeps run-", "ning until the end of the line.",
                "<page>", "Next paragraph starts here."])
    paras = _reflow(ext.lines)
    assert paras[0] == "The quick brown fox jumps over the lazy dog and keeps running until the end of the line."
    assert paras[1] == "Next paragraph starts here."
