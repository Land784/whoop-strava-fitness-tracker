"""Strava OAuth and activity sync.

Uses httpx.AsyncClient so network I/O doesn't block the event loop while
waiting on Strava's API. All DB writes happen in the caller's session so
the transaction boundary stays at the router level.
"""

from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.workout import Workout

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


async def exchange_code(code: str, user: User, db: AsyncSession) -> None:
    """Exchange the OAuth authorization code for access + refresh tokens
    and persist them on the user row."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code != 200:
        raise ValueError(f"Strava token exchange failed: {resp.text}")

    data = resp.json()
    # Tokens should be encrypted at rest in production — see core/security.py
    user.strava_access_token = data["access_token"]
    user.strava_refresh_token = data["refresh_token"]
    await db.commit()


async def refresh_token(user: User, db: AsyncSession) -> str:
    """Refresh the Strava access token using the stored refresh token."""
    if not user.strava_refresh_token:
        raise ValueError("No Strava refresh token stored for this user")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "refresh_token": user.strava_refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        raise ValueError("Strava token refresh failed")

    data = resp.json()
    user.strava_access_token = data["access_token"]
    user.strava_refresh_token = data["refresh_token"]
    await db.commit()
    return data["access_token"]


async def sync_activities(user: User, db: AsyncSession) -> int:
    """Fetch recent Strava activities and upsert them as Workout rows.
    Returns the number of new activities synced."""
    if not user.strava_access_token:
        raise ValueError("User has not connected Strava")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {user.strava_access_token}"},
            params={"per_page": 30},
        )

    # 401 means the token has expired — refresh and retry once
    if resp.status_code == 401:
        token = await refresh_token(user, db)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers={"Authorization": f"Bearer {token}"},
                params={"per_page": 30},
            )

    if resp.status_code != 200:
        raise ValueError(f"Strava activities fetch failed: {resp.status_code}")

    activities = resp.json()
    synced = 0

    for activity in activities:
        strava_id = str(activity["id"])

        # Upsert pattern: skip if we already have this activity
        existing = (
            await db.execute(
                select(Workout).where(
                    Workout.user_id == user.id,
                    Workout.strava_id == strava_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            continue

        workout = Workout(
            user_id=user.id,
            strava_id=strava_id,
            type=activity.get("sport_type") or activity.get("type"),
            date=date.fromisoformat(activity["start_date_local"][:10]),
            duration_seconds=activity.get("moving_time"),
            distance_meters=activity.get("distance"),
            avg_hr=activity.get("average_heartrate"),
        )
        db.add(workout)
        synced += 1

    await db.commit()
    return synced
