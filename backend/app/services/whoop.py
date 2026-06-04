"""WHOOP OAuth (confidential client) and recovery/sleep sync.

Mirrors the Strava service: tokens are stored encrypted and decrypted only at the
moment we call WHOOP, and a 401 triggers a one-time refresh + retry. WHOOP access
tokens expire ~hourly, so we request the `offline` scope (in the authorize URL)
which is what makes WHOOP return a refresh token in the first place.

Targets the WHOOP v2 API. Sleep performance lives on the sleep records, not the
recovery records, so we fetch both and join them on the recovery's `sleep_id`.
"""

from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.models.recovery import RecoveryScore
from app.models.user import User
from app.models.workout import Workout
from app.services.workout_match import find_cross_source_duplicate, merge_into, parse_start

WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"


async def exchange_code(code: str, user: User, db: AsyncSession) -> None:
    """Exchange the authorization code for WHOOP tokens; store them encrypted."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            WHOOP_TOKEN_URL,
            data={
                "client_id": settings.whoop_client_id,
                "client_secret": settings.whoop_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.whoop_redirect_uri,
            },
        )

    if resp.status_code != 200:
        raise ValueError(f"WHOOP token exchange failed: {resp.text}")

    data = resp.json()
    user.whoop_access_token = encrypt_token(data["access_token"])
    # The refresh token is only returned when the `offline` scope was requested.
    if data.get("refresh_token"):
        user.whoop_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()


async def refresh_token(user: User, db: AsyncSession) -> str:
    """Refresh the WHOOP access token. Returns the new *plaintext* access token
    for immediate use; the persisted copy is encrypted."""
    if not user.whoop_refresh_token:
        raise ValueError("No WHOOP refresh token stored for this user")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            WHOOP_TOKEN_URL,
            data={
                "client_id": settings.whoop_client_id,
                "client_secret": settings.whoop_client_secret,
                "refresh_token": decrypt_token(user.whoop_refresh_token),
                "grant_type": "refresh_token",
                # Re-request `offline` so WHOOP keeps issuing a refresh token.
                "scope": "offline",
            },
        )

    if resp.status_code != 200:
        raise ValueError("WHOOP token refresh failed")

    data = resp.json()
    user.whoop_access_token = encrypt_token(data["access_token"])
    if data.get("refresh_token"):
        user.whoop_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()
    return data["access_token"]


async def _get(path: str, token: str, params: dict) -> httpx.Response:
    """GET a WHOOP v2 endpoint with the given bearer token."""
    async with httpx.AsyncClient() as client:
        return await client.get(
            f"{WHOOP_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )


async def sync_recovery(user: User, db: AsyncSession) -> int:
    """Fetch recent WHOOP recovery + sleep and upsert RecoveryScore rows.
    Returns the number of new rows added."""
    if not user.whoop_access_token:
        raise ValueError("User has not connected WHOOP")

    token = decrypt_token(user.whoop_access_token)

    resp = await _get("/recovery", token, {"limit": 25})
    # 401 -> the access token expired; refresh once and retry.
    if resp.status_code == 401:
        token = await refresh_token(user, db)
        resp = await _get("/recovery", token, {"limit": 25})
    if resp.status_code != 200:
        raise ValueError(f"WHOOP recovery fetch failed: {resp.status_code}")
    recoveries = resp.json().get("records", [])

    # Sleep performance lives on sleep records — build sleep_id -> performance.
    # Best-effort: if the sleep call fails, recoveries still sync (sleep null).
    sleep_perf: dict[str, float | None] = {}
    sleep_resp = await _get("/activity/sleep", token, {"limit": 25})
    if sleep_resp.status_code == 200:
        for s in sleep_resp.json().get("records", []):
            sleep_perf[s["id"]] = (s.get("score") or {}).get("sleep_performance_percentage")

    synced = 0
    for rec in recoveries:
        # WHOOP marks records SCORED / PENDING_SCORE / UNSCORABLE — skip the
        # ones it hasn't finished scoring.
        if rec.get("score_state") != "SCORED":
            continue

        record_date = date.fromisoformat(rec["created_at"][:10])
        score = rec.get("score") or {}

        existing = (
            await db.execute(
                select(RecoveryScore).where(
                    RecoveryScore.user_id == user.id,
                    RecoveryScore.date == record_date,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        db.add(
            RecoveryScore(
                user_id=user.id,
                date=record_date,
                whoop_recovery_score=score.get("recovery_score"),
                hrv_ms=score.get("hrv_rmssd_milli"),
                resting_hr=score.get("resting_heart_rate"),
                sleep_score=sleep_perf.get(rec.get("sleep_id")),
            )
        )
        synced += 1

    await db.commit()
    return synced


async def sync_workouts(user: User, db: AsyncSession) -> int:
    """Fetch recent WHOOP workouts and upsert them as Workout rows.
    Returns the number of new rows added (merges into an existing Strava row
    don't count as new).

    If the same physical workout was already pulled from Strava (matched by
    start time), we merge into that row instead of inserting a duplicate — the
    result is one workout with source="both", carrying both ids. See
    services/workout_match.py for the matching + field-priority policy.
    """
    if not user.whoop_access_token:
        raise ValueError("User has not connected WHOOP")

    token = decrypt_token(user.whoop_access_token)

    resp = await _get("/activity/workout", token, {"limit": 25})
    if resp.status_code == 401:
        token = await refresh_token(user, db)
        resp = await _get("/activity/workout", token, {"limit": 25})
    if resp.status_code != 200:
        raise ValueError(f"WHOOP workout fetch failed: {resp.status_code}")

    synced = 0
    for w in resp.json().get("records", []):
        if w.get("score_state") != "SCORED":
            continue

        whoop_id = w["id"]
        # Parse the start instant up front so it can also backfill an existing row.
        start, end = w.get("start"), w.get("end")
        started_at = parse_start(start)

        existing = (
            await db.execute(
                select(Workout).where(
                    Workout.user_id == user.id,
                    Workout.whoop_id == whoop_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            # Backfill started_at onto rows synced before that column existed, so
            # glucose windowing works for historical workouts. No-op once set.
            if existing.started_at is None and started_at is not None:
                existing.started_at = started_at
            continue

        duration = None
        if start and end:
            duration = int(
                (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
            )
        score = w.get("score") or {}
        fields = {
            "whoop_id": whoop_id,
            # "running" -> "Running", "functional_fitness" -> "Functional Fitness"
            "type": (w.get("sport_name") or "Workout").replace("_", " ").title(),
            "date": date.fromisoformat(start[:10]) if start else None,
            "started_at": started_at,
            "duration_seconds": duration,
            "distance_meters": score.get("distance_meter"),
            "avg_hr": score.get("average_heart_rate"),
        }

        # Same session already pulled from Strava? Merge into it instead of
        # creating a duplicate (one row, source="both", both ids set).
        match = await find_cross_source_duplicate(db, user.id, started_at, "whoop")
        if match is not None:
            merge_into(match, fields, "whoop")
            continue

        db.add(Workout(user_id=user.id, source="whoop", **fields))
        synced += 1

    await db.commit()
    return synced
