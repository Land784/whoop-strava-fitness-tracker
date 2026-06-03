"""Tests for WHOOP recovery+sleep sync. httpx is replaced with a routing fake so
nothing hits the network. sync_recovery calls /recovery and /activity/sleep, and
may POST a token refresh on a 401 — the fake routes by (method, url-substring)
and supports a 401-then-200 sequence.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_token
from app.models.recovery import RecoveryScore
from app.models.user import User
from app.services import whoop


class FakeResp:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    def json(self):
        return self._json


class FakeClient:
    """Stand-in for httpx.AsyncClient. `routes` is a list of
    [method, url-substring, [responses...]] shared across client instances, so a
    queued 401-then-200 survives the separate AsyncClient() calls sync makes."""

    def __init__(self, routes: list, recorder: dict):
        self._routes = routes
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def _next(self, method: str, url: str):
        for m, sub, responses in self._routes:
            if m == method and sub in url:
                return responses.pop(0) if len(responses) > 1 else responses[0]
        raise AssertionError(f"unexpected {method} {url}")

    async def get(self, url, headers=None, params=None):
        self._recorder.setdefault("auth", []).append((headers or {}).get("Authorization"))
        return self._next("GET", url)

    async def post(self, url, data=None):
        self._recorder["refreshed"] = True
        return self._next("POST", url)


def _factory(routes: list, recorder: dict):
    def make(*args, **kwargs):
        return FakeClient(routes, recorder)

    return make


RECOVERIES = {
    "records": [
        {
            "sleep_id": "sleep-1", "score_state": "SCORED",
            "created_at": "2026-06-01T13:00:00.000Z",
            "score": {"recovery_score": 78, "hrv_rmssd_milli": 62.5, "resting_heart_rate": 48},
        },
        {
            "sleep_id": "sleep-2", "score_state": "PENDING_SCORE",
            "created_at": "2026-06-02T13:00:00.000Z", "score": {},
        },
    ]
}
SLEEPS = {
    "records": [
        {"id": "sleep-1", "score_state": "SCORED",
         "score": {"sleep_performance_percentage": 91.0}},
    ]
}


async def test_sync_inserts_scored_correlates_sleep_skips_unscored(
    db: AsyncSession, user: User, monkeypatch
):
    user.whoop_access_token = encrypt_token("whoop_plain")
    await db.commit()

    recorder: dict = {}
    routes = [
        ["GET", "/recovery", [FakeResp(200, RECOVERIES)]],
        ["GET", "/activity/sleep", [FakeResp(200, SLEEPS)]],
    ]
    monkeypatch.setattr(whoop.httpx, "AsyncClient", _factory(routes, recorder))

    # Only the SCORED record is inserted; the PENDING one is skipped.
    assert await whoop.sync_recovery(user, db) == 1
    # The decrypted token was sent.
    assert recorder["auth"][0] == "Bearer whoop_plain"

    row = (
        await db.execute(select(RecoveryScore).where(RecoveryScore.user_id == user.id))
    ).scalar_one()
    assert row.whoop_recovery_score == 78
    assert row.hrv_ms == 62.5
    assert row.resting_hr == 48
    assert row.sleep_score == 91.0  # joined from /sleep via sleep_id


async def test_sync_skips_duplicates(db: AsyncSession, user: User, monkeypatch):
    user.whoop_access_token = encrypt_token("tok")
    await db.commit()

    routes = [
        ["GET", "/recovery", [FakeResp(200, RECOVERIES)]],
        ["GET", "/activity/sleep", [FakeResp(200, SLEEPS)]],
    ]
    monkeypatch.setattr(whoop.httpx, "AsyncClient", _factory(routes, {}))

    assert await whoop.sync_recovery(user, db) == 1
    assert await whoop.sync_recovery(user, db) == 0  # upsert by (user_id, date)


async def test_sync_refreshes_on_401(db: AsyncSession, user: User, monkeypatch):
    user.whoop_access_token = encrypt_token("expired")
    user.whoop_refresh_token = encrypt_token("refresh_tok")
    await db.commit()

    recorder: dict = {}
    routes = [
        # /recovery: 401 first, then 200 after the refresh.
        ["GET", "/recovery", [FakeResp(401, text="expired"), FakeResp(200, RECOVERIES)]],
        ["GET", "/activity/sleep", [FakeResp(200, SLEEPS)]],
        ["POST", "oauth2/token", [FakeResp(200, {"access_token": "new_access", "refresh_token": "new_refresh"})]],
    ]
    monkeypatch.setattr(whoop.httpx, "AsyncClient", _factory(routes, recorder))

    assert await whoop.sync_recovery(user, db) == 1
    assert recorder.get("refreshed") is True
    # The retry used the refreshed access token.
    assert recorder["auth"][-1] == "Bearer new_access"


async def test_sync_requires_connection(db: AsyncSession, user: User):
    with pytest.raises(ValueError):
        await whoop.sync_recovery(user, db)
