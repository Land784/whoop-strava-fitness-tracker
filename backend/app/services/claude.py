"""Business logic for all Claude AI interactions.

Routers call these functions and convert any ValueError into HTTP 4xx/5xx.
This file never imports from fastapi — that separation keeps logic testable
without spinning up a web server.
"""

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.recovery import RecoveryScore
from app.models.training_plan import TrainingPlan
from app.models.user import User
from app.models.workout import Workout


async def get_insights(question: str, user: User, db: AsyncSession) -> str:
    """Return a coaching insight for the given question, using the user's
    recent workout and recovery data as context."""
    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

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

    workout_ctx = "\n".join(
        f"- {w.type or 'Unknown'} on {w.date}: tss={w.tss}, dist={w.distance_meters}m, avg_hr={w.avg_hr}"
        for w in workouts
    ) or "No recent workouts."

    recovery_ctx = "\n".join(
        f"- {r.date}: recovery={r.whoop_recovery_score}, hrv={r.hrv_ms}ms, rhr={r.resting_hr}, sleep={r.sleep_score}"
        for r in recovery
    ) or "No recent recovery data."

    # System prompt bakes in the user's data so Claude has context for
    # every response without the client needing to send it each time
    system = (
        "You are a personal fitness coach. Always ground your advice in the "
        "user's actual data shown below.\n\n"
        f"Recent workouts (last 7):\n{workout_ctx}\n\n"
        f"Recent recovery (last 7 days):\n{recovery_ctx}"
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return message.content[0].text


async def generate_training_plan(week_start: str, user: User, db: AsyncSession) -> TrainingPlan:
    """Generate a weekly training plan and persist it."""
    if not settings.anthropic_api_key:
        raise ValueError("AI service is not configured")

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

    avg_tss = (
        sum(w.tss for w in recent_workouts if w.tss) / len(recent_workouts)
        if recent_workouts else 0
    )
    avg_recovery = (
        sum(r.whoop_recovery_score for r in recent_recovery if r.whoop_recovery_score)
        / len(recent_recovery)
        if recent_recovery else 50
    )
    prompt_summary = (
        f"2-week avg TSS: {avg_tss:.1f}, 7-day avg recovery: {avg_recovery:.1f}, "
        f"week starting: {week_start}"
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Generate a 7-day training plan for the week starting {week_start}. "
                f"Context: {prompt_summary}. "
                "Return a JSON object with keys 'days' (array of daily plans) and 'summary'."
            ),
        }],
    )

    plan = TrainingPlan(
        user_id=user.id,
        week_start=week_start,
        plan_json=message.content[0].text,
        prompt_summary=prompt_summary,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan
