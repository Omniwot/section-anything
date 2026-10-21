import os
from pathlib import Path

import pytest


def test_engines_register():
    from lightrag.parser import registry
    from lightrag.parser.plugins import load_third_party_parsers

    load_third_party_parsers(force=True)
    names = {"sectionany", "sectionany_free", "sectionany_quick", "sectionany_standard", "sectionany_local"}
    assert names <= set(registry._REGISTRY)


@pytest.mark.skipif(not (os.getenv("SECTIONANY_BACKEND") and os.getenv("SECTIONANY_TEST_PDF")),
                    reason="set SECTIONANY_BACKEND and SECTIONANY_TEST_PDF for the end-to-end parse")
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


needs_core = pytest.mark.skipif(not (os.getenv("SECTIONANY_BACKEND") and os.getenv("SECTIONANY_TEST_PDF")),
                                reason="set SECTIONANY_BACKEND and SECTIONANY_TEST_PDF")


@needs_core
def test_unpriced_cloud_model_is_refused_before_any_call(monkeypatch):
    from lightrag_section_anything.core import section_pdf

    monkeypatch.setenv("SECTIONANY_QUICK_MODEL", "no-such-model")
    with pytest.raises(ValueError, match="no price for model"):
        section_pdf(Path(os.environ["SECTIONANY_TEST_PDF"]), "quick")


@needs_core
def test_file_size_cap(monkeypatch):
    from lightrag_section_anything.parser import FreeParser

    monkeypatch.setenv("SECTIONANY_MAX_MB", "0.001")
    src = Path(os.environ["SECTIONANY_TEST_PDF"])
    with pytest.raises(ValueError, match="SECTIONANY_MAX_MB"):
        FreeParser().validate_source_blocking(src, src.name)
