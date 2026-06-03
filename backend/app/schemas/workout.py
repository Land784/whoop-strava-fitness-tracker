from datetime import date, datetime

from pydantic import BaseModel


class WorkoutCreate(BaseModel):
    type: str | None = None
    date: date | None = None
    duration_seconds: int | None = None
    distance_meters: float | None = None
    avg_hr: int | None = None
    tss: float | None = None


class WorkoutOut(WorkoutCreate):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    strava_id: str | None = None
    created_at: datetime
