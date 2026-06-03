"""Tests for Strava activity sync.

We never hit the real Strava API — httpx.AsyncClient is replaced with a fake that
returns canned responses. This keeps tests fast, deterministic, and offline.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_token
from app.models.user import User
from app.models.workout import Workout
from app.services import strava


class FakeResponse:
    def __init__(self, status_code: int, json_data):
        self.status_code = status_code
        self._json = json_data
        self.text = str(json_data)

    def json(self):
        return self._json


class FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    def __init__(self, response: FakeResponse, recorder: dict):
        self._response = response
        self._recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None, params=None):
        # Record the auth header so a test can assert the token was decrypted.
        self._recorder["auth"] = (headers or {}).get("Authorization")
        return self._response


ACTIVITIES = [
    {
        "id": 111, "sport_type": "Run", "start_date_local": "2026-06-01T08:00:00Z",
        "moving_time": 1800, "distance": 5000.0, "average_heartrate": 150,
    },
    {
        "id": 222, "type": "Ride", "start_date_local": "2026-06-02T09:00:00Z",
        "moving_time": 3600, "distance": 20000.0,
    },
]


async def test_sync_inserts_new_then_skips_duplicates(
    db: AsyncSession, user: User, monkeypatch
):
    # The DB stores the token encrypted, exactly as the real flow does.
    user.strava_access_token = encrypt_token("plain_access_token")
    await db.commit()

    recorder: dict = {}
    monkeypatch.setattr(
        strava.httpx,
        "AsyncClient",
        lambda *a, **k: FakeAsyncClient(FakeResponse(200, ACTIVITIES), recorder),
    )

    # First sync inserts both activities.
    assert await strava.sync_activities(user, db) == 2

    # The request used the DECRYPTED token — proves decrypt-on-read works.
    assert recorder["auth"] == "Bearer plain_access_token"

    rows = (
        await db.execute(select(Workout).where(Workout.user_id == user.id))
    ).scalars().all()
    assert {w.strava_id for w in rows} == {"111", "222"}

    # Re-syncing the same activities inserts nothing (upsert by strava_id).
    assert await strava.sync_activities(user, db) == 0


async def test_sync_requires_connection(db: AsyncSession, user: User):
    """With no stored token, the service raises (the router maps this to HTTP)."""
    with pytest.raises(ValueError):
        await strava.sync_activities(user, db)
