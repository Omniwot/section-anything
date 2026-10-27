from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from section_anything.config import Settings
from section_anything.extract import Extraction
from section_anything.llm import Usage


@dataclass
class RawSection:
    """What a strategy proposes; the pipeline resolves and validates it."""

    title: str
    level: int
    number: str = ""
    start_marker: str = ""
    end_marker: str = ""
    start_line: int | None = None  # global line index hint
    title_from_text: bool = True


@dataclass
class Context:
    model: str
    usage: Usage
    cost_cap_usd: float
    progress: Callable[[float, str], None] = field(default=lambda _f, _m: None)
    settings: Settings | None = None  # None: Settings() from the environment


@dataclass
class Estimate:
    input_tokens: int
    output_tokens: int
    calls: int


class Strategy:
    id: str = ""
    label: str = ""
    description: str = ""
    uses_llm: bool = False
    effort: str | None = "low"

    async def run(self, ext: Extraction, ctx: Context) -> list[RawSection]:
        raise NotImplementedError

    def estimate(self, ext: Extraction, model: str = "", settings: Settings | None = None) -> Estimate:
        """Expected calls and tokens for `ext` on `model` (token counts depend on the model's provider;
        no model: OpenAI's)."""
        return Estimate(0, 0, 0)
