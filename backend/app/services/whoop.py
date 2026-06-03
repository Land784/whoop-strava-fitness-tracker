"""WHOOP OAuth (PKCE flow) and recovery/sleep data sync."""

from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.recovery import RecoveryScore
from app.models.user import User

WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"


async def exchange_code(code: str, user: User, db: AsyncSession) -> None:
    """Exchange authorization code for WHOOP tokens (PKCE flow)."""
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
    user.whoop_access_token = data["access_token"]
    user.whoop_refresh_token = data["refresh_token"]
    await db.commit()


async def sync_recovery(user: User, db: AsyncSession) -> int:
    """Fetch recent WHOOP recovery records and upsert them.
    Returns the count of new records added."""
    if not user.whoop_access_token:
        raise ValueError("User has not connected WHOOP")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{WHOOP_API_BASE}/recovery",
            headers={"Authorization": f"Bearer {user.whoop_access_token}"},
            params={"limit": 25},
        )

    if resp.status_code != 200:
        raise ValueError(f"WHOOP recovery fetch failed: {resp.status_code}")

    records = resp.json().get("records", [])
    synced = 0

    for record in records:
        record_date = date.fromisoformat(record["created_at"][:10])

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

        score = RecoveryScore(
            user_id=user.id,
            date=record_date,
            whoop_recovery_score=record.get("score", {}).get("recovery_score"),
            hrv_ms=record.get("score", {}).get("hrv_rmssd_milli"),
            resting_hr=record.get("score", {}).get("resting_heart_rate"),
            sleep_score=record.get("score", {}).get("sleep_performance_percentage"),
        )
        db.add(score)
        synced += 1

    await db.commit()
    return synced
