"""The MCP server, driven in process through the SDK's own client (no network, free mode only)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp import Client  # noqa: E402

from section_anything.mcp_server import build_server, main  # noqa: E402


def _call(server, tool: str, args: dict):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def test_tools_are_listed_read_only_with_output_schemas():
    async def go():
        async with Client(build_server()) as client:
            return (await client.list_tools()).tools

    tools = {t.name: t for t in asyncio.run(go())}
    assert set(tools) == {"section_pdf", "read_sections", "estimate_cost"}
    for t in tools.values():
        assert t.annotations.read_only_hint is True and t.output_schema
    assert "heading_path" in str(tools["section_pdf"].output_schema)


def test_outline_then_read_sections(paper_pdf):
    server = build_server()
    res = _call(server, "section_pdf", {"path": str(paper_pdf)})
    assert not res.is_error
    data = res.structured_content
    assert data["mode"] == "free" and data["cost_usd"] == 0.0
    assert [s["heading_path"] for s in data["sections"]][2] == ["1 Introduction", "1.1 Scope"]
    assert all("text" not in s for s in data["sections"])

    res = _call(server, "read_sections", {"path": str(paper_pdf), "indexes": [1, 3], "max_chars": 60})
    got = res.structured_content["sections"]
    assert [s["heading_path"] for s in got] == [["1 Introduction"], ["2 Methods"]]
    assert got[0]["text"].startswith("Sectioning splits a long document")  # body only, heading left out
    assert got[0]["truncated"] is True and len(got[0]["text"]) == 60


def test_bad_requests_come_back_as_tool_errors(paper_pdf, tmp_path):
    server = build_server(roots=[tmp_path / "elsewhere"])
    res = _call(server, "section_pdf", {"path": str(paper_pdf)})
    assert res.is_error and "outside the folders" in res.content[0].text

    server = build_server()
    for args, message in [
        ({"path": "paper.pdf"}, "absolute path"),
        ({"path": str(tmp_path / "notes.txt")}, "only .pdf"),
        ({"path": str(tmp_path / "missing.pdf")}, "no such file"),
        ({"path": str(paper_pdf), "mode": "turbo"}, "unknown mode"),
        ({"path": str(paper_pdf), "mode": "quick"}, "API key"),
    ]:
        res = _call(server, "section_pdf", args)
        assert res.is_error and message in res.content[0].text, (args, res.content[0].text)
    res = _call(server, "read_sections", {"path": str(paper_pdf), "indexes": [99]})
    assert res.is_error and "sections 0 to 4" in res.content[0].text


def test_cost_estimate_and_free_only_ceiling(paper_pdf):
    res = _call(build_server(max_usd=0.0), "estimate_cost", {"path": str(paper_pdf)})
    est = res.structured_content
    assert est["pages"] == 2 and est["max_usd"] == 0.0
    by_mode = {m["mode"]: m for m in est["modes"]}
    assert by_mode["free"]["cost_usd"] == 0.0 and not by_mode["free"]["over_cap"]
    assert by_mode["quick"]["model"] == "gpt-6-luna" and by_mode["quick"]["cost_usd"] > 0
    assert by_mode["standard"]["over_cap"] is True
    # A call cannot raise the server's ceiling.
    res = _call(build_server(max_usd=0.1), "estimate_cost", {"path": str(paper_pdf), "max_usd": 5.0})
    assert res.structured_content["max_usd"] == 0.1


def test_main_without_the_extra(monkeypatch, capsys):
    import section_anything.mcp_server as m

    monkeypatch.setattr(m, "MCPServer", None)
    assert main([]) == 2
    assert "pip install 'section-anything[mcp]'" in capsys.readouterr().err
