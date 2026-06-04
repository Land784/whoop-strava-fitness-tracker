from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GlucoseReading(Base):
    """A single CGM estimated glucose value (EGV) from Dexcom.

    Unlike RecoveryScore (one row per user per *day*), glucose is high-frequency
    time-series: Dexcom samples every ~5 minutes, so this table grows by ~288
    rows per user per day. Two consequences shape the schema below:

      1. Uniqueness is per *instant*, not per day — the natural key is
         (user_id, system_time). The unique constraint makes the sync's upsert
         idempotent: re-fetching a reading we already stored (which happens on
         every incremental sync because of the deliberate overlap window) is a
         harmless no-op instead of a duplicate row.

      2. Every read is a *windowed* range scan ("readings for user X between
         time A and B"), so (user_id, system_time) also gets a composite index.
         Without it, each glucose lookup would scan the entire table.
    """

    __tablename__ = "glucose_readings"
    __table_args__ = (
        UniqueConstraint("user_id", "system_time", name="uq_glucose_user_time"),
        # Composite index supports the windowed range queries the analysis does.
        # It also backs the unique constraint, but we name it explicitly so the
        # intent (fast time-range lookups) is clear.
        Index("ix_glucose_user_time", "user_id", "system_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # The instant the reading was recorded, in UTC. Dexcom returns both this
    # (`systemTime`) and a device-local `displayTime`; we store and join on UTC so
    # a daylight-saving shift can never misalign a workout's glucose window. The
    # local time is only relevant when labelling a chart for a human to read.
    system_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Glucose in mg/dL. Dexcom's EGV `value` is an integer in mg/dL; we keep that
    # as the canonical unit and convert to mmol/L only for display if ever needed.
    value_mgdl: Mapped[int] = mapped_column(Integer, nullable=False)

    # Dexcom trend arrow as a string, e.g. "flat", "fortyFiveUp", "singleDown".
    # Nullable because some readings (e.g. the first after a sensor warm-up) have
    # no trend yet.
    trend: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
