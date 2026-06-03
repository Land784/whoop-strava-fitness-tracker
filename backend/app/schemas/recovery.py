# `date` aliased to `date_` so the model field named `date` can't shadow the
# type. See the note in schemas/workout.py for the full explanation.
from datetime import date as date_, datetime

from pydantic import BaseModel


class RecoveryCreate(BaseModel):
    date: date_
    whoop_recovery_score: float | None = None
    hrv_ms: float | None = None
    resting_hr: int | None = None
    sleep_score: float | None = None


class RecoveryOut(RecoveryCreate):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    created_at: datetime
