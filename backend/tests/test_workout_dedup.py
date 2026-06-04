"""Cross-source workout de-duplication.

Drives the *real* Strava and WHOOP sync functions (httpx faked) against the same
user, with a Strava activity and a WHOOP workout that start within the match
window — and asserts they collapse into a single merged row (source="both")
with the field-aware values: Strava distance/duration/type, WHOOP heart rate.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import encrypt_token
from app.models.user import User
from app.models.workout import Workout
from app.services import strava, whoop

pytestmark = pytest.mark.asyncio


class FakeResp:
    def __init__(self, status_code: int, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = str(json_data)

    def json(self):
        return self._json


class FakeClient:
    """httpx.AsyncClient stand-in that routes by URL substring.

    Both services do `import httpx`, so strava.httpx and whoop.httpx are the
    SAME module object — patching AsyncClient once covers both, and a single
    fake must answer for both endpoints (/athlete/activities and
    /activity/workout). Routing by URL is how one client serves both.
    """

    def __init__(self, routes: list[tuple[str, FakeResp]]):
        self._routes = routes

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None, params=None):
        for substr, resp in self._routes:
            if substr in url:
                return resp
        raise AssertionError(f"no fake route for {url}")


def _factory(routes: list[tuple[str, FakeResp]]):
    return lambda *a, **k: FakeClient(routes)


# Same physical run: WHOOP detects start 08:00:00, Strava records 08:02:00.
# Two minutes apart → inside the 5-minute match window.
STRAVA_ACT = {
    "id": 555,
    "sport_type": "Run",
    "start_date": "2026-06-01T08:02:00Z",
    "start_date_local": "2026-06-01T08:02:00Z",
    "moving_time": 2600,
    "distance": 9500.0,
    "average_heartrate": 148,
}
WHOOP_WK = {
    "records": [
        {
            "id": "whoop-run",
            "score_state": "SCORED",
            "sport_name": "running",
            "start": "2026-06-01T08:00:00.000Z",
            "end": "2026-06-01T08:45:00.000Z",
            "score": {"average_heart_rate": 152, "distance_meter": 9000.0},
        }
    ]
}


async def _connect(db: AsyncSession, user: User) -> None:
    user.strava_access_token = encrypt_token("s")
    user.whoop_access_token = encrypt_token("w")
    await db.commit()


def _both_clients(monkeypatch, whoop_records=WHOOP_WK) -> None:
    # One patch on the shared httpx module; the fake routes per endpoint.
    routes = [
        ("/athlete/activities", FakeResp(200, [STRAVA_ACT])),
        ("/activity/workout", FakeResp(200, whoop_records)),
    ]
    monkeypatch.setattr(strava.httpx, "AsyncClient", _factory(routes))


async def _assert_single_merged_row(db: AsyncSession, user: User) -> None:
    rows = (
        await db.execute(select(Workout).where(Workout.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 1
    w = rows[0]
    assert w.source == "both"
    assert w.strava_id == "555"
    assert w.whoop_id == "whoop-run"
    # Field-aware merge: Strava wins distance/duration/type; WHOOP wins avg_hr.
    assert w.distance_meters == 9500.0
    assert w.duration_seconds == 2600
    assert w.type == "Run"
    assert w.avg_hr == 152


async def test_strava_then_whoop_merges(db: AsyncSession, user: User, monkeypatch):
    await _connect(db, user)
    _both_clients(monkeypatch)

    assert await strava.sync_activities(user, db) == 1  # inserts the Strava row
    assert await whoop.sync_workouts(user, db) == 0     # merges → no new row
    await _assert_single_merged_row(db, user)


async def test_whoop_then_strava_merges(db: AsyncSession, user: User, monkeypatch):
    """Order-independent: same result if WHOOP syncs first."""
    await _connect(db, user)
    _both_clients(monkeypatch)

    assert await whoop.sync_workouts(user, db) == 1     # inserts the WHOOP row
    assert await strava.sync_activities(user, db) == 0  # merges → no new row
    await _assert_single_merged_row(db, user)


async def test_distant_starts_do_not_merge(db: AsyncSession, user: User, monkeypatch):
    """A WHOOP workout hours away from the Strava one stays a separate row."""
    whoop_late = {
        "records": [
            dict(
                WHOOP_WK["records"][0],
                start="2026-06-01T15:00:00.000Z",
                end="2026-06-01T15:45:00.000Z",
            )
        ]
    }
    await _connect(db, user)
    _both_clients(monkeypatch, whoop_records=whoop_late)

    assert await strava.sync_activities(user, db) == 1
    assert await whoop.sync_workouts(user, db) == 1  # no match → new row
    count = (
        await db.execute(
            select(func.count()).select_from(Workout).where(Workout.user_id == user.id)
        )
    ).scalar()
    assert count == 2


async def test_resync_is_idempotent(db: AsyncSession, user: User, monkeypatch):
    """Re-running both syncs after a merge adds nothing and never re-merges."""
    await _connect(db, user)
    _both_clients(monkeypatch)
    await strava.sync_activities(user, db)
    await whoop.sync_workouts(user, db)

    assert await strava.sync_activities(user, db) == 0
    assert await whoop.sync_workouts(user, db) == 0
    await _assert_single_merged_row(db, user)
