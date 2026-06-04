from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyBriefing(Base):
    """A once-per-day AI coaching summary shown on the dashboard.

    Persisted (rather than regenerated each visit) so we make at most ONE Claude
    call per user per day. The summary is inherently a daily artifact — it's
    about how you recovered *today* — so "one row per user per day" is the
    natural shape, mirroring RecoveryScore.
    """

    __tablename__ = "daily_briefings"
    # Enforce one briefing per user per day at the DB level, not just via an
    # existence check in the service. Without this, two near-simultaneous
    # dashboard loads could both miss the check and each insert a row (and each
    # pay for a Claude call). The constraint makes the race impossible — the
    # second insert fails and the service falls back to reading the first row.
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_briefing_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # The structured coach output as a JSON string: {recovery, state,
    # recommended_workout}. Stored as Text (like TrainingPlan.plan_json) so the
    # shape can evolve without a migration. The service guarantees it is always
    # valid JSON with those keys, so readers can json.loads it safely.
    content_json: Mapped[str] = mapped_column(Text, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
