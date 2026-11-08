"""`write_guidance`: the sheet writer for `standard` (research finding F069, writer prompt "docs2"). Hand-made
PDFs and a fake model: no network."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import body, write_pdf

import section_anything
import section_anything.guidance as g
from section_anything import ConfigError, CostCapExceeded, Settings, UnpricedModelError
from section_anything.cli import main
from section_anything.strategies.llm_text import TEXT_SYSTEM


def _sample(tmp_path: Path, name: str, pages: int = 2) -> Path:
    return write_pdf(tmp_path / f"{name}.pdf", [
        [(f"{p + 1} Part number {p + 1}", 14, True), *body(4), (f"{p + 1}.1 Detail", 12, True), *body(3)]
        for p in range(pages)
    ])


class Fake:
    """Answers every call with `sheet` (or `answers` in turn) and records what it was asked."""

    def __init__(self, sheet: str = "- Numbered lines such as <n> <Title> are level 1.", answers: list[str] | None = None):
        self.sheet, self.answers, self.calls = sheet, list(answers or []), []

    async def __call__(self, **kw):
        self.calls.append(kw)
        return g.Sheet(sheet=self.answers.pop(0) if self.answers else self.sheet)


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(g, "structured", f)
    return f


def test_two_samples_one_call(tmp_path, fake, caplog):
    a, b = _sample(tmp_path, "a"), _sample(tmp_path, "b")
    with caplog.at_level(logging.WARNING):
        sheet = section_anything.write_guidance([a, b], api_key="sk-test")
    assert sheet == fake.sheet + "\n"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["system"] == g.WRITER_SYSTEM and call["schema"] is g.Sheet
    assert call["model"] == Settings().standard_model and call["effort"] == "medium"
    assert call["user"].startswith("Here is all the sample material: 2 documents. Write the rule sheet, at most 1400 words.")
    assert "=== DOCUMENT 1 of 2: every line, pages 1-2 of 2 ===" in call["user"]
    assert "=== DOCUMENT 2 of 2: every line" in call["user"]
    assert "⟨H+4⟩⟨B⟩ 1 Part number 1" in call["user"]  # the rendering standard's model sees
    assert not caplog.records


def test_writer_prompt_is_the_measured_one():
    """The runner's own instructions, the owner's two rules, the 1,400-word limit; nothing tied to one
    kind of document."""
    assert TEXT_SYSTEM in g.WRITER_SYSTEM and TEXT_SYSTEM in g.MERGE_SYSTEM
    for prompt in (g.WRITER_SYSTEM, g.MERGE_SYSTEM):
        assert "A numbered paragraph or provision is a section even when it has no title" in prompt
        assert "Index letter groups, running headers and contents entries are not sections." in prompt
    assert "at most 1400 words" in g.MERGE_SYSTEM
    low = (g.WRITER_SYSTEM + g.MERGE_SYSTEM).lower()
    for word in ("regulat", "statut", "legislat", "jurisdiction", "legal", "annex", "act ", "rfc", "manual", "thesis"):
        assert word not in low.replace(TEXT_SYSTEM.lower(), ""), word


def test_one_sample_warns(tmp_path, fake, caplog):
    with caplog.at_level(logging.WARNING, logger="section_anything.guidance"):
        g.write_guidance([_sample(tmp_path, "a")], api_key="sk-test")
    assert len(caplog.records) == 1 and "1 sample" in caplog.records[0].getMessage()
    assert "represent" in caplog.records[0].getMessage()


def test_no_samples_and_wrong_type(tmp_path, fake):
    with pytest.raises(ConfigError):
        g.write_guidance([], api_key="sk-test")
    with pytest.raises(TypeError):
        g.write_guidance(str(_sample(tmp_path, "a")), api_key="sk-test")
    assert not fake.calls


def test_long_samples_are_merged(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "BUDGET_CHARS", 1_500)
    f = Fake("- a partial rule")

    async def answer(**kw):
        await f(**kw)
        return g.Sheet(sheet="- merged" if kw["system"] == g.MERGE_SYSTEM else "- a partial rule")

    monkeypatch.setattr(g, "structured", answer)
    a, b = _sample(tmp_path, "a", pages=2), _sample(tmp_path, "b", pages=2)
    sheet = g.write_guidance([a, b], api_key="sk-test", max_usd=5)
    writes = [c for c in f.calls if c["system"] == g.WRITER_SYSTEM]
    assert len(writes) >= 2 and f.calls[-1]["system"] == g.MERGE_SYSTEM
    assert all("a later step merges the parts' sheets" in c["user"] and "at most 800 words" in c["user"] for c in writes)
    assert "(part 1 of" in writes[0]["user"]
    assert f.calls[-1]["user"].startswith(f"PARTIAL SHEETS ({len(writes)}):")
    assert "- a partial rule" in f.calls[-1]["user"]
    assert sheet == "- merged\n"


def test_long_sheet_is_shortened(tmp_path, monkeypatch):
    f = Fake(answers=["word " * 1800, "- short"])
    monkeypatch.setattr(g, "structured", f)
    sheet = g.write_guidance([_sample(tmp_path, "a"), _sample(tmp_path, "b")], api_key="sk-test")
    assert [c["system"] for c in f.calls] == [g.WRITER_SYSTEM, g.SHORTEN_SYSTEM]
    assert sheet == "- short\n"


def test_copied_titles_are_replaced(tmp_path, monkeypatch):
    titles = [{"rights of the data subject", "1 rights of the data subject", "introduction"}, {"introduction"}]

    async def sample_titles(ext, settings):
        return titles.pop(0)

    monkeypatch.setattr(g, "_sample_titles", sample_titles)
    f = Fake(answers=["- Headings like Rights of the Data Subject are level 1. Introduction too.",
                      "- Headings like Rights of the Data Subject are still here."])
    monkeypatch.setattr(g, "structured", f)
    sheet = g.write_guidance([_sample(tmp_path, "a"), _sample(tmp_path, "b")], api_key="sk-test")
    assert f.calls[1]["system"] == g.REWRITE_SYSTEM
    assert "- rights of the data subject" in f.calls[1]["user"]
    assert sheet == "- Headings like <title> are still here.\n"  # what the rewrite left is redacted


def test_refused_up_front_over_the_cap(tmp_path, fake):
    with pytest.raises(CostCapExceeded, match=r"over the \$0\.00 cap.*--max-usd"):
        g.write_guidance([_sample(tmp_path, "a"), _sample(tmp_path, "b")], api_key="sk-test", max_usd=0.0)
    assert not fake.calls


def test_estimate_counts_every_call(tmp_path, monkeypatch):
    from section_anything.isolate import extract_pdf

    exts = [extract_pdf(_sample(tmp_path, n), settings=Settings()) for n in "ab"]
    one = g.estimate_usd(exts, "gpt-6-luna", Settings())
    assert one > 0
    assert g.estimate_usd(exts, "claude-haiku-5-5", Settings()) > one  # Claude's tokenizer counts more
    assert g.estimate_usd(exts, "ollama/granite4:tiny-h", Settings()) == 0
    monkeypatch.setattr(g, "BUDGET_CHARS", 1_500)
    assert g.estimate_usd(exts, "gpt-6-luna", Settings()) > one  # more calls, and a merge


def test_claude_provider(tmp_path, fake, monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    g.write_guidance([_sample(tmp_path, "a"), _sample(tmp_path, "b")], model="claude-haiku-5-5")
    assert fake.calls[0]["model"] == "claude-haiku-5-5"
    assert fake.calls[0]["settings"].provider_for("claude-haiku-5-5") == "anthropic"


def test_refused_before_reading(tmp_path, fake, monkeypatch):
    def no_read(*_a, **_k):
        raise AssertionError("a PDF was read")

    monkeypatch.setattr(g, "extract_pdf", no_read)
    with pytest.raises(ConfigError, match="API key"):
        g.write_guidance([tmp_path / "a.pdf", tmp_path / "b.pdf"])
    with pytest.raises(UnpricedModelError):
        g.write_guidance([tmp_path / "a.pdf", tmp_path / "b.pdf"], model="some-new-model", api_key="sk-test")


def test_cli(tmp_path, fake, monkeypatch, capsys):
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-test")
    a, b, out = _sample(tmp_path, "a"), _sample(tmp_path, "b"), tmp_path / "sheet.md"
    assert main(["guidance", str(a), str(b), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == fake.sheet + "\n"
    assert "sheet: 10 words from 2 samples, 0 model calls" in capsys.readouterr().err
    assert main(["guidance", str(a), str(b)]) == 0
    assert capsys.readouterr().out == fake.sheet + "\n"
    assert main(["guidance", str(a), str(b), "--max-usd", "0"]) == 3
    assert main(["guidance", str(tmp_path / "missing.pdf"), str(b)]) in (2, 4)
    monkeypatch.delenv("SECTIONANY_API_KEY")
    assert main(["guidance", str(a), str(b)]) == 2


def test_guidance_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["guidance", "--help"])
    assert exc.value.code == 0
    assert "represent the documents" in capsys.readouterr().out
