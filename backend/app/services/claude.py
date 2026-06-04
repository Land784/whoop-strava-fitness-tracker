"""Business logic for all Claude AI interactions.

Routers call these functions and convert any ValueError into HTTP 4xx/5xx.
This file never imports from fastapi — that separation keeps logic testable
without spinning up a web server.
"""

from collections.abc import AsyncIterator
from datetime import date

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.recovery import RecoveryScore
from app.models.training_plan import TrainingPlan
from app.models.user import User
from app.models.workout import Workout

# How many prior turns of a conversation we feed back to Claude. Bounds the
# token cost (and latency) of a long chat — older turns drop off the front.
# Kept here, not in the prompt, because it's a tuning knob, not coach behaviour.
MAX_HISTORY_MESSAGES = 20


async def _build_coach_system_prompt(user: User, db: AsyncSession) -> str:
    """Build the system prompt that grounds the coach in the user's own data.

    Pulled into its own helper because both the single-shot insight and the
    streaming chat need the *exact same* context. Duplicating it would mean two
    places to update every time the data we surface changes — and they'd drift.
    """
    workouts = (
        await db.execute(
            select(Workout)
            .where(Workout.user_id == user.id)
            .order_by(Workout.date.desc())
            .limit(7)
        )
    ).scalars().all()

    recovery = (
        await db.execute(
            select(RecoveryScore)
            .where(RecoveryScore.user_id == user.id)
            .order_by(RecoveryScore.date.desc())
            .limit(7)
        )
    ).scalars().all()

    # No TSS here: we don't compute it yet, so "tss=None" would just mislead the
    # model. Describe load with the fields we actually have from Strava.
    workout_ctx = "\n".join(
        f"- {w.type or 'Unknown'} on {w.date}: "
        f"{w.duration_seconds}s, dist={w.distance_meters}m, avg_hr={w.avg_hr}"
        for w in workouts
    ) or "No recent workouts."

    recovery_ctx = "\n".join(
        f"- {r.date}: recovery={r.whoop_recovery_score}, hrv={r.hrv_ms}ms, rhr={r.resting_hr}, sleep={r.sleep_score}"
        for r in recovery
    ) or "No recent recovery data."

    # System prompt bakes in the user's data so Claude has context for
    # every response without the client needing to send it each time.
    return (
        "You are a personal fitness coach. Always ground your advice in the "
        "user's actual data shown below.\n\n"
        f"Recent workouts (last 7):\n{workout_ctx}\n\n"
        f"Recent recovery (last 7 days):\n{recovery_ctx}"
    )


async def get_insights(question: str, user: User, db: AsyncSession) -> str:
    """Return a single coaching insight for one question (non-streaming).

    Kept as the simple synchronous path — handy for scripts and tests. The
    browser chat uses stream_insights instead.
    """
    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

    system = await _build_coach_system_prompt(user, db)

    # AsyncAnthropic + await: the network call yields control back to the event
    # loop instead of blocking the whole server while Claude responds.
    # Chat uses the cheaper Haiku model (settings.claude_chat_model), not the
    # Sonnet model the training plan uses. See config.py for why.
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.claude_chat_model,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return message.content[0].text


async def stream_insights(
    messages: list[dict[str, str]], user: User, db: AsyncSession
) -> AsyncIterator[str]:
    """Stream a coaching reply token-by-token for a *multi-turn* conversation.

    `messages` is the full chat history ([{role, content}, ...]) — passing it
    every turn is how Claude "remembers" the conversation: the API itself is
    stateless, so memory lives in what the client re-sends each request.

    This is an async generator (it `yield`s). Each yield is a chunk of text the
    router forwards to the browser as a Server-Sent Event.
    """
    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

    # Keep only the most recent turns to bound cost. After trimming, Anthropic
    # requires the first message to be a 'user' turn, so drop any leading
    # 'assistant' turn the slice may have left exposed.
    trimmed = messages[-MAX_HISTORY_MESSAGES:]
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)

    system = await _build_coach_system_prompt(user, db)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    # client.messages.stream(...) returns a context manager (note: not awaited).
    # Inside it, .text_stream is an async iterator of just the text deltas —
    # the SDK does the work of pulling the raw event stream apart for us.
    async with client.messages.stream(
        model=settings.claude_chat_model,
        max_tokens=512,
        system=system,
        messages=trimmed,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def generate_training_plan(week_start: str, user: User, db: AsyncSession) -> TrainingPlan:
    """Generate a weekly training plan and persist it."""
    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

    # week_start arrives as an ISO string from the request. Parse it to a real
    # `date` before persisting: the column is a DATE, and we shouldn't rely on
    # the database silently coercing a string (Postgres does, SQLite doesn't —
    # and "works only because the DB is lenient" is a bug waiting to surface).
    # date.fromisoformat raises ValueError on a bad string, which the router
    # already maps to an HTTP error.
    week_start_date = date.fromisoformat(week_start)

    recent_workouts = (
        await db.execute(
            select(Workout)
            .where(Workout.user_id == user.id)
            .order_by(Workout.date.desc())
            .limit(14)
        )
    ).scalars().all()

    recent_recovery = (
        await db.execute(
            select(RecoveryScore)
            .where(RecoveryScore.user_id == user.id)
            .order_by(RecoveryScore.date.desc())
            .limit(7)
        )
    ).scalars().all()

    # Summarise recent load *without* TSS (not computed yet): how many workouts,
    # typical duration, and total distance over the two-week window.
    n_workouts = len(recent_workouts)
    avg_minutes = (
        sum(w.duration_seconds for w in recent_workouts if w.duration_seconds)
        / n_workouts
        / 60
        if n_workouts
        else 0
    )
    total_km = sum(w.distance_meters for w in recent_workouts if w.distance_meters) / 1000
    avg_recovery = (
        sum(r.whoop_recovery_score for r in recent_recovery if r.whoop_recovery_score)
        / len(recent_recovery)
        if recent_recovery
        else 50
    )
    prompt_summary = (
        f"Last 14 days: {n_workouts} workouts, ~{avg_minutes:.0f} min each, "
        f"{total_km:.0f} km total. 7-day avg recovery: {avg_recovery:.0f}. "
        f"Week starting: {week_start}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Generate a 7-day training plan for the week starting {week_start}. "
                    f"Context: {prompt_summary}. "
                    "Return a JSON object with keys 'days' (array of daily plans) and 'summary'."
                ),
            }
        ],
    )

    plan = TrainingPlan(
        user_id=user.id,
        week_start=week_start_date,
        plan_json=message.content[0].text,
        prompt_summary=prompt_summary,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan
