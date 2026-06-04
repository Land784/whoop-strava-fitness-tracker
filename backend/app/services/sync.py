"""Orchestrates a full data sync for a user across all connected sources."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import strava, whoop


async def sync_all(user: User, db: AsyncSession) -> dict[str, int | str]:
    """Trigger Strava + WHOOP sync and return a summary.

    Errors from individual sources are caught and reported rather than
    aborting the whole sync — a disconnected Strava shouldn't prevent
    WHOOP data from coming in.
    """
    results: dict[str, int | str] = {}

    try:
        results["strava_activities"] = await strava.sync_activities(user, db)
    except ValueError as exc:
        results["strava_error"] = str(exc)

    try:
        results["whoop_recovery"] = await whoop.sync_recovery(user, db)
    except ValueError as exc:
        results["whoop_error"] = str(exc)

    try:
        results["whoop_workouts"] = await whoop.sync_workouts(user, db)
    except ValueError as exc:
        results["whoop_workouts_error"] = str(exc)

    return results
