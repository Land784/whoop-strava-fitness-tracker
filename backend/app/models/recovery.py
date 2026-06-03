from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RecoveryScore(Base):
    __tablename__ = "recovery_scores"
    # One recovery row per user per day — guaranteed at the DB level, not just
    # by the existence checks in sync_recovery / create_recovery.
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_recovery_user_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)

    # WHOOP-specific metrics
    whoop_recovery_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0–100
    hrv_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0–100

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
