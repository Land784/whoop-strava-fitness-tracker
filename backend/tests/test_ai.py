"""Tests for the AI layer (services/claude.py + routers/ai.py).

We never hit the real Anthropic API. Unlike the Strava/WHOOP tests — which mock
httpx because those services make raw HTTP calls — the Claude service talks to
Anthropic through the SDK's client object. So we mock at that seam instead:
`anthropic.AsyncAnthropic` is replaced with a fake whose `.messages.create()`
records the kwargs it was called with. That recorder lets us assert the two
things that matter most here:

  - the correct *model* is used per endpoint (cheap Haiku for chat, stronger
    Sonnet for the weekly plan) — this pins down the cost decision so a future
    edit can't silently undo it; and
  - the user's own data reaches the prompt, while another user's data does not.

Plus the trio every endpoint needs: happy path, auth failure (401), isolation.
"""

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models.recovery import RecoveryScore
from app.models.training_plan import TrainingPlan
from app.models.user import User
from app.models.workout import Workout
from app.services import claude

pytestmark = pytest.mark.asyncio


# ── Fake Anthropic SDK ──────────────────────────────────────────────────────────
# The real call is: client = anthropic.AsyncAnthropic(...); msg = await
# client.messages.create(...); return msg.content[0].text. We mirror just enough
# of that shape: a message whose .content[0].text is our canned reply.


class _FakeBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


class _FakeStreamManager:
    """Mirrors the SDK's streaming helper: an async context manager whose
    `.text_stream` is an async iterator of text deltas."""

    def __init__(self, recorder: dict, chunks: list[str]):
        self._recorder = recorder
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    @property
    def text_stream(self):
        return self._aiter()

    async def _aiter(self):
        for chunk in self._chunks:
            yield chunk


class _FakeMessages:
    def __init__(self, recorder: dict, reply: str, chunks: list[str]):
        self._recorder = recorder
        self._reply = reply
        self._chunks = chunks

    async def create(self, **kwargs):
        # Capture everything the service passed (model, system, messages, ...)
        # so a test can assert on it afterwards.
        self._recorder.update(kwargs)
        return _FakeMessage(self._reply)

    def stream(self, **kwargs):
        # Note: .stream() is NOT awaited in the SDK — it returns a context
        # manager synchronously, exactly like the real client.
        self._recorder.update(kwargs)
        return _FakeStreamManager(self._recorder, self._chunks)


class _FakeAnthropic:
    def __init__(self, recorder: dict, reply: str, chunks: list[str]):
        self.messages = _FakeMessages(recorder, reply, chunks)


def install_fake_anthropic(
    monkeypatch,
    reply: str = "Keep it easy today.",
    chunks: list[str] | None = None,
    api_key: str = "test-key",
) -> dict:
    """Patch the SDK + API key inside the claude module and return the recorder.

    We patch `claude.settings.anthropic_api_key` (not the real env) so the
    service's "is AI configured?" guard passes, and swap the SDK constructor
    for one that hands back our fake client. `chunks` are the streamed deltas.
    """
    recorder: dict = {}
    chunks = chunks if chunks is not None else ["You ", "look ", "recovered."]
    monkeypatch.setattr(claude.settings, "anthropic_api_key", api_key)
    monkeypatch.setattr(
        claude.anthropic,
        "AsyncAnthropic",
        lambda *a, **k: _FakeAnthropic(recorder, reply, chunks),
    )
    return recorder


# ── Service: get_insights ───────────────────────────────────────────────────────

async def test_get_insights_uses_chat_model_and_grounds_in_user_data(
    db: AsyncSession, user: User, monkeypatch
):
    db.add(Workout(user_id=user.id, type="Run", date=date(2026, 6, 1), duration_seconds=1800))
    db.add(RecoveryScore(user_id=user.id, date=date(2026, 6, 1), whoop_recovery_score=65.0))
    await db.commit()

    recorder = install_fake_anthropic(monkeypatch, reply="You look recovered — go for it.")

    result = await claude.get_insights("Am I ready to train?", user, db)

    assert result == "You look recovered — go for it."
    # Chat must use the cheap Haiku model, NOT the Sonnet plan model.
    assert recorder["model"] == settings.claude_chat_model
    assert recorder["model"] != settings.claude_model
    # The user's actual data was baked into the system prompt.
    assert "Run" in recorder["system"]
    assert "65.0" in recorder["system"]


async def test_get_insights_requires_api_key(db: AsyncSession, user: User, monkeypatch):
    """No key configured → service raises ValueError (router maps it to 503)."""
    monkeypatch.setattr(claude.settings, "anthropic_api_key", "")
    with pytest.raises(ValueError):
        await claude.get_insights("Anything?", user, db)


