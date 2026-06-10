"""Dexcom OAuth (authorization-code) and glucose (EGV) sync.

Mirrors the WHOOP service: tokens are stored encrypted and decrypted only at the
moment we call Dexcom, and a 401 triggers a one-time refresh + retry. Dexcom
access tokens are short-lived, so we request the `offline_access` scope (in the
authorize URL) which is what makes Dexcom return a refresh token.

Two things are specific to Dexcom and shape this file:

  1. **Sandbox vs production host.** Dexcom gates production behind an app review,
     so we develop against the sandbox (synthetic data, instant access). The host
     is chosen from settings.dexcom_use_sandbox, so going live is an env change.

  2. **High-frequency time-series.** Dexcom samples every ~5 min, and the EGV
     endpoint caps each request to a bounded date range. So a backfill loops in
     <=30-day chunks. Incremental syncs re-fetch a 6h overlap because the Web API
     is delayed 1-3h and readings arrive late — the idempotent upsert on
     (user_id, system_time) makes re-fetching a stored reading a no-op.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.models.glucose import GlucoseReading
from app.models.user import User

# Backfill depth on first connect, the per-request range cap, and the incremental
# overlap. Constants, not settings: they're tuning knobs, not deployment config.
BACKFILL_DAYS = 90
CHUNK_DAYS = 30
OVERLAP_HOURS = 6

SANDBOX_BASE = "https://sandbox-api.dexcom.com"
PRODUCTION_BASE = "https://api.dexcom.com"


def _base() -> str:
    """API + OAuth host, chosen by the sandbox flag. Both OAuth and data
    endpoints live on the same host, so one switch covers everything."""
    return SANDBOX_BASE if settings.dexcom_use_sandbox else PRODUCTION_BASE


def authorize_url(state: str) -> str:
    """Build the Dexcom authorize URL for the OAuth redirect.

    Lives here (not in the router like WHOOP's) because the host switches with
    the sandbox flag, and that logic is already centralised in _base(). The
    `offline_access` scope is what makes Dexcom return a refresh token — its
    access tokens are short-lived, exactly like WHOOP's `offline`.
    """
    query = urlencode(
        {
            "client_id": settings.dexcom_client_id,
            "redirect_uri": settings.dexcom_redirect_uri,
            "response_type": "code",
            "scope": "offline_access",
            "state": state,
        }
    )
    return f"{_base()}/v2/oauth2/login?{query}"


def _to_aware_utc(dt: datetime) -> datetime:
    """Normalise any datetime to tz-AWARE UTC.

    We store glucose timestamps as aware UTC to match Workout.started_at, so the
    later window join compares like-for-like. This matters because system_time is
    a Postgres `timestamptz`: the async driver (asyncpg) interprets a *naive*
    datetime parameter in the server PROCESS's local timezone, silently shifting
    a naive "UTC" value by the host's offset (e.g. storing 12:00 as 17:00 on a
    US/Eastern host). Pinning everything to aware UTC removes that ambiguity. A
    value with no offset is assumed UTC; an offset value is converted to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_system_time(raw: str) -> datetime:
    """Parse Dexcom's `systemTime` (UTC) into tz-aware UTC.

    Dexcom usually returns systemTime without an offset (it's UTC by definition),
    but we defensively handle a trailing 'Z' or explicit offset too."""
    return _to_aware_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))


def _fmt(dt: datetime) -> str:
    """Format a datetime for Dexcom's startDate/endDate.

    Dexcom's EGV endpoint wants a UTC wall-clock timestamp with NO offset suffix,
    so we convert to UTC and drop the zone in the string only (the in-process
    values stay aware UTC — see _to_aware_utc)."""
    return _to_aware_utc(dt).strftime("%Y-%m-%dT%H:%M:%S")


