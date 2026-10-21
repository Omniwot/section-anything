"""Entry point for ``lightrag.parsers``: registers one engine per position of the dial.
Import-cheap: implementations load lazily through ``ParserSpec.impl``."""

from __future__ import annotations

import os

IMPL = "lightrag_section_anything.parser:{}"


def _has_key() -> bool:
    return bool(os.getenv("SECTIONANY_API_KEY") or os.getenv("OPENAI_API_KEY"))


def register_parsers() -> None:
    from lightrag.parser.registry import ParserSpec, register_parser

    pdf = frozenset({"pdf"})
    register_parser(ParserSpec(
        engine_name="sectionany", impl=IMPL.format("SectionAnyParser"), suffixes=pdf, queue_group="sectionany",
        concurrency=int(os.getenv("MAX_PARALLEL_PARSE_SECTIONANY", "2"))))
    for mode, cls, ready, need in (
        ("free", "FreeParser", lambda: True, lambda: None),
        ("quick", "QuickParser", _has_key, lambda: "SECTIONANY_API_KEY or OPENAI_API_KEY"),
        ("standard", "StandardParser", _has_key, lambda: "SECTIONANY_API_KEY or OPENAI_API_KEY"),
        ("local", "LocalParser", lambda: bool(os.getenv("SECTIONANY_LOCAL_MODEL")), lambda: "SECTIONANY_LOCAL_MODEL"),
    ):
        register_parser(ParserSpec(
            engine_name=f"sectionany_{mode}", impl=IMPL.format(cls), suffixes=pdf, queue_group="sectionany",
            endpoint_configured=ready, endpoint_requirement=need))