async def test_get_insights_excludes_other_users_data(
    db: AsyncSession, user: User, monkeypatch
):
    """The system prompt for user A must never contain user B's workouts."""
    user_b = User(email="b@example.com", hashed_password=hash_password("pass"))
    db.add(user_b)
    await db.commit()
    await db.refresh(user_b)
    db.add(Workout(user_id=user_b.id, type="SecretSwim", date=date(2026, 6, 1)))
    await db.commit()

    recorder = install_fake_anthropic(monkeypatch)
    await claude.get_insights("How am I doing?", user, db)

    assert "SecretSwim" not in recorder["system"]
    assert "No recent workouts." in recorder["system"]


# ── Service: generate_training_plan ─────────────────────────────────────────────

async def test_generate_training_plan_uses_sonnet_and_persists(
    db: AsyncSession, user: User, monkeypatch
):
    db.add(Workout(user_id=user.id, type="Ride", date=date(2026, 6, 1), duration_seconds=3600, distance_meters=20000.0))
    db.add(RecoveryScore(user_id=user.id, date=date(2026, 6, 1), whoop_recovery_score=70.0))
    await db.commit()

    plan_json = '{"days": [], "summary": "easy week"}'
    recorder = install_fake_anthropic(monkeypatch, reply=plan_json)

    plan = await claude.generate_training_plan("2026-06-08", user, db)

    # The plan endpoint keeps the stronger (more expensive) Sonnet model.
    assert recorder["model"] == settings.claude_model
    # The plan was persisted with Claude's output and a context summary.
    assert isinstance(plan, TrainingPlan)
    assert plan.id is not None
    assert plan.user_id == user.id
    assert plan.plan_json == plan_json
    assert plan.prompt_summary is not None


# ── Router: /ai/insights over HTTP ──────────────────────────────────────────────

async def test_insights_endpoint_happy_path(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    install_fake_anthropic(monkeypatch, reply="Prioritise sleep tonight.")

    resp = await client.post(
        "/ai/insights", json={"question": "Any advice?"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["insight"] == "Prioritise sleep tonight."


async def test_insights_requires_auth(client: AsyncClient):
    resp = await client.post("/ai/insights", json={"question": "Hi"})
    # HTTPBearer returns 403 when the Authorization header is missing entirely.
    assert resp.status_code in (401, 403)


async def test_insights_returns_503_when_unconfigured(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """With no API key, the service raises and the router maps it to 503."""
    monkeypatch.setattr(claude.settings, "anthropic_api_key", "")
    resp = await client.post(
        "/ai/insights", json={"question": "Hi"}, headers=auth_headers
    )
    assert resp.status_code == 503


# ── Router: /ai/chat (streaming, multi-turn) ────────────────────────────────────

async def test_chat_streams_chunks_as_sse(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    recorder = install_fake_anthropic(monkeypatch, chunks=["Hello ", "there!"])

    resp = await client.post(
        "/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # Each chunk arrives as its own JSON-encoded SSE frame, then a [DONE] marker.
    assert 'data: {"text": "Hello "}' in body
    assert 'data: {"text": "there!"}' in body
    assert "data: [DONE]" in body
    # Chat streaming uses the cheap Haiku model, same as the non-streaming path.
    assert recorder["model"] == settings.claude_chat_model


async def test_chat_passes_full_history_for_memory(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """The whole conversation is forwarded to Claude — that's how it 'remembers'."""
    recorder = install_fake_anthropic(monkeypatch)
    history = [
        {"role": "user", "content": "I ran 5k yesterday"},
        {"role": "assistant", "content": "Nice, how did it feel?"},
        {"role": "user", "content": "Pretty tired. Should I rest?"},
    ]

    resp = await client.post("/ai/chat", json={"messages": history}, headers=auth_headers)

    assert resp.status_code == 200
    assert recorder["messages"] == history


async def test_chat_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert resp.status_code in (401, 403)


async def test_chat_rejects_history_not_ending_in_user_turn(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """Claude requires the last turn to be the user's — reject otherwise (400)."""
    install_fake_anthropic(monkeypatch)
    resp = await client.post(
        "/ai/chat",
        json={"messages": [{"role": "assistant", "content": "hi"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


async def test_chat_returns_503_when_unconfigured(
    client: AsyncClient, auth_headers: dict, monkeypatch
):
    """No API key → 503 up front, before any streaming begins."""
    monkeypatch.setattr(claude.settings, "anthropic_api_key", "")
    resp = await client.post(
        "/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 503