async def exchange_code(code: str, user: User, db: AsyncSession) -> None:
    """Exchange the authorization code for Dexcom tokens; store them encrypted."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base()}/v2/oauth2/token",
            data={
                "client_id": settings.dexcom_client_id,
                "client_secret": settings.dexcom_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.dexcom_redirect_uri,
            },
        )

    if resp.status_code != 200:
        raise ValueError(f"Dexcom token exchange failed: {resp.text}")

    data = resp.json()
    user.dexcom_access_token = encrypt_token(data["access_token"])
    if data.get("refresh_token"):
        user.dexcom_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()


async def refresh_token(user: User, db: AsyncSession) -> str:
    """Refresh the Dexcom access token. Returns the new *plaintext* token for
    immediate use; the persisted copy is encrypted."""
    if not user.dexcom_refresh_token:
        raise ValueError("No Dexcom refresh token stored for this user")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_base()}/v2/oauth2/token",
            data={
                "client_id": settings.dexcom_client_id,
                "client_secret": settings.dexcom_client_secret,
                "refresh_token": decrypt_token(user.dexcom_refresh_token),
                "grant_type": "refresh_token",
                "redirect_uri": settings.dexcom_redirect_uri,
            },
        )

    if resp.status_code != 200:
        raise ValueError("Dexcom token refresh failed")

    data = resp.json()
    user.dexcom_access_token = encrypt_token(data["access_token"])
    if data.get("refresh_token"):
        user.dexcom_refresh_token = encrypt_token(data["refresh_token"])
    await db.commit()
    return data["access_token"]


async def _get(path: str, token: str, params: dict) -> httpx.Response:
    """GET a Dexcom endpoint with the given bearer token."""
    async with httpx.AsyncClient() as client:
        return await client.get(
            f"{_base()}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )


async def sync_glucose(user: User, db: AsyncSession) -> int:
    """Fetch recent EGVs from Dexcom and upsert GlucoseReading rows.
    Returns the number of *new* rows added.

    First sync (no readings yet) backfills BACKFILL_DAYS; later syncs start a
    little before the latest stored reading (OVERLAP_HOURS) so readings that the
    delayed Web API published late aren't permanently skipped. The window is
    walked in <=CHUNK_DAYS chunks because the EGV endpoint caps each request's
    date range.
    """
    if not user.dexcom_access_token:
        raise ValueError("User has not connected Dexcom")

    token = decrypt_token(user.dexcom_access_token)
    now = datetime.now(timezone.utc)  # aware UTC; all window math stays aware

    # Where to start: full backfill on first sync, else overlap-before-latest.
    latest = (
        await db.execute(
            select(func.max(GlucoseReading.system_time)).where(
                GlucoseReading.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if latest is None:
        start = now - timedelta(days=BACKFILL_DAYS)
    else:
        # `latest` is aware on Postgres but naive on SQLite (the test DB has no
        # real tz type) — normalise so the subtraction below never mixes the two.
        start = _to_aware_utc(latest) - timedelta(hours=OVERLAP_HOURS)

    synced = 0
    chunk_start = start
    while chunk_start < now:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), now)

        resp = await _get(
            "/v3/users/self/egvs",
            token,
            {"startDate": _fmt(chunk_start), "endDate": _fmt(chunk_end)},
        )
        # 401 -> access token expired; refresh once and retry this same chunk.
        if resp.status_code == 401:
            token = await refresh_token(user, db)
            resp = await _get(
                "/v3/users/self/egvs",
                token,
                {"startDate": _fmt(chunk_start), "endDate": _fmt(chunk_end)},
            )
        if resp.status_code != 200:
            raise ValueError(f"Dexcom EGV fetch failed: {resp.status_code}")

        for rec in resp.json().get("records", []):
            value = rec.get("value")
            # Some records (e.g. sensor gaps / non-EGV events) carry no value —
            # nothing to store for those.
            if value is None or not rec.get("systemTime"):
                continue

            st = _parse_system_time(rec["systemTime"])

            # Idempotent upsert: if this exact (user, instant) reading is already
            # stored — which is expected for everything inside the overlap window
            # on an incremental sync — skip it rather than inserting a duplicate.
            existing = (
                await db.execute(
                    select(GlucoseReading).where(
                        GlucoseReading.user_id == user.id,
                        GlucoseReading.system_time == st,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            db.add(
                GlucoseReading(
                    user_id=user.id,
                    system_time=st,
                    value_mgdl=int(value),
                    trend=rec.get("trend"),
                )
            )
            synced += 1

        chunk_start = chunk_end

    await db.commit()
    return synced
