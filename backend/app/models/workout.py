from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # strava_id / whoop_id let us upsert rather than duplicate when syncing from
    # each provider (a workout can come from either source).
    strava_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    whoop_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)

    # Provenance: "strava" | "whoop" | "manual" — drives the source badge in the
    # UI. server_default keeps existing rows valid when this column is added.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'manual'"))

    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Training Stress Score — a composite measure of workout load
    tss: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
