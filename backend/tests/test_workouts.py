"""Tests for the /workouts endpoints.

Each test covers one scenario. The three scenarios every endpoint needs:
  - Happy path: correct data in, correct data out.
  - Auth failure (401): no token or bad token should be rejected.
  - User isolation: user A's data is invisible to user B.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User
from app.models.workout import Workout

pytestmark = pytest.mark.asyncio


# ── Happy path ─────────────────────────────────────────────────────────────────

async def test_create_workout(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/workouts/",
        json={"type": "Run", "date": "2024-01-15", "duration_seconds": 3600, "tss": 65.0},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["type"] == "Run"
    assert data["tss"] == 65.0


async def test_list_workouts(client: AsyncClient, auth_headers: dict, db: AsyncSession, user: User):
    # Seed a workout directly so we're not testing create via list
    db.add(Workout(user_id=user.id, type="Ride", date="2024-01-10", tss=80.0))
    await db.commit()

    resp = await client.get("/workouts/", headers=auth_headers)
    assert resp.status_code == 200
    types = [w["type"] for w in resp.json()]
    assert "Ride" in types


# ── Auth failure ───────────────────────────────────────────────────────────────

async def test_create_workout_requires_auth(client: AsyncClient):
    resp = await client.post("/workouts/", json={"type": "Run"})
    # 403 is what HTTPBearer returns when no Authorization header is present
    assert resp.status_code in (401, 403)


async def test_list_workouts_requires_auth(client: AsyncClient):
    resp = await client.get("/workouts/")
    assert resp.status_code in (401, 403)


# ── User isolation ─────────────────────────────────────────────────────────────

async def test_user_cannot_see_other_users_workouts(
    client: AsyncClient, db: AsyncSession, user: User
):
    """User B's workouts must not appear in user A's list."""
    user_b = User(email="b@example.com", hashed_password=hash_password("pass"))
    db.add(user_b)
    await db.commit()
    await db.refresh(user_b)

    db.add(Workout(user_id=user_b.id, type="Swim", date="2024-01-12"))
    await db.commit()

    # Request as user A
    headers_a = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    resp = await client.get("/workouts/", headers=headers_a)
    assert resp.status_code == 200
    types = [w["type"] for w in resp.json()]
    assert "Swim" not in types


async def test_user_cannot_delete_other_users_workout(
    client: AsyncClient, db: AsyncSession, user: User
):
    user_b = User(email="b2@example.com", hashed_password=hash_password("pass"))
    db.add(user_b)
    await db.commit()
    await db.refresh(user_b)

    workout = Workout(user_id=user_b.id, type="Swim", date="2024-01-13")
    db.add(workout)
    await db.commit()
    await db.refresh(workout)

    headers_a = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    resp = await client.delete(f"/workouts/{workout.id}", headers=headers_a)
    assert resp.status_code == 404  # not 204 — user A sees "not found" not "forbidden"
