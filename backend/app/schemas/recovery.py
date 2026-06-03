from datetime import date, datetime

from pydantic import BaseModel


class RecoveryCreate(BaseModel):
    date: date
    whoop_recovery_score: float | None = None
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_score: float | None = None


class RecoveryOut(RecoveryCreate):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    created_at: datetime
