"""Tests for services/glucose.summarize_workout_glucose — the deterministic math
the AI coach later quotes. Because Claude only *phrases* these numbers, the
numbers themselves have to be correct, so they're pinned here against fixtures.

Covers: the padded window (readings outside it are excluded), each statistic,
the too-few-readings guard (returns None), and the no-start-time guard.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glucose import GlucoseReading
from app.models.user import User
from app.models.workout import Workout
from app.services.glucose import summarize_workout_glucose

# Workout: starts 12:00, runs 1h (ends 13:00). Window = [11:00, 15:00]
# (60 min before start, 120 min after end).
START = datetime(2026, 6, 1, 12, 0, 0)


def _reading(user_id: int, minutes_from_start: int, value: int) -> GlucoseReading:
    return GlucoseReading(
        user_id=user_id,
        system_time=START + timedelta(minutes=minutes_from_start),
        value_mgdl=value,
        trend="flat",
    )


async def test_summary_windows_and_computes_stats(db: AsyncSession, user: User):
    workout = Workout(
        user_id=user.id,
        type="Ride",
        started_at=START,
        duration_seconds=3600,
    )
    db.add(workout)
    # Inside the window:
    db.add(_reading(user.id, -30, 140))   # 11:30 — first reading => "start"
    db.add(_reading(user.id, 30, 110))    # 12:30
    db.add(_reading(user.id, 90, 68))     # 13:30 — below 70
    db.add(_reading(user.id, 120, 90))    # 14:00
    # Outside the window — must be excluded entirely:
    db.add(_reading(user.id, -120, 200))  # 10:00 (before window)
    db.add(_reading(user.id, 200, 50))    # 15:20 (after window)
    await db.commit()
    await db.refresh(workout)

    summary = await summarize_workout_glucose(workout, db)

    assert summary is not None
    assert summary["count"] == 4              # only in-window readings
    assert summary["start_mgdl"] == 140       # earliest in-window, not the 10:00 one
    assert summary["min_mgdl"] == 68
    assert summary["max_mgdl"] == 140         # the 200 at 10:00 is excluded
    assert summary["avg_mgdl"] == 102         # round((140+110+68+90)/4) = 102
    assert summary["drop_mgdl"] == 72         # 140 - 68
    assert summary["count_below_70"] == 1     # just the 68


async def test_summary_returns_none_below_min_readings(db: AsyncSession, user: User):
    workout = Workout(user_id=user.id, type="Run", started_at=START, duration_seconds=1800)
    db.add(workout)
    db.add(_reading(user.id, 0, 120))
    db.add(_reading(user.id, 10, 118))  # only 2 readings (< MIN_READINGS)
    await db.commit()
    await db.refresh(workout)

    assert await summarize_workout_glucose(workout, db) is None


async def test_summary_returns_none_without_start_time(db: AsyncSession, user: User):
    """A workout with no started_at can't anchor a window — skip it."""
    workout = Workout(user_id=user.id, type="Manual", started_at=None)
    db.add(workout)
    db.add(_reading(user.id, 0, 120))
    db.add(_reading(user.id, 5, 118))
    db.add(_reading(user.id, 10, 116))
    await db.commit()
    await db.refresh(workout)

    assert await summarize_workout_glucose(workout, db) is None
