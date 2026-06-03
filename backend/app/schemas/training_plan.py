from datetime import date, datetime

from pydantic import BaseModel


class TrainingPlanOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    generated_at: datetime
    week_start: date
    plan_json: str
    prompt_summary: str | None = None
