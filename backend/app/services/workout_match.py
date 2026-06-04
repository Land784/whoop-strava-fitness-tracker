"""Cross-source workout de-duplication.

Strava and WHOOP have no shared workout ID, so the *same* physical session
shows up as two records. We detect that by start time (the one thing both
systems agree on) and merge them into a single Workout row that carries both
IDs — the model was built for this (it has strava_id, whoop_id AND source).

All the matching + field-priority policy lives here, in one place, so the two
sync services can't drift apart on what "the same workout" means or which
source wins a given field.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workout import Workout

# How far apart two start times can be and still be considered the same workout.
# Clocks and auto-detected start instants differ slightly between providers, so
# we allow a few minutes. Two genuinely different workouts starting within five
# minutes of each other is implausible, which is why start time alone is a
# strong enough signal — we deliberately do NOT also require matching durations
# (Strava reports *moving* time, WHOOP reports *elapsed*, so they often differ).
MATCH_WINDOW = timedelta(minutes=5)


def parse_start(iso: str | None) -> datetime | None:
    """Parse a provider timestamp into a naive-UTC datetime.

    We normalise to naive UTC (tz-aware converted to UTC, then tzinfo dropped)
    so every started_at is directly comparable regardless of the source's
    timezone — and so comparisons behave the same on Postgres and SQLite (the
    latter doesn't preserve tz). Strava's `start_date` and WHOOP's `start` are
    both UTC, so this keeps them on the same clock.
    """
    if not iso:
        return None
    # Python 3.11+ parses a trailing 'Z', but normalise it for safety.
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _view_from_row(w: Workout) -> dict:
    """The merge-relevant fields of an already-stored single-source workout."""
    return {
        "type": w.type,
        "distance_meters": w.distance_meters,
        "duration_seconds": w.duration_seconds,
        "avg_hr": w.avg_hr,
        "started_at": w.started_at,
        "date": w.date,
    }


def _merged_fields(strava: dict | None, whoop: dict | None) -> dict:
    """Field-aware merge of a Strava view and a WHOOP view.

    Each device is trusted for what it measures best, with a non-null fallback
    to the other source:
      - distance / duration / type  -> Strava wins (it has GPS + clean sport names)
      - average heart rate          -> WHOOP wins (dedicated strap sensor)
    """
    s = strava or {}
    w = whoop or {}

    def prefer(primary, secondary):
        return primary if primary is not None else secondary

    return {
        "type": prefer(s.get("type"), w.get("type")),
        "distance_meters": prefer(s.get("distance_meters"), w.get("distance_meters")),
        "duration_seconds": prefer(s.get("duration_seconds"), w.get("duration_seconds")),
        "avg_hr": prefer(w.get("avg_hr"), s.get("avg_hr")),
        # Prefer Strava's start/date if present, else WHOOP's — they should agree.
        "started_at": prefer(s.get("started_at"), w.get("started_at")),
        "date": prefer(s.get("date"), w.get("date")),
    }


async def find_cross_source_duplicate(
    db: AsyncSession, user_id: int, started_at: datetime | None, incoming_source: str
) -> Workout | None:
    """Find a single-source workout from the *other* provider near `started_at`.

    Only matches rows that have the other provider's id but NOT the incoming
    one (so we never re-merge an already-merged row, or touch manual entries).
    Returns the closest match by start time, or None.
    """
    if started_at is None:
        return None

    lo, hi = started_at - MATCH_WINDOW, started_at + MATCH_WINDOW
    if incoming_source == "strava":
        incoming_id, other_id = Workout.strava_id, Workout.whoop_id
    else:
        incoming_id, other_id = Workout.whoop_id, Workout.strava_id

    rows = (
        await db.execute(
            select(Workout).where(
                Workout.user_id == user_id,
                Workout.started_at.is_not(None),
                Workout.started_at >= lo,
                Workout.started_at <= hi,
                other_id.is_not(None),   # came from the other provider
                incoming_id.is_(None),   # not already linked to this one
            )
        )
    ).scalars().all()
    if not rows:
        return None
    return min(rows, key=lambda w: abs((w.started_at - started_at).total_seconds()))


def merge_into(existing: Workout, incoming: dict, incoming_source: str) -> None:
    """Merge an incoming provider's parsed fields into an existing workout row.

    `existing` is a single-source row from the *other* provider; `incoming` is
    the dict the sync built for the new record (including its id). Mutates
    `existing` in place: applies the field-aware merge, links both ids, and
    marks source='both'.
    """
    existing_view = _view_from_row(existing)
    if incoming_source == "strava":
        merged = _merged_fields(strava=incoming, whoop=existing_view)
        existing.strava_id = incoming["strava_id"]
    else:
        merged = _merged_fields(strava=existing_view, whoop=incoming)
        existing.whoop_id = incoming["whoop_id"]

    existing.type = merged["type"]
    existing.distance_meters = merged["distance_meters"]
    existing.duration_seconds = merged["duration_seconds"]
    existing.avg_hr = merged["avg_hr"]
    existing.started_at = merged["started_at"]
    existing.date = merged["date"]
    existing.source = "both"


async def merge_existing_duplicates(db: AsyncSession, user_id: int) -> int:
    """One-off cleanup: merge cross-source duplicate workouts already in the DB.

    New workouts merge at insert time (find_cross_source_duplicate), but rows
    synced *before* the started_at column existed had no start instant to match
    on, so the same session from Strava and WHOOP was stored as two rows. Now
    that started_at has been backfilled, this pairs a Strava-only row with a
    WHOOP-only row at the same start time, merges the WHOOP row into the Strava
    row (source='both', both ids set), and deletes the now-redundant WHOOP row.

    Returns the number of merges performed. Idempotent: with no remaining
    single-source pairs it merges nothing.
    """
    def _single_source(rows, keep_id, drop_id):
        return [r for r in rows if getattr(r, keep_id) and not getattr(r, drop_id)]

    all_rows = (
        await db.execute(
            select(Workout).where(
                Workout.user_id == user_id,
                Workout.started_at.is_not(None),
            )
        )
    ).scalars().all()

    strava_rows = _single_source(all_rows, "strava_id", "whoop_id")
    whoop_rows = _single_source(all_rows, "whoop_id", "strava_id")

    merges = 0
    used: set[int] = set()
    for s in strava_rows:
        # Nearest unused WHOOP row within the match window (same policy as the
        # insert-time matcher) — start time alone is a strong enough signal.
        candidates = [
            w
            for w in whoop_rows
            if w.id not in used
            and abs((w.started_at - s.started_at).total_seconds()) <= MATCH_WINDOW.total_seconds()
        ]
        if not candidates:
            continue
        w = min(candidates, key=lambda x: abs((x.started_at - s.started_at).total_seconds()))

        # Capture the WHOOP fields into a plain dict, then delete + flush the
        # WHOOP row BEFORE merge_into reassigns its whoop_id to the Strava row.
        # Otherwise both rows briefly hold the same whoop_id and the unique
        # constraint trips on flush.
        incoming = {**_view_from_row(w), "whoop_id": w.whoop_id}
        used.add(w.id)
        await db.delete(w)
        await db.flush()
        merge_into(s, incoming, "whoop")
        merges += 1

    await db.commit()
    return merges
