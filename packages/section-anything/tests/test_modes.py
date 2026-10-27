"""quick and standard end to end, with a fake model (no network)."""

from __future__ import annotations

import re
from types import SimpleNamespace

import section_anything
import section_anything.llm as llm
from section_anything.strategies.llm_text import ReviewItem, ReviewResult, TextResult, TextSection


class FakeModel:
    """Answers review and full-text requests from the prompt, like a careful model would."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        self.settings_seen = None

    async def _parse(self, **kwargs):
        self.requests.append(kwargs)
        user = kwargs["messages"][1]["content"]
        schema = kwargs["response_format"]
        if schema is ReviewResult:
            items = []
            for m in re.finditer(r"^(\d+)\| p\d+ \S+ (.*?)  ⟶", user, re.M):
                text = m.group(2)
                num = re.match(r"(\d+(?:\.\d+)*)\s", text)
                level = num.group(1).count(".") + 1 if num else 1
                items.append(ReviewItem(id=int(m.group(1)), is_heading=True, level=level,
                                        number=num.group(1) if num else "", title=""))
            parsed = ReviewResult(items=items)
        else:
            sections = []
            for m in re.finditer(r"^(\d+)\| ⟨H\+\d+⟩⟨B⟩ (.*)$", user, re.M):
                text = m.group(2)
                num = re.match(r"(\d+(?:\.\d+)*)\s+(.*)", text)
                sections.append(TextSection(
                    start_line=int(m.group(1)), number=num.group(1) if num else "",
                    title=num.group(2) if num else text, title_from_text=True,
                    level=num.group(1).count(".") + 1 if num else 1, start_marker=text, end_marker=""))
            parsed = TextResult(sections=sections)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100, prompt_tokens_details=None,
                                completion_tokens_details=None)
        msg = SimpleNamespace(refusal=None, parsed=parsed)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=msg, finish_reason="stop")])

    async def close(self) -> None:
        pass


def _fake(monkeypatch) -> FakeModel:
    fake = FakeModel()

    def client(model, settings):
        fake.settings_seen = settings
        return fake

    monkeypatch.setattr(llm, "_client", client)
    return fake


def test_quick_mode(paper_pdf, monkeypatch):
    fake = _fake(monkeypatch)
    tree = section_anything.section(paper_pdf, "quick", api_key="sk-test", max_usd=0.2)
    assert tree.mode == "quick" and tree.model == "gpt-6-luna"
    assert [(s["number"], s["title"]) for s in tree.sections][1:3] == [("1", "Introduction"), ("1.1", "Scope")]
    assert len(fake.requests) == 1 and fake.requests[0]["model"] == "gpt-6-luna"
    assert fake.settings_seen.max_usd_per_doc == 0.2  # explicit arguments reach the model call
    assert tree.usage["calls"] == 1 and tree.cost_usd == round((1000 * 0.10 + 100 * 0.50) / 1e6, 4)


def test_standard_mode(paper_pdf, monkeypatch):
    fake = _fake(monkeypatch)
    tree = section_anything.section(paper_pdf, "standard", api_key="sk-test")
    assert tree.mode == "standard" and tree.model == "gpt-6-luna"  # the model of the published scores
    assert fake.requests[0]["model"] == "gpt-6-luna"
    assert [s["title"] for s in tree.sections] == ["A Study of Sectioning", "Introduction", "Scope", "Methods",
                                                    "Results"]
    assert [s["level"] for s in tree.sections] == [1, 1, 2, 1, 1]
    assert fake.requests[0]["max_completion_tokens"] == 32_000 and fake.requests[0]["reasoning_effort"] == "low"
    assert "untrusted" in fake.requests[0]["messages"][0]["content"]
