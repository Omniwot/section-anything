import os
import sys
from pathlib import Path

import pytest

needs_pdf = pytest.mark.skipif(not os.getenv("SECTIONANY_TEST_PDF"),
                               reason="set SECTIONANY_TEST_PDF to a PDF for the end-to-end parse")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Library defaults, whatever the shell has set (the test PDF path excepted)."""
    for key in list(os.environ):
        if key.upper().startswith("SECTIONANY_") and key.upper() != "SECTIONANY_TEST_PDF":
            monkeypatch.delenv(key)


def test_engines_register():
    from lightrag.parser import registry
    from lightrag.parser.plugins import load_third_party_parsers

    load_third_party_parsers(force=True)
    names = {"sectionany", "sectionany_free", "sectionany_quick", "sectionany_standard", "sectionany_local"}
    assert names <= set(registry._REGISTRY)


def test_core_comes_from_the_library_not_the_web_app():
    import lightrag_section_anything.core as core
    import lightrag_section_anything.parser  # noqa: F401

    assert core.section.__module__ == "section_anything.api"
    assert "app" not in sys.modules and "app.sectioning" not in sys.modules


@needs_pdf
def test_free_parse_writes_sidecar(tmp_path):
    from lightrag_section_anything.parser import FreeParser

    src = Path(os.environ["SECTIONANY_TEST_PDF"])
    blocks, warnings, meta = FreeParser().extract(src, parsed_dir=tmp_path, asset_dir=tmp_path / "a", base_name="t")
    assert warnings["sectionany_mode"] == "free" and warnings["sectionany_cost_usd"] == 0
    assert any(b["heading"] for b in blocks)
    seen: list[tuple[int, str]] = []
    for b in blocks:  # parent_headings must be earlier, shallower headings
        if b["level"] > 0:
            for p in b["parent_headings"]:
                assert any(h == p and lv < b["level"] for lv, h in seen)
            seen.append((b["level"], b["heading"]))
    assert (tmp_path / "t.sectionany.json").exists()
    ir = FreeParser().build_ir(blocks, document_name=src.name, asset_dir_name="a", metadata=meta)
    assert ir.document_format == "pdf" and len(ir.blocks) == len(blocks)


@needs_pdf
def test_unpriced_cloud_model_is_refused_before_any_call(monkeypatch):
    from lightrag_section_anything.core import section_pdf

    monkeypatch.setenv("SECTIONANY_QUICK_MODEL", "no-such-model")
    with pytest.raises(ValueError, match="no price for model"):
        section_pdf(Path(os.environ["SECTIONANY_TEST_PDF"]), "quick")


@needs_pdf
def test_file_size_cap(monkeypatch):
    from lightrag_section_anything.parser import FreeParser

    monkeypatch.setenv("SECTIONANY_MAX_MB", "0.001")
    src = Path(os.environ["SECTIONANY_TEST_PDF"])
    with pytest.raises(ValueError, match="SECTIONANY_MAX_MB"):
        FreeParser().validate_source_blocking(src, src.name)


@needs_pdf
def test_page_cap(monkeypatch):
    from lightrag_section_anything.parser import FreeParser

    monkeypatch.setenv("SECTIONANY_MAX_PAGES", "1")
    src = Path(os.environ["SECTIONANY_TEST_PDF"])
    with pytest.raises(ValueError, match="SECTIONANY_MAX_PAGES"):
        FreeParser().validate_source_blocking(src, src.name)


def test_bad_mode_is_a_value_error(tmp_path):
    from lightrag_section_anything.core import section_pdf

    with pytest.raises(ValueError, match="unknown mode"):
        section_pdf(tmp_path / "x.pdf", "turbo")


def test_any_provider_key_makes_the_paid_engines_ready(monkeypatch):
    from lightrag_section_anything import plugin

    for key in plugin.KEYS:
        monkeypatch.delenv(key, raising=False)
    assert not plugin._has_key()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")  # Claude models (SECTIONANY_QUICK_MODEL=claude-...)
    assert plugin._has_key()
