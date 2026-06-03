# `date` is imported under an alias because we have a model FIELD named `date`.
# Writing `date: date | None = None` crashes: the field's default binds
# `date = None` in the class namespace, which then shadows the `date` type when
# the annotation is resolved (`None | None` → TypeError). Aliasing the type to
# `date_` means the field name and the type name never collide.
from datetime import date as date_, datetime

from pydantic import BaseModel


class WorkoutCreate(BaseModel):
    type: str | None = None
    date: date_ | None = None
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
