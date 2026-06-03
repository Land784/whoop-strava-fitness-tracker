from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)

    # Storing the full plan as JSON text — flexible for evolving Claude output
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)

    # A short summary of the prompt context used to generate this plan,
    # useful for debugging why Claude produced a particular recommendation
    prompt_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
