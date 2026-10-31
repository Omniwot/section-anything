"""Batch mode: `section_many` and the command line's folder mode. No network: paid runs use a fake
model, or caps so small that the estimate alone downgrades or refuses them."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_modes import _fake

import section_anything
import section_anything.api as api
import section_anything.llm as llm
from section_anything import (
    ConfigError,
    CostCapExceeded,
    DocumentResult,
    LlmCallFailed,
    PdfError,
    Settings,
    asection_many,
    section_many,
)
from section_anything.cli import main, plan_outputs
from section_anything.pipeline import BY_ID

CALL_USD = (1000 * 0.10 + 100 * 0.50) / 1e6  # one fake call on gpt-6-luna: 1,000 tokens in, 100 out


@pytest.fixture
def bad_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf at all")
    return path


@pytest.fixture
def no_extraction(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("the PDF was read")

    monkeypatch.setattr(api, "extract_pdf", refuse)


def copies(pdf: Path, folder: Path, *names: str) -> list[Path]:
    out = []
    for name in names:
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        out.append(Path(shutil.copy(pdf, folder / name)))
    return out


def quick_estimate(pdf: Path) -> float:
    """What quick mode on gpt-6-luna is estimated to cost for this PDF, before it runs."""
    s = Settings()
    ext = api.extract_pdf(pdf, settings=s)
    est = BY_ID["llm_review"].estimate(ext, "gpt-6-luna", s)
    return s.price_for("gpt-6-luna").estimate(est.input_tokens, est.output_tokens, est.calls)


# Python API


def test_results_for_each_pdf_with_errors_recorded(paper_pdf, three_page_pdf, bad_pdf, tmp_path):
    missing = tmp_path / "missing.pdf"
    results = section_many([paper_pdf, bad_pdf, str(three_page_pdf), missing])
    assert iter(results) is results  # an iterator: documents run as results are asked for
    results = list(results)
    assert all(isinstance(r, DocumentResult) for r in results)
    assert [r.path for r in results] == [paper_pdf, bad_pdf, three_page_pdf, missing]
    assert [r.ok for r in results] == [True, False, True, False]
    good = results[0]
    assert good.error is None and len(good.tree.sections) == 5 and good.tree.mode == "free"
    assert good.cost_usd == 0.0 and good.max_usd == 0.50
    bad = results[1]
    assert bad.tree is None and isinstance(bad.error, PdfError) and "could not be opened" in str(bad.error)
    assert isinstance(results[3].error, PdfError) and "missing.pdf" in str(results[3].error)


def test_on_error_raise_stops_at_the_first_error(paper_pdf, bad_pdf):
    it = section_many([paper_pdf, bad_pdf, paper_pdf], on_error="raise")
    assert next(it).ok
    with pytest.raises(PdfError, match="could not be opened"):
        next(it)
    assert list(it) == []  # the run is over


def test_configuration_errors_are_raised_not_recorded(paper_pdf, no_extraction):
    with pytest.raises(ConfigError, match="needs an API key"):
        list(section_many([paper_pdf, paper_pdf], "quick"))  # recorded errors would read both PDFs
    with pytest.raises(ConfigError, match="unknown mode"):
        section_many([paper_pdf], "turbo")  # at the call, before iterating
    with pytest.raises(ConfigError, match="on_error"):
        section_many([paper_pdf], on_error="ignore")
    with pytest.raises(ConfigError, match="max_usd_total"):
        section_many([paper_pdf], max_usd_total=-1)
    with pytest.raises(TypeError, match="list of paths"):
        section_many(str(paper_pdf))


def test_total_budget_lowers_each_documents_cap(paper_pdf, tmp_path, monkeypatch):
    pdfs = copies(paper_pdf, tmp_path, "a.pdf", "b.pdf", "c.pdf")
    estimate = quick_estimate(paper_pdf)
    assert estimate > CALL_USD  # the fake spends less than the estimate
    total = estimate + CALL_USD / 2  # pays for the first document's estimate, not the second's
    fake = _fake(monkeypatch)
    results = list(section_many(pdfs, "quick", api_key="sk-test", max_usd_total=total))
    assert [r.tree.mode for r in results] == ["quick", "free", "free"]
    assert len(fake.requests) == 1
    assert results[0].max_usd == pytest.approx(total) and results[0].cost_usd == pytest.approx(CALL_USD)
    assert results[1].max_usd == pytest.approx(total - CALL_USD)  # what is left after the first
    assert results[1].tree.downgraded[0].startswith("quick: estimated") and results[1].cost_usd == 0.0
    assert sum(r.cost_usd for r in results) <= total


def test_total_budget_with_over_budget_fail(paper_pdf, tmp_path, monkeypatch):
    pdfs = copies(paper_pdf, tmp_path, "a.pdf", "b.pdf")
    total = quick_estimate(paper_pdf) + CALL_USD / 2
    _fake(monkeypatch)
    first, second = section_many(pdfs, "quick", api_key="sk-test", max_usd_total=total, over_budget="fail")
    assert first.ok and first.tree.mode == "quick"
    assert isinstance(second.error, CostCapExceeded) and second.tree is None
    assert "what was left of the" in str(second.error) and "--max-usd-total" in str(second.error)
    with pytest.raises(CostCapExceeded, match="total budget"):
        list(section_many(pdfs, "quick", api_key="sk-test", max_usd_total=total, over_budget="fail",
                          on_error="raise"))


def test_spent_budget_refuses_without_reading(paper_pdf, three_page_pdf, no_extraction):
    results = list(section_many([paper_pdf, three_page_pdf], "standard", api_key="sk-test", max_usd_total=0,
                                over_budget="fail"))
    assert all(isinstance(r.error, CostCapExceeded) for r in results)
    assert "total budget is spent" in str(results[0].error) and "was not read" in str(results[0].error)


def test_per_document_cap_still_applies(paper_pdf):
    # No total: max_usd passes through. With a larger total, the smaller per-document cap wins.
    (r,) = section_many([paper_pdf], "standard", api_key="sk-test", max_usd=0.000001)
    assert r.max_usd == 0.000001 and r.tree.mode == "free" and r.tree.downgraded
    (r,) = section_many([paper_pdf], "standard", api_key="sk-test", max_usd_total=1.0,
                        settings=Settings(max_usd_per_doc=0.000002))
    assert r.max_usd == 0.000002 and r.tree.mode == "free"
    (r,) = section_many([paper_pdf], "standard", api_key="sk-test", max_usd_total=0.000003)
    assert r.max_usd == 0.000003 and [d.split(":")[0] for d in r.tree.downgraded] == ["standard", "quick"]


def test_free_mode_never_spends(paper_pdf, three_page_pdf):
    results = list(section_many([paper_pdf, three_page_pdf], max_usd_total=0))
    assert all(r.ok and r.cost_usd == 0.0 and r.max_usd == 0.0 for r in results)


class Unusable:
    """A model that answers (and is paid) but never with a parsable result."""

    def __init__(self) -> None:
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **_kwargs):
        self.calls += 1
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100, prompt_tokens_details=None,
                                completion_tokens_details=None)
        msg = SimpleNamespace(refusal=None, parsed=None)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg, finish_reason="length")])

    async def close(self) -> None:
        pass


def test_spending_of_a_failed_document_counts(paper_pdf, three_page_pdf, monkeypatch):
    fake = Unusable()
    monkeypatch.setattr(llm, "_client", lambda model, s: fake)
    first, second = section_many([paper_pdf, three_page_pdf], "quick", api_key="sk-test", max_usd_total=0.01)
    assert isinstance(first.error, LlmCallFailed) and fake.calls >= 2
    assert first.cost_usd == pytest.approx(2 * CALL_USD)  # two paid attempts, then the error
    assert second.max_usd == pytest.approx(0.01 - 2 * CALL_USD)


def test_progress_covers_the_whole_run(paper_pdf, three_page_pdf):
    seen: list[tuple[float, str]] = []
    list(section_many([paper_pdf, three_page_pdf], progress=lambda f, m: seen.append((f, m))))
    fractions = [f for f, _ in seen]
    assert fractions == sorted(fractions) and 0 <= fractions[0] and fractions[-1] <= 1
    assert seen[0][1].startswith("paper.pdf (1 of 2): ") and seen[-1][1].startswith("three.pdf (2 of 2): ")
    assert any(f >= 0.5 for f, m in seen if m.startswith("three.pdf"))


def test_async_variant(paper_pdf, bad_pdf):
    async def collect():
        return [r async for r in asection_many([paper_pdf, bad_pdf])]

    good, bad = asyncio.run(collect())
    assert good.ok and len(good.tree.sections) == 5 and isinstance(bad.error, PdfError)
    assert section_anything.section_many is section_many


# Command line


def test_cli_folder_writes_one_output_per_pdf(paper_pdf, three_page_pdf, tmp_path, capsys):
    docs, out = tmp_path / "docs", tmp_path / "out"
    copies(paper_pdf, docs, "a.pdf", ".hidden.pdf", "sub/c.pdf")
    copies(three_page_pdf, docs, "b.PDF")
    (docs / "notes.txt").write_text("not a pdf")
    assert main([str(docs), "-o", str(out)]) == 0
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == ["a.md", "b.md"]
    assert (out / "a.md").read_text() == section_anything.section(paper_pdf).to_markdown()
    err = capsys.readouterr().err.splitlines()
    assert err[0].startswith(f"[1/2] {docs / 'a.pdf'}: 5 sections, 2 pages, mode free")
    assert err[0].endswith(f"-> {out / 'a.md'}")
    assert err[-1].startswith("2 PDFs: 2 done, 0 failed, 0 skipped; 0 model calls, $0.0000")

    assert main([str(docs), "-o", str(out), "--format", "json", "--body", "-q"]) == 0
    data = json.loads((out / "a.json").read_text())
    assert len(data["sections"]) == 5 and "text" in data["sections"][0]
    assert capsys.readouterr().err == ""


def test_cli_recursive_keeps_subfolders(paper_pdf, tmp_path):
    docs, out = tmp_path / "docs", tmp_path / "out"
    copies(paper_pdf, docs, "x.pdf", "sub/x.pdf", "sub/deeper/y.pdf")
    assert main([str(docs), "-o", str(out), "--recursive", "-q"]) == 0
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*.md")) == [
        "sub/deeper/y.md", "sub/x.md", "x.md"]


def test_cli_several_pdfs_with_the_same_name(paper_pdf, tmp_path):
    a, b = copies(paper_pdf, tmp_path, "a/x.pdf", "b/x.pdf")
    out = tmp_path / "out"
    assert main([str(a), str(b), str(a), "-o", str(out), "-q"]) == 0  # each PDF once
    assert sorted(p.name for p in out.iterdir()) == ["x-2.md", "x.md"]
    # Names that differ only in case clash too, and a renamed output never takes another PDF's name.
    plan = plan_outputs([Path("d1/x.pdf"), Path("d2/X.PDF"), Path("d3/x-2.pdf")], Path("o"), "json")
    assert [t.as_posix() for _, t in plan] == ["o/x.json", "o/X-3.json", "o/x-2.json"]


def test_cli_skip_existing_resumes(paper_pdf, bad_pdf, tmp_path, capsys):
    docs, out = tmp_path / "docs", tmp_path / "out"
    copies(paper_pdf, docs, "a.pdf", "b.pdf")
    shutil.copy(bad_pdf, docs / "c.pdf")
    assert main([str(docs), "-o", str(out), "-q"]) == 4
    assert not (out / "c.md").exists()  # a failed PDF leaves no output, so a resumed run retries it
    (out / "a.md").write_text("kept")
    capsys.readouterr()
    assert main([str(docs), "-o", str(out), "--skip-existing"]) == 4
    err = capsys.readouterr().err
    assert (out / "a.md").read_text() == "kept"
    assert f"{docs / 'a.pdf'}: skipped, {out / 'a.md'} exists" in err
    assert "[1/1]" in err and "3 PDFs: 0 done, 1 failed, 2 skipped" in err
    assert main([str(docs), "-o", str(out), "-q"]) == 4
    assert (out / "a.md").read_text() != "kept"  # without the flag, outputs are rewritten


def test_cli_partial_failure_exit_code(paper_pdf, bad_pdf, tmp_path, capsys):
    out = tmp_path / "out"
    assert main([str(paper_pdf), str(bad_pdf), "-o", str(out)]) == 4
    assert (out / "paper.md").exists() and not (out / "bad.md").exists()
    err = capsys.readouterr().err
    assert f"[2/2] {bad_pdf}: failed, PdfError: PDF could not be opened" in err
    assert "2 PDFs: 1 done, 1 failed, 0 skipped" in err


def test_cli_total_budget(paper_pdf, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-test")
    docs, out = tmp_path / "docs", tmp_path / "out"
    copies(paper_pdf, docs, "a.pdf", "b.pdf")
    assert main([str(docs), "-o", str(out), "--mode", "standard", "--max-usd-total", "0.000001"]) == 0
    err = capsys.readouterr().err
    assert err.count("mode free") == 2 and "downgraded: standard" in err
    assert "$0.0000 of the $0.00 total cap" in err
    assert main([str(docs), "-o", str(out), "--mode", "standard", "--max-usd-total", "0", "--over-budget",
                 "fail"]) == 4
    assert "total budget is spent" in capsys.readouterr().err


def test_cli_folder_mode_arguments(paper_pdf, tmp_path, capsys):
    docs = tmp_path / "docs"
    copies(paper_pdf, docs, "a.pdf")
    assert main([str(docs)]) == 2  # no -o
    (tmp_path / "file").write_text("")
    assert main([str(docs), "-o", str(tmp_path / "file")]) == 2
    assert main([str(paper_pdf), "--recursive", "--max-usd-total", "1"]) == 2  # folder-mode flags, one PDF
    assert main([str(docs), "-o", str(tmp_path / "out"), "--mode", "quick"]) == 2  # no API key
    assert main([str(docs), "-o", str(tmp_path / "out"), "--max-usd-total", "-1"]) == 2
    assert not (tmp_path / "out").exists()
    err = capsys.readouterr().err
    assert "need -o/--output DIR" in err and "not a folder" in err and "only for a folder" in err
    assert "needs an API key" in err
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty), "-o", str(tmp_path / "out")]) == 0
    assert "0 PDFs: 0 done" in capsys.readouterr().err


def test_cli_single_file_is_unchanged(paper_pdf, tmp_path, capsys):
    target = tmp_path / "paper.md"
    assert main([str(paper_pdf), "-o", str(target)]) == 0
    out, err = capsys.readouterr()
    assert out == "" and target.read_text().startswith("# A Study of Sectioning\n")
    assert err.startswith("5 sections, 2 pages, mode free") and err.count("\n") == 1
