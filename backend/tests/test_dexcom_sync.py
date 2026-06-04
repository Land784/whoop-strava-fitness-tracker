"""Tests for Dexcom glucose sync. As with the WHOOP/Strava tests, httpx is
replaced with a routing fake so nothing hits the network. sync_glucose walks the
EGV endpoint in <=30-day chunks and may POST a token refresh on a 401 — the fake
routes by (method, url-substring) and supports a 401-then-200 sequence.

Key behaviours pinned here:
  - first sync backfills 90 days, which the chunking splits into multiple GETs;
  - the (user_id, system_time) upsert is idempotent (a second sync inserts 0);
  - a 401 triggers exactly one refresh + retry;
  - calling without a connected token raises ValueError.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_token
from app.models.glucose import GlucoseReading
from app.models.user import User
from app.services import dexcom


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
    queued 401-then-200 survives the separate AsyncClient() calls sync makes. A
    route with a single response serves it repeatedly (handy: the chunk loop GETs
    the EGV endpoint several times and should get the same payload each time)."""

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
        self._recorder.setdefault("get_params", []).append(params)
        return self._next("GET", url)

    async def post(self, url, data=None):
        self._recorder["refreshed"] = True
        return self._next("POST", url)


def _factory(routes: list, recorder: dict):
    def make(*args, **kwargs):
        return FakeClient(routes, recorder)

    return make


def _egvs(n: int = 3, base: datetime | None = None) -> dict:
    """Build an EGV payload with `n` distinct 5-min readings, anchored a day ago
    so they fall inside the 90-day backfill window. systemTime is UTC with no
    offset, exactly as Dexcom returns it."""
    base = base or (datetime.now(timezone.utc) - timedelta(days=1))
    records = []
    for i in range(n):
        t = base + timedelta(minutes=5 * i)
        records.append(
            {
                "systemTime": t.strftime("%Y-%m-%dT%H:%M:%S"),
                "displayTime": t.strftime("%Y-%m-%dT%H:%M:%S"),
                "value": 100 + i,
                "trend": "flat",
            }
        )
    return {"records": records}


async def test_first_sync_backfills_in_chunks_and_inserts(
    db: AsyncSession, user: User, monkeypatch
):
    user.dexcom_access_token = encrypt_token("dex_plain")
    await db.commit()

    recorder: dict = {}
    routes = [["GET", "/v3/users/self/egvs", [FakeResp(200, _egvs(3))]]]
    monkeypatch.setattr(dexcom.httpx, "AsyncClient", _factory(routes, recorder))

    # 3 distinct readings inserted, even though the same payload is served for
    # every chunk (the upsert dedupes the repeats).
    assert await dexcom.sync_glucose(user, db) == 3
    # The decrypted token was sent.
    assert recorder["auth"][0] == "Bearer dex_plain"
    # 90-day backfill / 30-day chunks => at least 3 GETs (proves chunking).
    assert len(recorder["auth"]) >= 3

    rows = (
        await db.execute(select(GlucoseReading).where(GlucoseReading.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 3
    assert {r.value_mgdl for r in rows} == {100, 101, 102}
    assert all(r.trend == "flat" for r in rows)


async def test_second_sync_is_idempotent(db: AsyncSession, user: User, monkeypatch):
    user.dexcom_access_token = encrypt_token("tok")
    await db.commit()

    routes = [["GET", "/v3/users/self/egvs", [FakeResp(200, _egvs(3))]]]
    monkeypatch.setattr(dexcom.httpx, "AsyncClient", _factory(routes, {}))

    assert await dexcom.sync_glucose(user, db) == 3
    # Same readings re-served (and re-fetched in the overlap window) => 0 new.
    assert await dexcom.sync_glucose(user, db) == 0


async def test_sync_refreshes_on_401(db: AsyncSession, user: User, monkeypatch):
    user.dexcom_access_token = encrypt_token("expired")
    user.dexcom_refresh_token = encrypt_token("refresh_tok")
    await db.commit()

    recorder: dict = {}
    routes = [
        # First EGV GET 401s, then 200 after the refresh; later chunks 200.
        ["GET", "/v3/users/self/egvs", [FakeResp(401, text="expired"), FakeResp(200, _egvs(3))]],
        ["POST", "oauth2/token", [FakeResp(200, {"access_token": "new_access", "refresh_token": "new_refresh"})]],
    ]
    monkeypatch.setattr(dexcom.httpx, "AsyncClient", _factory(routes, recorder))

    assert await dexcom.sync_glucose(user, db) == 3
    assert recorder.get("refreshed") is True
    # The retry used the refreshed access token.
    assert recorder["auth"][-1] == "Bearer new_access"


async def test_sync_requires_connection(db: AsyncSession, user: User):
    with pytest.raises(ValueError):
        await dexcom.sync_glucose(user, db)
