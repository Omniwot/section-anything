"""Demo GIF and social preview for the README, drawn from one real, captured session.

Paper:   Visual Instruction Tuning, Liu et al., arXiv:2304.08485v2 (CC BY 4.0),
         https://arxiv.org/pdf/2304.08485v2 (sha256 dc8bace378a282ea78caa9b5959306202fbfa3b8cedaf8a66541a9af18f4d3bf)
Mode:    quick, default model (gpt-6-luna)
Library: section-anything 0.1.3
Date:    2026-10-27

Two steps:

    # 1. Run the README's Python example on the paper in Quick mode (needs an API key in
    #    SECTIONANY_API_KEY, and SECTIONANY_BASE_URL for a non-OpenAI endpoint). Writes the
    #    session exactly as a Python prompt would show it, after a one-line header.
    python docs/assets/make_demo.py capture 2304.08485v2.pdf docs/assets/demo-capture.txt

    # 2. Draw docs/assets/demo.gif and docs/assets/social-preview.png from that file (Pillow;
    #    uses the macOS system fonts Menlo and SF).
    python docs/assets/make_demo.py render docs/assets/demo-capture.txt

Every line of Python session in the images comes from the capture. The renderer only wraps long
lines at the window width and cuts long outputs, marking each cut with "… +N more lines". The
wait for section() is shortened, and the title bar says so with the real time. The GIF's last
frame shows install commands only (nothing run).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = "Liu et al., arXiv:2304.08485 (CC BY 4.0)"
SEP = "-" * 72


# ---------------------------------------------------------------------------------------------
# 1. Capture


def capture(pdf: Path, out: Path) -> None:
    import code
    import contextlib
    import datetime
    import hashlib
    import io
    import os
    import shutil
    import tempfile

    import section_anything

    work = Path(tempfile.mkdtemp(prefix="sa-demo-"))
    shutil.copyfile(pdf, work / "paper.pdf")
    os.chdir(work)  # so the session can say "paper.pdf", as in the README
    ns: dict = {"__name__": "__console__"}
    console = code.InteractiveInterpreter(ns)
    lines: list[str] = []

    def run(stmt: str) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            assert not console.runsource(stmt, symbol="single")
        lines.append(">>> " + stmt)
        lines.extend(buf.getvalue().splitlines())

    run("import section_anything")
    run('tree = section_anything.section("paper.pdf", mode="quick")')
    if "tree" not in ns:  # the run failed: show why and write nothing
        sys.exit("\n".join(lines))
    run("print(tree.to_markdown())")
    run("print(tree.summary())")
    # The section to show, fixed before the run: 4.1 (a subsection), else the first numbered
    # level-2 section.
    secs = ns["tree"].sections
    k = next((i for i, s in enumerate(secs) if s["number"] == "4.1"), None)
    if k is None:
        k = next(i for i, s in enumerate(secs) if s["level"] == 2 and s["number"])
    run(f"s = tree.sections[{k}]")
    run("s")
    run('print(tree.text[s["start"]:s["end"]])')
    lines.append(">>> ")

    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    head = (f"section-anything {section_anything.__version__} | paper {pdf.name} sha256 {sha} | "
            f"captured {datetime.date.today().isoformat()}")
    out.write_text(head + "\n" + SEP + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}: {len(lines)} lines")


# ---------------------------------------------------------------------------------------------
# 2. Render


def parse(path: Path) -> tuple[str, list[tuple[str, list[str]]]]:
    """The header line and the session as (statement, output lines) blocks."""
    text = path.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n" + SEP + "\n")
    assert sep, "no header separator"
    blocks: list[tuple[str, list[str]]] = []
    for line in body.rstrip("\n").split("\n"):
        if line.startswith(">>> "):
            blocks.append((line[4:], []))
        else:
            blocks[-1][1].append(line)
    return head, blocks


def render(cap: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    head, blocks = parse(cap)
    version = re.match(r"section-anything (\S+) ", head).group(1)
    stmts = [b[0] for b in blocks]
    out = dict(blocks)
    summary = ast.literal_eval(out["print(tree.summary())"][0])
    assert summary["mode"] == "quick", summary
    model = summary["model"]
    footer = f"Real output of section-anything {version}, Quick mode ({model})  ·  paper: {PAPER}"

    # Colours and fonts (as in the 0.1.0 demo)
    BG, BAR, PANEL = (30, 30, 46), (42, 42, 60), (24, 24, 37)
    FG, DIM, FAINT = (205, 214, 244), (147, 153, 178), (108, 112, 134)
    GREEN, BLUE, YELLOW = (166, 227, 161), (137, 180, 250), (249, 226, 175)
    DOTS = [(243, 139, 168), (249, 226, 175), (166, 227, 161)]
    MENLO = "/System/Library/Fonts/Menlo.ttc"
    SF = "/System/Library/Fonts/SFNS.ttf"

    def sf(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
        f = ImageFont.truetype(SF, size)
        try:
            f.set_variation_by_name(weight)
        except Exception:  # noqa: BLE001 - older FreeType: keep the default weight
            pass
        return f

    def wrap(line: str, cols: int) -> list[str]:
        """Wrap at the window width, at a space where possible; nothing is dropped."""
        rows = []
        while len(line) > cols:
            cut = line.rfind(" ", 0, cols + 1)
            cut = cut if cut > cols // 2 else cols
            rows.append(line[:cut])
            line = line[cut:].lstrip(" ") if line[cut:cut + 1] == " " else line[cut:]
        rows.append(line)
        return rows

    Run = tuple[str, tuple[int, int, int]]

    # ---- GIF --------------------------------------------------------------------------------
    W, ROWS, LH = 860, 30, 19  # 102 columns: the paper's text lines (up to ~100) do not wrap
    FONT = ImageFont.truetype(MENLO, 14, index=0)
    SMALL = sf(13)
    CW = FONT.getlength("M")
    TITLE_H, PAD_X, PAD_TOP, FOOT_H = 30, 20, 12, 26
    H = TITLE_H + PAD_TOP + ROWS * LH + 6 + FOOT_H
    COLS = int((W - 2 * PAD_X) // CW)

    def base(title: str) -> Image.Image:
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, TITLE_H], fill=BAR)
        for i, c in enumerate(DOTS):
            x = 16 + i * 20
            d.ellipse([x, TITLE_H // 2 - 6, x + 12, TITLE_H // 2 + 6], fill=c)
        d.text((W / 2 - SMALL.getlength(title) / 2, TITLE_H / 2), title, font=SMALL, fill=DIM, anchor="lm")
        fy = H - FOOT_H
        d.line([0, fy, W, fy], fill=BAR)
        d.text((PAD_X, fy + FOOT_H / 2), footer, font=SMALL, fill=FAINT, anchor="lm")
        return im

    BASES = {"python": base("python3 — ~/papers"), "shell": base("zsh — ~/papers")}

    def prompt(stmt: str = "") -> list[Run]:
        return [(">>> ", GREEN), (stmt, FG)]

    def text_rows(lines: list[str], colour=FG) -> list[list[Run]]:
        return [[(r, colour)] for line in lines for r in wrap(line, COLS)]

    def cut_rows(lines: list[str], max_rows: int, cols: int = COLS) -> list[list[Run]]:
        """All lines if they fit in `max_rows`; else the first whole lines and a visible marker."""
        rows = [[(r, FG)] for line in lines for r in wrap(line, cols)]
        if len(rows) <= max_rows:
            return rows
        n = _whole_lines(lines, max_rows - 1, cols, wrap)
        return ([[(r, FG)] for line in lines[:n] for r in wrap(line, cols)]
                + [[(f"… +{len(lines) - n} more lines (cut for space)", YELLOW)]])

    def draw(rows: list[list[Run]], cursor: bool, note: str = "", win: str = "python") -> Image.Image:
        assert len(rows) <= ROWS, f"{len(rows)} rows do not fit"
        im = BASES[win].copy()
        d = ImageDraw.Draw(im)
        if note:  # window chrome, not terminal output: marks a shortened wait
            d.text((W - 16 - SMALL.getlength(note), TITLE_H / 2), note, font=SMALL, fill=YELLOW, anchor="lm")
        y0 = TITLE_H + PAD_TOP
        for r, runs in enumerate(rows):
            x = PAD_X
            for text, col in runs:
                d.text((x, y0 + r * LH), text, font=FONT, fill=col)
                x += FONT.getlength(text)
        if cursor and rows:
            r = len(rows) - 1
            x = PAD_X + sum(FONT.getlength(t) for t, _ in rows[r])
            d.rectangle([x + 1, y0 + r * LH + 1, x + CW, y0 + r * LH + LH - 3], fill=FG)
        return im

    frames: list[tuple[Image.Image, int]] = []

    def add(rows, cursor, ms, note="", win="python"):
        frames.append((draw(rows, cursor, note, win), ms))

    def blink(rows, total_ms, note="", win="python"):
        t, on = 0, True
        while t < total_ms:
            ms = min(530 if on else 470, total_ms - t)
            add(rows, on, ms, note, win)
            t += ms
            on = not on

    def type_stmt(history, stmt, per_char):
        for i in range(0, len(stmt) + 1, 2):
            add(history + [prompt(stmt[:i])], True, per_char * 2)
        add(history + [prompt(stmt)], True, 300)

    def reveal(before, rows, per_frame, ms):
        for k in range(per_frame, len(rows) + per_frame, per_frame):
            add(before + rows[:k], False, ms)

    # Scene 1: the README example, then the heading tree and the run's summary.
    s1 = stmts[:4]
    assert s1 == ["import section_anything", 'tree = section_anything.section("paper.pdf", mode="quick")',
                  "print(tree.to_markdown())", "print(tree.summary())"], s1
    tree_lines = out[s1[2]]
    summary_rows = text_rows(out[s1[3]], DIM)
    fixed = 4 + 1 + len(summary_rows)  # four statements, the closing prompt, the summary
    tree_rows = cut_rows(tree_lines, ROWS - fixed)

    blink([prompt()], 900)
    type_stmt([], s1[0], 40)
    screen = [prompt(s1[0])]
    type_stmt(screen, s1[1], 40)
    blink(screen + [prompt(s1[1])], 1600, f"running (real: {summary['seconds']} s, shortened)")
    screen += [prompt(s1[1])]
    type_stmt(screen, s1[2], 40)
    screen += [prompt(s1[2])]
    reveal(screen, tree_rows, 2, 45)
    screen += tree_rows
    type_stmt(screen, s1[3], 35)
    screen += [prompt(s1[3])] + summary_rows
    add(screen, False, 200)
    blink(screen + [prompt()], 5200)
    scene1 = screen + [prompt()]

    # Scene 2: one section as a chunk: its record, then its text (screen cleared).
    s2 = stmts[4:7]
    assert re.fullmatch(r"s = tree\.sections\[\d+\]", s2[0]) and s2[1:] == ["s", 'print(tree.text[s["start"]:s["end"]])'], s2
    rec_rows = text_rows(out[s2[1]])
    body = out[s2[2]]
    body_rows = cut_rows(body, ROWS - 3 - len(rec_rows) - 1)  # statements, record, closing prompt
    blink([prompt()], 500)
    type_stmt([], s2[0], 40)
    screen = [prompt(s2[0])]
    type_stmt(screen, s2[1], 40)
    screen += [prompt(s2[1])]
    reveal(screen, rec_rows, 2, 60)
    screen += rec_rows
    type_stmt(screen, s2[2], 40)
    screen += [prompt(s2[2])]
    reveal(screen, body_rows, 3, 45)
    screen += body_rows
    blink(screen + [prompt()], 9000)
    scene2 = screen + [prompt()]

    # Scene 3: install line and the integration packages (commands only, nothing run).
    shell = [("~/papers ", BLUE), ("$ ", GREEN)]
    end_rows: list[list[Run]] = [
        shell + [("pip install section-anything", FG)],
        [],
        [("# integrations for LangChain, LlamaIndex and LightRAG:", FAINT)],
        shell + [("pip install langchain-section-anything", FG)],
        shell + [("pip install llama-index-readers-section-anything", FG)],
        shell + [("pip install lightrag-section-anything", FG)],
    ]
    for k in range(1, len(end_rows) + 1):
        add(end_rows[:k], False, 120, win="shell")
    blink(end_rows, 3600, win="shell")

    # One shared palette from the busiest frames, so unchanged pixels match across frames.
    sample = Image.new("RGB", (W, H * 3))
    for i, rows in enumerate((scene1, scene2, end_rows)):
        sample.paste(draw(rows, True, "running (real: 0.00 s, shortened)"), (0, H * i))
    pal = sample.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pframes = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f, _ in frames]
    gif = HERE / "demo.gif"
    pframes[0].save(gif, save_all=True, append_images=pframes[1:], duration=[ms for _, ms in frames],
                    loop=0, optimize=False, disposal=1)
    secs = sum(ms for _, ms in frames) / 1000
    print(f"{gif}: {gif.stat().st_size / 1e6:.2f} MB, {len(frames)} frames, {secs:.1f} s, {W}x{H}")

    # ---- Social preview (1280x640) -----------------------------------------------------------
    SW, SH, X = 1280, 640, 64
    im = Image.new("RGB", (SW, SH), BG)
    d = ImageDraw.Draw(im)
    d.text((X, 40), "Section Anything", font=sf(54, "Bold"), fill=FG)
    pip = "pip install section-anything"
    mono = ImageFont.truetype(MENLO, 19, index=0)
    d.text((SW - X - mono.getlength(pip), 70), pip, font=mono, fill=BLUE, anchor="lm")
    d.text((X, 116), "Find the real sections of a PDF: every heading, its level, the pages it spans and "
           "the exact text under it.", font=sf(24), fill=DIM)
    big = sf(40, "Bold")
    d.text((X, 160), "70.0", font=big, fill=GREEN)
    d.text((X + big.getlength("70.0") + 12, 172), "vs 49.4 for Docling", font=sf(22, "Semibold"), fill=FG)
    d.text((X, 212), "heading-tree TEDS (0–100) on 905 held-out arXiv papers from READoc; Standard mode, "
           "gpt-6-luna", font=sf(17), fill=FAINT)

    # Terminal panel: scene 2 of the GIF, the same captured lines.
    px0, py0, px1, py1 = X, 252, SW - X, 592
    d.rounded_rectangle([px0, py0, px1, py1], radius=12, fill=PANEL)
    d.rounded_rectangle([px0, py0, px1, py0 + 30], radius=12, fill=BAR)
    d.rectangle([px0, py0 + 18, px1, py0 + 30], fill=BAR)
    for i, c in enumerate(DOTS):
        x = px0 + 16 + i * 20
        d.ellipse([x, py0 + 9, x + 12, py0 + 21], fill=c)
    pm = ImageFont.truetype(MENLO, 15, index=0)
    plh = 20
    pcols = int((px1 - px0 - 36) // pm.getlength("M"))
    prows: list[list[Run]] = []
    for stmt in s2:
        prows.append(prompt(stmt))
        if stmt != s2[-1]:
            prows += [[(r, FG)] for line in out[stmt] for r in wrap(line, pcols)]
    prows += cut_rows(body, (py1 - py0 - 46) // plh - len(prows), pcols)
    y = py0 + 40
    for runs in prows:
        x = px0 + 18
        for text, col in runs:
            d.text((x, y), text, font=pm, fill=col)
            x += pm.getlength(text)
        y += plh
    d.text((X, py1 + 22), f"Real output of section-anything {version}, Quick mode ({model}), on {PAPER}.  "
           "Apache-2.0", font=sf(15), fill=FAINT, anchor="lm")
    png = HERE / "social-preview.png"
    im.save(png, optimize=True)
    print(f"{png}: {png.stat().st_size / 1e6:.2f} MB, {SW}x{SH}")


def _whole_lines(body: list[str], rows: int, cols: int, wrap) -> int:
    """How many whole body lines fit in `rows` wrapped rows."""
    n = used = 0
    for line in body:
        used += len(wrap(line, cols))
        if used > rows:
            break
        n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "capture":
        capture(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    elif len(sys.argv) == 3 and sys.argv[1] == "render":
        render(Path(sys.argv[2]).resolve())
    else:
        sys.exit(__doc__)
