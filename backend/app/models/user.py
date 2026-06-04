from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

    # OAuth tokens (stored encrypted in production)
    whoop_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    whoop_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    strava_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    strava_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    dexcom_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    dexcom_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
