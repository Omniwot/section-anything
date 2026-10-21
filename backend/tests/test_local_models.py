from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.api.v1 import auth
from app.core.config import settings
from app.sectioning.bridge import BrowserBridge
from app.sectioning.llm import Usage, structured


class Out(BaseModel):
    answer: str


async def _browser_answers(bridge: BrowserBridge, replies: list[str]) -> list[dict]:
    """Play the visitor's browser: take each queued prompt and answer it."""
    seen = []
    for reply in replies:
        req = await bridge.next(wait=2)
        assert req is not None
        seen.append(req)
        assert bridge.resolve(req["id"], reply, None)
    return seen


@pytest.mark.asyncio
async def test_browser_model_round_trip() -> None:
    usage = Usage()
    usage.bridge = BrowserBridge()
    call = asyncio.create_task(structured(model="browser/qwen3:4b", system="sys", user="doc", schema=Out,
                                          usage=usage, cost_cap_usd=0.0, step="t"))
    seen = await _browser_answers(usage.bridge, ['{"answer": "yes"}'])
    out = await call
    assert out.answer == "yes"
    assert seen[0]["model"] == "qwen3:4b" and seen[0]["system"] == "sys" and seen[0]["user"] == "doc"
    assert seen[0]["schema"]["properties"]["answer"]["type"] == "string"
    assert usage.cost_usd == 0.0 and usage.calls == 1


@pytest.mark.asyncio
async def test_browser_model_bad_reply_is_retried() -> None:
    usage = Usage()
    usage.bridge = BrowserBridge()
    call = asyncio.create_task(structured(model="browser/m", system="s", user="u", schema=Out, usage=usage,
                                          cost_cap_usd=0.0, step="t"))
    await _browser_answers(usage.bridge, ["not json", '```json\n{"answer": "ok"}\n```'])
    assert (await call).answer == "ok"


@pytest.mark.asyncio
async def test_browser_error_and_unknown_prompt() -> None:
    bridge = BrowserBridge()
    assert not bridge.resolve("nope", "x", None)
    call = asyncio.create_task(bridge.call({"model": "m"}, wait_seconds=2))
    req = await bridge.next(wait=2)
    bridge.resolve(req["id"], None, "connection refused")
    with pytest.raises(RuntimeError, match="local model error"):
        await call


def test_paid_model_access(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PAID_MODELS_FOR", "all")
    assert settings.may_use_paid_models("anyone@example.com")
    monkeypatch.setattr(settings, "PAID_MODELS_FOR", "owner@example.com, other@example.com")
    assert settings.may_use_paid_models("Owner@Example.com")
    assert not settings.may_use_paid_models("visitor@example.com")


def test_failed_login_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    auth._FAILED.clear()
    keys = ("email:a@example.com", "ip:1.2.3.4")
    for _ in range(3):
        assert not auth._too_many(*keys)
        auth._note_failure(*keys)
    assert auth._too_many(*keys)
    assert not auth._too_many("email:b@example.com", "ip:5.6.7.8")
