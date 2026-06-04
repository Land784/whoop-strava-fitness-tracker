"""Glucose pattern analysis.

The division of labour for the AI feature: *Python computes the numbers here*,
and Claude only phrases them (see services/claude.py). LLMs are unreliable at
arithmetic over many values, and for glucose a hallucinated "dropped 45" when it
was really 15 is a safety problem — so every statistic the coach quotes is
computed deterministically and is unit-testable.

This module does no I/O beyond a windowed read; it never reasons about insulin.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glucose import GlucoseReading
from app.models.workout import Workout

# The padded window around a workout (decided in the design grill): glucose
# behaviour around exercise is heavily lagged, so we look from an hour before to
# two hours after to capture the pre-workout level, the in-session response, and
# the post-workout drop/rebound that is often the whole story.
PRE_WINDOW = timedelta(minutes=60)
POST_WINDOW = timedelta(minutes=120)

# Below this many readings in the window we decline to summarise: a "pattern"
# from one or two delayed points would be misleading. The coach then says it
# doesn't have enough glucose data rather than inventing a trend.
MIN_READINGS = 3

# The clinical low threshold (mg/dL). Readings under this are flagged because a
# post-exercise drop below 70 is the pattern most worth surfacing.
LOW_THRESHOLD = 70


async def summarize_workout_glucose(workout: Workout, db: AsyncSession) -> dict | None:
    """Summarise the glucose readings around a single workout.

    Returns a small dict of deterministic stats, or None when we can't/shouldn't
    summarise (no start time, or too few readings in the window — e.g. a recent
    workout whose post-window data the 1-3h-delayed API hasn't published yet).
    """
    # Can't build a window without a precise start. Older/manual rows may lack it.
    if workout.started_at is None:
        return None

    start_instant = workout.started_at
    # If duration is unknown, anchor the post-window to the start instant rather
    # than guessing a length.
    end_instant = start_instant + timedelta(seconds=workout.duration_seconds or 0)

    lo = start_instant - PRE_WINDOW
    hi = end_instant + POST_WINDOW

    readings = (
        await db.execute(
            select(GlucoseReading)
            .where(
                GlucoseReading.user_id == workout.user_id,
                GlucoseReading.system_time >= lo,
                GlucoseReading.system_time <= hi,
            )
            .order_by(GlucoseReading.system_time)
        )
    ).scalars().all()

    if len(readings) < MIN_READINGS:
        return None

    values = [r.value_mgdl for r in readings]
    start_val = values[0]
    low = min(values)

    return {
        "count": len(values),
        "start_mgdl": start_val,
        "min_mgdl": low,
        "max_mgdl": max(values),
        "avg_mgdl": round(sum(values) / len(values)),
        # Drop from the starting level to the lowest point in the window. Clamped
        # at 0 so a workout where glucose only rose reads as "no drop", not a
        # negative number.
        "drop_mgdl": max(0, start_val - low),
        "count_below_70": sum(1 for v in values if v < LOW_THRESHOLD),
    }
