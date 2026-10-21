from __future__ import annotations

import json

from section_anything.cli import main


def test_cli_markdown_and_json(paper_pdf, capsys):
    assert main([str(paper_pdf), "--format", "md"]) == 0
    out, err = capsys.readouterr()
    assert out.startswith("# A Study of Sectioning\n## 1 Introduction\n")
    assert "5 sections, 2 pages, mode free" in err and "$0.0000" in err

    assert main([str(paper_pdf), "--format", "json", "-q"]) == 0
    out, err = capsys.readouterr()
    data = json.loads(out)
    assert data["mode"] == "free" and len(data["sections"]) == 5 and err == ""


def test_cli_exit_codes(paper_pdf, three_page_pdf, tmp_path, capsys):
    assert main([str(paper_pdf), "--mode", "quick"]) == 2  # no API key
    assert main([str(paper_pdf), "--mode", "quick", "--model", "nope"]) == 2  # unpriced model
    assert main([str(three_page_pdf), "--max-pages", "2"]) == 4
    missing = tmp_path / "missing.pdf"
    assert main([str(missing)]) == 4
    err = capsys.readouterr().err
    assert "no price for model 'nope'" in err and "3 pages; the limit is 2" in err


def test_cli_cost_cap_refusal(paper_pdf, monkeypatch, capsys):
    monkeypatch.setenv("SECTIONANY_API_KEY", "sk-test")
    assert main([str(paper_pdf), "--mode", "standard", "--max-usd", "0.000001", "--over-budget", "fail"]) == 3
    assert "per-document cap" in capsys.readouterr().err
