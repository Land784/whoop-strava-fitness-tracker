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
from app.core.security import decrypt_token, encrypt_token
from app.models.user import User
from app.models.workout import Workout
from app.services.workout_match import find_cross_source_duplicate, merge_into, parse_start

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
    # Encrypt before persisting — the DB only ever holds ciphertext. We decrypt
    # only at the moment we actually call Strava (see sync/refresh below).
    user.strava_access_token = encrypt_token(data["access_token"])
    user.strava_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()


async def refresh_token(user: User, db: AsyncSession) -> str:
    """Refresh the Strava access token using the stored refresh token.

    Returns the new *plaintext* access token so the caller can use it
    immediately; the copy we persist is encrypted.
    """
    if not user.strava_refresh_token:
        raise ValueError("No Strava refresh token stored for this user")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                # Decrypt only to hand it back to Strava in this request.
                "refresh_token": decrypt_token(user.strava_refresh_token),
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        raise ValueError("Strava token refresh failed")

    data = resp.json()
    user.strava_access_token = encrypt_token(data["access_token"])
    user.strava_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()
    return data["access_token"]


async def sync_activities(user: User, db: AsyncSession) -> int:
    """Fetch recent Strava activities and upsert them as Workout rows.
    Returns the number of new activities synced."""
    if not user.strava_access_token:
        raise ValueError("User has not connected Strava")

    # Decrypt the stored token only for the lifetime of this request.
    access = decrypt_token(user.strava_access_token)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access}"},
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

        # Use start_date (UTC) for matching; start_date_local is for the display
        # date. Falling back to local keeps tests/fixtures that only set one.
        started_at = parse_start(activity.get("start_date") or activity.get("start_date_local"))
        fields = {
            "strava_id": strava_id,
            "type": activity.get("sport_type") or activity.get("type"),
            "date": date.fromisoformat(activity["start_date_local"][:10]),
            "started_at": started_at,
            "duration_seconds": activity.get("moving_time"),
            "distance_meters": activity.get("distance"),
            "avg_hr": activity.get("average_heartrate"),
        }

        # If WHOOP already recorded this same session, merge into that row rather
        # than creating a second one. merge_into links both ids and marks it
        # source="both".
        match = await find_cross_source_duplicate(db, user.id, started_at, "strava")
        if match is not None:
            merge_into(match, fields, "strava")
            continue

        db.add(Workout(user_id=user.id, source="strava", **fields))
        synced += 1

    await db.commit()
    return synced
