"""Business logic for all Claude AI interactions.

Routers call these functions and convert any ValueError into HTTP 4xx/5xx.
This file never imports from fastapi — that separation keeps logic testable
without spinning up a web server.
"""

import json
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.daily_briefing import DailyBriefing
from app.models.recovery import RecoveryScore
from app.models.training_plan import TrainingPlan
from app.models.user import User
from app.models.workout import Workout
from app.services.glucose import summarize_workout_glucose
from app.services.workout_match import _as_naive_utc

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
    #
    # Each workout line also gets its glucose summary, computed on the fly from
    # the raw CGM readings in a padded window (services/glucose.py). On the fly,
    # not stored, because the 1-3h-delayed Dexcom data fills in over time — a
    # summary frozen at sync would be permanently half-empty for recent sessions.
    # Python does the arithmetic; Claude only phrases it.
    workout_lines: list[str] = []
    any_glucose = False
    for w in workouts:
        line = (
            f"- {w.type or 'Unknown'} on {w.date}: "
            f"{w.duration_seconds}s, dist={w.distance_meters}m, avg_hr={w.avg_hr}"
        )
        g = await summarize_workout_glucose(w, db)
        if g:
            any_glucose = True
            line += (
                f" | glucose: start {g['start_mgdl']}, min {g['min_mgdl']}, "
                f"avg {g['avg_mgdl']}, max {g['max_mgdl']} mg/dL, "
                f"drop {g['drop_mgdl']}, {g['count_below_70']} reading(s) <70 "
                f"(over {g['count']} readings)"
            )
        workout_lines.append(line)
    workout_ctx = "\n".join(workout_lines) or "No recent workouts."

    recovery_ctx = "\n".join(
        f"- {r.date}: recovery={r.whoop_recovery_score}, hrv={r.hrv_ms}ms, rhr={r.resting_hr}, sleep={r.sleep_score}"
        for r in recovery
    ) or "No recent recovery data."

    glucose_note = (
        "Glucose values above are Dexcom CGM readings and are delayed 1-3 hours, "
        "so they describe past sessions — never the current moment."
        if any_glucose
        else "No glucose data is attached to these workouts yet."
    )

    # System prompt bakes in the user's data so Claude has context for
    # every response without the client needing to send it each time.
    #
    # The medical-safety guardrail lives here, in code, rather than relying on us
    # to prompt it correctly each call — and because every entry point (chat,
    # insight, daily briefing) shares this builder, the guardrail covers them all.
    return (
        "You are a personal fitness coach. Always ground your advice in the "
        "user's actual data shown below.\n\n"
        f"Recent workouts (last 7):\n{workout_ctx}\n\n"
        f"Recent recovery (last 7 days):\n{recovery_ctx}\n\n"
        f"{glucose_note}\n\n"
        "IMPORTANT — medical safety: You are not a medical device and must never "
        "give insulin dosing advice. Do not recommend insulin doses, basal rates, "
        "bolus amounts, correction factors, or carbohydrate-ratio changes. If the "
        "user asks how much insulin to take or how to adjust their pump, decline "
        "and tell them to consult their care team or endocrinologist. You may "
        "discuss general fueling, carbohydrate timing, and the glucose patterns "
        "you observe in their data."
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


def _parse_briefing(raw: str) -> dict[str, str]:
    """Turn Claude's reply into the three briefing fields.

    Claude is *asked* for bare JSON but LLMs sometimes wrap it in ```json fences
    or add a sentence of preamble. Rather than trust the format, we slice from
    the first '{' to the last '}' and parse that. If it still won't parse, we
    don't throw away the text — we surface it in 'state' so the card shows
    something rather than an error.
    """
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return {
                "recovery": str(data.get("recovery") or "—").strip(),
                "state": str(data.get("state") or "—").strip(),
                "recommended_workout": str(data.get("recommended_workout") or "—").strip(),
            }
        except json.JSONDecodeError:
            pass
    return {"recovery": "—", "state": text or "—", "recommended_workout": "—"}


async def _latest_data_timestamp(user: User, db: AsyncSession) -> datetime | None:
    """The most recent `created_at` across the user's workouts and recovery rows.

    This is the freshness signal for the daily briefing. A sync inserts rows
    stamped with the current time, so if the newest such row is later than the
    briefing we already generated, there's new data worth re-briefing on. Returns
    None when the user has no data at all (nothing synced yet).
    """
    latest_workout = (
        await db.execute(
            select(Workout.created_at)
            .where(Workout.user_id == user.id)
            .order_by(Workout.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_recovery = (
        await db.execute(
            select(RecoveryScore.created_at)
            .where(RecoveryScore.user_id == user.id)
            .order_by(RecoveryScore.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    stamps = [t for t in (latest_workout, latest_recovery) if t is not None]
    # Normalise before max(): timestamptz comes back tz-aware on Postgres but
    # naive on the SQLite test DB, and the two can't be compared. See
    # _as_naive_utc (the same footgun that bit the workout dedup).
    return max(stamps, key=_as_naive_utc) if stamps else None


async def get_or_create_daily_briefing(user: User, db: AsyncSession) -> DailyBriefing:
    """Return today's dashboard briefing, regenerating it when new data arrives.

    The original contract was "one Claude call per user per day". We relax it
    slightly so the card actually reflects what you've synced: today's row is
    reused on every page load UNTIL a newer workout or recovery row appears (i.e.
    you synced something new), at which point the next load regenerates the
    briefing *in place*. Cost is therefore bounded by data changes, not page
    views — at most a handful of Sonnet calls a day.
    """
    today = date.today()

    existing = (
        await db.execute(
            select(DailyBriefing).where(
                DailyBriefing.user_id == user.id,
                DailyBriefing.date == today,
            )
        )
    ).scalar_one_or_none()

    latest_data_ts = await _latest_data_timestamp(user, db)

    # Reuse today's briefing unless the user has synced newer data since it was
    # generated. Both timestamps come from the DB, so comparing them is safe on
    # either backend once normalised to naive-UTC.
    if existing is not None:
        if latest_data_ts is None or _as_naive_utc(latest_data_ts) <= _as_naive_utc(
            existing.generated_at
        ):
            return existing
        # else: fresh data exists → fall through and regenerate in place below.

    # No-data guard: if nothing is connected/synced yet, there's nothing to brief
    # on — so don't spend a Claude call to be told to connect a device. Return a
    # transient (un-persisted) briefing; the moment real data exists, the next
    # load generates and stores a real one. (Only reachable when existing is
    # None — an existing row implies data once existed, handled by the branch
    # above.)
    if latest_data_ts is None:
        content = {
            "recovery": "No recovery data yet.",
            "state": "Connect WHOOP and Strava in Settings, then sync.",
            "recommended_workout": "Once your data is flowing, your daily recommendation appears here.",
        }
        return DailyBriefing(
            user_id=user.id,
            date=today,
            content_json=json.dumps(content),
            generated_at=datetime.now(timezone.utc),
        )

    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

    system = await _build_coach_system_prompt(user, db)
    prompt = (
        "Using the data above, produce today's coaching briefing as a JSON "
        "object with exactly these three string keys:\n"
        '- "recovery": one or two sentences on how they recovered, grounded in '
        "their latest recovery score, HRV, resting HR, and sleep.\n"
        '- "state": one short sentence naming their current readiness state '
        "(e.g. primed, balanced, run-down).\n"
        '- "recommended_workout": one or two sentences recommending today\'s '
        "session — type plus rough intensity/duration — justified by the data.\n"
        "Return ONLY the JSON object: no markdown fences, no preamble."
    )

    # Sonnet (claude_model), not the cheap chat Haiku: this is the flagship
    # dashboard card and runs at most once per day, so the cost is negligible and
    # the better reasoning is worth it for the recommendation.
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    content = _parse_briefing(message.content[0].text)

    # Regeneration path: today's row already exists but new data made it stale.
    # Update it in place — the unique (user_id, date) constraint means we reuse
    # the row rather than inserting a second one for the same day.
    if existing is not None:
        existing.content_json = json.dumps(content)
        existing.generated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    briefing = DailyBriefing(
        user_id=user.id,
        date=today,
        content_json=json.dumps(content),
    )
    db.add(briefing)
    try:
        await db.commit()
    except IntegrityError:
        # Another request inserted today's row between our existence check and
        # this commit (the unique constraint caught it). Roll back and read the
        # winner instead of failing — and crucially, we don't double-charge for
        # a second Claude call because that already happened above only once.
        await db.rollback()
        return (
            await db.execute(
                select(DailyBriefing).where(
                    DailyBriefing.user_id == user.id,
                    DailyBriefing.date == today,
                )
            )
        ).scalar_one()
    await db.refresh(briefing)
    return briefing
